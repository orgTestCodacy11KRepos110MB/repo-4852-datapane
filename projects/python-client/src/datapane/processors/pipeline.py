from __future__ import annotations

import dataclasses as dc
import os
import typing as t
import webbrowser
from abc import ABC
from base64 import b64encode
from os import path as osp
from pathlib import Path
from uuid import uuid4

import importlib_resources as ir
from jinja2 import Environment, FileSystemLoader, Template, pass_context
from lxml import etree
from markupsafe import Markup

from datapane.blocks import BaseElement, View
from datapane.common import NPath, timestamp, ViewXML
from datapane.client import DPClientError, display_msg, config as c
from datapane.client.analytics import _NO_ANALYTICS, capture
from datapane.client.utils import InvalidReportError
from datapane.cloud_api import AppFormatting


from .file_store import FileEntry, FileStore
from .. import AppWidth


def get_cdn() -> str:
    from datapane import __version__
    cdn_base: str = os.getenv("DATAPANE_CDN_BASE", f"https://datapane-cdn.com/v{__version__}")
    return cdn_base


@dc.dataclass(frozen=True)
class ViewAST:
    # TODO - should these be parameterised types??
    # maybe a FileHandler interface??
    view_xml: ViewXML
    store: FileStore


Step = t.Callable[..., ViewAST]


class Pipeline:
    """A simple, programmable, eagerly-evaluated, pipeline that is specialised on ViewAST transformations"""

    # TODO - should we just use a lib for this?

    _state: ViewAST

    def __init__(self, s: ViewAST):
        self._state = s

    def pipe(self, step: Step) -> Pipeline:
        s1 = step(self._state)
        return Pipeline(s1)

    @property
    def result(self) -> ViewAST:
        return self._state


class BaseProcessor:
    """
    Contains logic for generating an App document and converting to XML
    """

    def __call__(self, *a, **kw):
        raise NotImplementedError("Implement in subclass")


class OptimiseAST(BaseProcessor):
    def __call__(self, view: View) -> View:
        """TODO - optimisations to improve the layout of the view"""
        return view


class PreUploadProcessor(BaseProcessor):
    def __call__(self, view: ViewAST) -> ViewAST:
        """TODO - pre-upload pass of the AST, can handle inlining file attributes from AssetStore"""
        return view


@dc.dataclass
class BuilderState:
    # TODO - does this subsume FileStore?
    """Hold state whilst building the Report XML document"""

    _dispatch_to: t.ClassVar[str] = "_to_xml"

    store: FileStore
    # embedded: bool = False
    # served: bool = False

    # attachment_count: int = 0
    # NOTE - store as single element or a list?
    # element: t.Optional[etree.Element] = None  # Empty Group Element?
    elements: t.List[etree.Element] = dc.field(default_factory=list)
    # attachments: t.List[Path] = dc.field(default_factory=list)

    @property
    def store_count(self) -> int:
        return len(self.store.files)

    def add_element(self, block: BaseElement, e: etree.Element) -> BuilderState:
        """Add an element to the list of nodes at the current XML tree location"""
        if block.name:
            e.set("name", block.name)

        self.elements.append(e)
        return self


class ConvertXML(BaseProcessor):
    """Convert the AST into XML"""

    def __init__(
        self,
        embedded: bool,
        served: bool,
        file_entry_klass: t.Type[FileEntry],
        dir_path: t.Optional[Path] = None,
        validate: bool = True,
    ):
        self.embedded = embedded
        self.served = served
        self.validate = validate
        # TODO - should we use a lambda for file_entry_klass with dir_path captured?
        self.file_store = FileStore(file_entry_klass, assets_dir=dir_path)
        if embedded and served:
            raise DPClientError("App can't be both embedded and served")

    def __call__(self, view: View) -> ViewAST:
        """Convert the View AST into an XML fragment"""

        # create initial state
        builder_state = BuilderState(store=self.file_store)
        report_doc, store = view._to_xml(builder_state)

        # TODO - move this out...
        # post_process and validate
        # processed_report_doc = local_post_transform(
        #     report_doc, embedded="true()" if self.embedded else "false()", served="true()" if self.served else "false()"
        # )
        # if self.validate:
        #     validate_report_doc(xml_doc=processed_report_doc)
        #     self._doc_status_checks(processed_report_doc)

        # convert to string
        view_xml_str = etree.tounicode(report_doc)

        #

        return ViewAST(view_xml_str, store)

    def _doc_status_checks(self, processed_report_doc: etree._ElementTree):
        # check for any unsupported local features, e.g. DataTable
        # NOTE - we could eventually have different validators for local and uploaded reports
        if self.embedded:
            return None

        # App checks
        # TODO - validate at least a single element
        asset_blocks = processed_report_doc.xpath("count(/View/*)")
        if asset_blocks == 0:
            raise InvalidReportError("Empty view - must contain at least one block")


class BaseExportHTML(BaseProcessor, ABC):
    """Provides shared logic for writing an app to local disk"""

    template: t.Optional[Template] = None
    # Type is `ir.abc.Traversable` which extends `Path`,
    # but the former isn't compatible with `shutil`
    internal_resources: Path = t.cast(Path, ir.files("datapane.resources.local_report"))
    logo: str
    template_name: str
    report_id: str = uuid4().hex
    served: bool

    def _write_html_template(
        self,
        view: ViewAST,
        name: str = "app",
        formatting: t.Optional[AppFormatting] = None,
    ) -> t.Tuple[str, str]:
        """Internal method to write the ViewXML and assets into a HTML container and associated files"""
        # create template on demand
        if not self.template:
            self._setup_template()

        formatting = formatting or AppFormatting()
        assets = view.store.as_dict() or {}
        report_id: str = uuid4().hex
        report_str = self.template.render(
            report_doc=view.view_xml,
            assets=assets,
            report_width_class=report_width_classes.get(formatting.width),
            report_name=name,
            report_date=timestamp(),
            css_header=formatting.to_css(),
            is_light_prose=formatting.light_prose,
            dp_logo=self.logo,
            report_id=report_id,
            author_id=c.config.session_id,
            events=not _NO_ANALYTICS,
            cdn_base=get_cdn(),
        )

        return report_str, report_id

    def _setup_template(self):
        # load the logo
        logo_img = (self.internal_resources / "datapane-logo-dark.png").read_bytes()
        self.logo = f"data:image/png;base64,{b64encode(logo_img).decode('ascii')}"

        template_loader = FileSystemLoader(self.internal_resources)
        template_env = Environment(loader=template_loader)
        template_env.globals["include_raw"] = include_raw
        self.template = template_env.get_template(self.template_name)


class ExportHTMLInlineAssets(BaseExportHTML):
    """Saves a given App as a single HTML file"""

    served = False
    template_name = "template.html"
    _tmp_report: t.Optional[Path] = None  # Temp local report

    def __init__(
        self, path: str, open: bool = False, name: t.Optional[str] = None, formatting: t.Optional[AppFormatting] = None
    ):
        self.path = path
        self.open = open
        self.name = name
        self.formatting = formatting

    def __call__(
        self,
        view: ViewAST,
    ) -> str:
        report_str, report_id = self._write_html_template(view, self.path, self.name, self.formatting, self.open)

        Path(self.path).write_text(report_str, encoding="utf-8")

        display_msg(f"App saved to ./{self.path}")

        if open:
            path_uri = f"file://{osp.realpath(osp.expanduser(self.path))}"
            webbrowser.open_new_tab(path_uri)

        capture("CLI Report Save", report_id=report_id)
        return report_id


class ExportHTMLFileAssets(BaseExportHTML):
    template_name = "template.html"
    served = True

    def __init__(self, app_dir: Path, name: str = "app", formatting: t.Optional[AppFormatting] = None):
        self.app_dir = app_dir
        self.name = name
        self.formatting = formatting

    def __call__(
        self,
        view: ViewAST,
        dest: t.Optional[NPath] = None,
    ) -> Path:

        # bundle_path = app_dir / SERVED_REPORT_BUNDLE_DIR
        # assets_path = app_dir / SERVED_REPORT_ASSETS_DIR
        #
        # bundle_path.mkdir(parents=True)
        # assets_path.mkdir(parents=True)

        # NOTE - unneeded as always use CDN
        # Copy across symlinked app bundle.
        # Ignore `call-arg` as CI errors on `dirs_exist_ok`
        # copytree(self.internal_resources / "report", bundle_path / "app", dirs_exist_ok=True)  # type: ignore[call-arg]
        # Copy across symlinked Vue module
        # copy(self.internal_resources / VUE_ESM_FILE, bundle_path / VUE_ESM_FILE)
        # Copy across attachments
        # # TODO - these should be placed in location by the FileHandler
        # for a in view.files:
        #     destination_path = assets_path / a.name
        #     if compress_assets:
        #         with compress_file(a) as a_gz:
        #             copy(a_gz, destination_path)
        #     else:
        #         copy(a, destination_path)


        report_str, report_id = self._write_html_template(
            view,
            name=self.name,
            formatting=self.formatting,
        )

        index_path = self.app_dir / "index.html"
        index_path.write_text(report_str, encoding="utf-8")
        display_msg(f"Built app in {self.app_dir}")
        return self.app_dir


class ExportHTMLStringInlineAssets(BaseExportHTML):
    """Export the View as a resizable HTML fragment"""
    served = False
    template_name = "template.html"

    def __init__(self,
        name: str = "Stringified App",
        formatting: t.Optional[AppFormatting] = None,
    ):
        self.name = name
        self.formatting = formatting

    def __call__(self, view: ViewAST) -> str:
        report_str, report_id = self._write_html_template(
            view,
            name=self.name,
            formatting=self.formatting
        )

        return report_str


@pass_context
def include_raw(ctx, name) -> Markup:  # noqa: ANN001
    """Normal jinja2 {% include %} doesn't escape {{...}} which appear in React's source code"""
    env = ctx.environment
    # Escape </script> to prevent 3rd party JS terminating the local app bundle.
    # Note there's an extra "\" because it needs to be escaped at both the python and JS level
    src = env.loader.get_source(env, name)[0].replace("</script>", r"<\\/script>")
    return Markup(src)


# TODO - Refactor to share dp_tags.widths
report_width_classes = {
    AppWidth.NARROW: "max-w-3xl",
    AppWidth.MEDIUM: "max-w-screen-xl",
    AppWidth.FULL: "max-w-full",
}

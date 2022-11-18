"""
Datapane Processors

Describes an API for serializing a Report object, rendering it locally and publishing to a remote server
"""

from __future__ import annotations

import abc
import dataclasses as dc
import datetime
import gzip
import hashlib
import io
import os
import shutil
import tempfile
import threading
import typing as t
import webbrowser
from abc import ABC
from base64 import b64encode
from contextlib import contextmanager
from http.server import HTTPServer, SimpleHTTPRequestHandler
from os import path as osp
from pathlib import Path
from shutil import copy, copyfileobj, copytree, rmtree
from time import sleep
from uuid import uuid4

import base64io
import importlib_resources as ir
from jinja2 import Environment, FileSystemLoader, Template, pass_context
from lxml import etree
from markupsafe import Markup  # used by Jinja

from datapane import __version__ as dp_version
from datapane.client import config as c
from datapane.client.analytics import _NO_ANALYTICS, capture, capture_event
from datapane.client.api.common import DPTmpFile, Resource
from datapane.client.api.runtime import _report
from datapane.client.utils import DPError, InvalidReportError, display_msg
from datapane.common import NPath, SDict, dict_drop_empty, guess_type, log, timestamp
from datapane.common.report import ViewXML, local_report_def, validate_report_doc
from datapane.common.utils import compress_file, pushd

from ...commands import file
from .blocks import BaseElement, View
from .core import App, AppFormatting, AppWidth

if t.TYPE_CHECKING:
    from datapane.client.api.common import FileAttachmentList


__all__ = ["upload", "save_report", "serve", "build"]

CDN_BASE: str = os.getenv("DATAPANE_CDN_BASE", f"https://datapane-cdn.com/v{dp_version}")


# TODO - Refactor to share dp_tags.widths
report_width_classes = {
    AppWidth.NARROW: "max-w-3xl",
    AppWidth.MEDIUM: "max-w-screen-xl",
    AppWidth.FULL: "max-w-full",
}


local_post_xslt = etree.parse(str(local_report_def / "local_post_process.xslt"))
local_post_transform = etree.XSLT(local_post_xslt)

VUE_ESM_FILE = "vue.esm-browser.prod.js"
SERVED_REPORT_BUNDLE_DIR = "static"
SERVED_REPORT_ASSETS_DIR = "assets"


class CompressedAssetsHTTPHandler(SimpleHTTPRequestHandler):
    """
    Python HTTP server for served local apps,
    with correct encoding header set on compressed assets
    """

    def end_headers(self):
        if self.path.startswith(f"/{SERVED_REPORT_ASSETS_DIR}") and not self.path.endswith(VUE_ESM_FILE):
            self.send_header("Content-Encoding", "gzip")
        super().end_headers()


@pass_context
def include_raw(ctx, name) -> Markup:  # noqa: ANN001
    """Normal jinja2 {% include %} doesn't escape {{...}} which appear in React's source code"""
    env = ctx.environment
    # Escape </script> to prevent 3rd party JS terminating the local app bundle.
    # Note there's an extra "\" because it needs to be escaped at both the python and JS level
    src = env.loader.get_source(env, name)[0].replace("</script>", r"<\\/script>")
    return Markup(src)


XFileHandler = t.List[Path]
GZIP_MTIME = datetime.datetime(year=2000, month=1, day=1).timestamp()


class FileEntry:
    file: t.IO
    _ext: str
    _dir_path: t.Optional[Path]

    # post-freeze
    frozen: bool = False
    mime: str
    hash: str
    size: int
    wrapped: t.BinaryIO

    def __init__(self, ext: str, mime: t.Optional[str] = None, dir_path: t.Optional[Path] = None):
        self.mime = mime or guess_type(Path(f"tmp{ext}"))
        self._ext = ext
        self._dir_path = dir_path

    def freeze(self) -> None:
        """Must be called after writing / adding to store
        # TODO - add to contextmanager??
        """
        if not self.frozen:
            self.frozen = True
            # self.file.flush()
            # set the internal properties
            # self.hash = self.hash or "HASH"
            # self.size = 100  #self.file.tell()

    @property
    @abc.abstractmethod
    def src(self) -> str:
        pass

    def as_dict(self) -> dict:
        assert self.frozen
        return dict(src=self.src, hash=self.hash, size=self.size, mime=self.mime)

    def as_fileentry(self) -> FileEntry:
        # TODO - needed??
        assert self.frozen
        return FileEntry(file=self, hash=self.hash, size=self.size, mime=self.mime)


class B64FileEntry(FileEntry):
    """Memory-based b64 file"""

    # requires b64io is bytes only and wraps to a bytes file only
    file: base64io.Base64IO
    wrapped: io.BytesIO
    contents: bytes

    def __init__(self, ext: str, mime: str, *a, **kw):
        super().__init__(ext, mime, *a, **kw)
        self.wrapped = io.BytesIO()
        self.file = base64io.Base64IO(self.wrapped)

    def freeze(self) -> None:
        if not self.frozen:
            self.frozen = True
            # get a reference to the buffer to splice later
            self.file.close()
            self.file.flush()
            self.contents = self.wrapped.getvalue()
            # calc other properties
            self.hash = hashlib.sha256(self.contents).hexdigest()[:10]
            self.size = self.wrapped.tell()

    @property
    def src(self) -> str:
        return f"data:{self.mime};base64,{self.contents.decode('ascii')}"


class GzipTmpFileEntry(FileEntry):
    """Gzipped file, by default stored in /tmp"""

    # both file and wapper files are bytes-only
    file: gzip.GzipFile
    # TODO - this could actually be an in-memory file...
    wrapped: tempfile.NamedTemporaryFile
    has_output_dir: bool = False

    # Do we need DPTmpFile here, or just use namedtempfile??
    def __init__(self, ext: str, mime: str, dir_path: t.Optional[Path] = None):
        super().__init__(ext, mime, dir_path)

        if dir_path:
            # create as a permanent file within the given dir
            self.has_output_dir = True
            self.wrapped = tempfile.NamedTemporaryFile("w+b", suffix=ext, prefix="dp-", dir=dir_path, delete=False)
        else:
            self.wrapped = tempfile.NamedTemporaryFile("w+b", suffix=ext, prefix="dp-")

        self.file = gzip.GzipFile(fileobj=self.wrapped, mode="w+b", mtime=GZIP_MTIME)

    def calc_hash(self, f: t.IO) -> str:
        f.seek(0)
        file_hash = hashlib.sha256()
        while chunk := f.read(8192):
            file_hash.update(chunk)
        return file_hash.hexdigest()[:10]

    @property
    def src(self) -> str:
        if self.has_output_dir:
            return f"/{SERVED_REPORT_ASSETS_DIR}/{Path(self.wrapped.name).name}"
        else:
            return "NYI"

    def freeze(self) -> None:
        if not self.frozen:
            self.frozen = True
            self.file.flush()
            self.file.close()
            self.wrapped.flush()
            # size will be the compressed size...
            self.size = self.wrapped.tell()
            self.hash = self.calc_hash(self.wrapped)


class FileStore:
    # TODO - make this a CAS (index by object itself?)
    # NOTE - currently we pass dir_path via the FileStore, could move into the file themselves?
    def __init__(self, fw_klass: t.Type[FileEntry], assets_dir: t.Optional[Path] = None):
        super().__init__()
        self.fw_klass = fw_klass
        self.files: t.List[FileEntry] = []
        self.dir_path = assets_dir

    def __add__(self, other: FileStore):
        # TODO - ensure factory is the same for both
        self.files.append(other.files)
        return self

    # # TODO - move to a contextmanager??
    # def get_file(self) -> t.IO:
    #     # return a file-type object to write into
    #     # TODO - move out into a factory?
    #     f = self._f()
    #
    # def attach_file(self, f):
    #     # convert asset to file and store in file list
    #     self.files.append(FileElement(file=f))

    @property
    def store_count(self) -> int:
        return len(self.files)

    @property
    def file_list(self) -> t.List[t.BinaryIO]:
        return [f.wrapped for f in self.files]

    @contextmanager
    def write_file(self, ext, mode) -> t.ContextManager[t.IO]:
        # file = self._f(ext)
        file = self.fw_klass(ext=ext)
        try:
            # yield a file-object we can write into
            yield file
        finally:
            file.flush()
            # file.seek(0)
            # file.close()

        self.add_file(file)

    def get_file(self, ext: str, mime: str) -> FileEntry:
        return self.fw_klass(ext, mime, self.dir_path)

    def add_file(self, fw: FileEntry) -> None:
        fw.freeze()
        self.files.append(fw)

    def load_file(self, path: Path) -> FileEntry:
        """load a file into the store (makes a copy)"""
        # TODO - ideally lazily-link a path to the store (rather than include it)
        # TODO - fix??
        ext = "".join(path.suffixes)
        with path.open("wb") as src_obj, self.fw_klass(ext=ext, dir_path=self.dir_path) as dest_obj:
            copyfileobj(src_obj, dest_obj)
        self.add_file(dest_obj)
        return dest_obj

    def as_dict(self) -> dict:
        """Build a json structure suitable for embedding in a html file, json-rpc response, etc."""
        v: FileEntry
        return {k: v.as_dict() for (k, v) in enumerate(self.files, 1)}


# TODO -
@dc.dataclass(frozen=True)
class ViewAST:
    # TODO - should these be parameterised types??
    # maybe a FileHandler interface??
    view_xml: ViewXML
    store: FileStore


# TODO - need to parameterise input and output
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


# def _f():
#     x = ViewAST("", FileStore(mk_b64file))
#     y = Pipeline(x).pipe(lambda s: s).pipe(lambda s: s).result


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


# TODO - should take the served / embedded flag here...
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
            raise DPError("App can't be both embedded and served")

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


###############################################################################
# Local Views
class Stringfy(BaseProcessor):
    # TODO - would be an in-memory FileHandler
    ...


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
        path: str,
        name: t.Optional[str] = None,
        formatting: t.Optional[AppFormatting] = None,
        open: bool = False,
    ) -> str:
        """Internal method to write the ViewXML and assets into a HTML container and associated files"""
        # create template on demand
        if not self.template:
            self._setup_template()

        name = name or Path(path).stem[:127]
        formatting = formatting or AppFormatting()

        # TODO - build the file store...

        assets = view.store.as_dict() or {}

        report_id: str = uuid4().hex
        r = self.template.render(
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
            cdn_base=CDN_BASE,
        )

        Path(path).write_text(r, encoding="utf-8")

        display_msg(f"App saved to ./{path}")

        if open:
            path_uri = f"file://{osp.realpath(osp.expanduser(path))}"
            webbrowser.open_new_tab(path_uri)

        return report_id

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
        report_id = self._write_html_template(view, self.path, self.name, self.formatting, self.open)
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

        self._write_html_template(
            view,
            str(self.app_dir / "index.html"),
            name=self.name,
            formatting=self.formatting,
        )

        display_msg(f"Successfully built app in {self.app_dir}")

        return self.app_dir


################################################################################
# exported public API
def serve(
    view: View,
    name: str = "app",
    dest: t.Optional[NPath] = None,
    port: int = 8000,
    host: str = "localhost",
    formatting: t.Optional[AppFormatting] = None,
    open: bool = True,
    overwrite: bool = False,
) -> None:
    """Serve the app via a local debug server
    Args:
        app: The `App` object
        name: The name of the app directory to be created
        dest: File path to store the app directory
        open: Open in your browser after creating (default: False)
        port: The port used to serve the app (default: 8000)
        host: The host used to serve the app (default: localhost)
        formatting: Sets the basic app styling; note that this is ignored if a app exists at the specified path
        overwrite: Replace existing app with the same name and destination if already exists (default: False)
    """
    # NOTE - this is basically build the static view, then serve

    # build in a tmp dir then serve
    app_dir = Path(tempfile.mkdtemp(prefix="dp-"))
    build(view, name="app", dest=app_dir, formatting=formatting)

    # Run the server in the specified path
    with pushd(app_dir / "app"):
        server = HTTPServer((host, port), CompressedAssetsHTTPHandler)
        display_msg(f"Server started at {host}:{port}")

        if open:
            # If the endpoint is simply opened then there is a race
            # between the page loading and server becoming available.
            def _open_browser(host: str, port: int) -> None:
                sleep(1)  # yield so server in main thread can start
                webbrowser.open_new_tab(f"http://{host}:{port}")

            threading.Thread(target=_open_browser, args=(host, port), daemon=True).start()

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            shutil.rmtree(app_dir, ignore_errors=True)


def build(
    view: View,
    name: str = "app",
    dest: t.Optional[NPath] = None,
    formatting: t.Optional[AppFormatting] = None,
    overwrite: bool = False,
) -> None:
    """Build an (static) app with a directory structure, which can be served by a local http server
    TODO(product) - unknown if we should keep this...

    Args:
        view: The `View` object
        name: The name of the app directory to be created
        dest: File path to store the app directory
        formatting: Sets the basic app styling
        overwrite: Replace existing app with the same name and destination if already exists (default: False)
    """

    # build the dest dir
    app_dir: Path = Path(dest or os.getcwd()) / name
    app_exists = app_dir.is_dir()

    if app_exists and overwrite:
        rmtree(app_dir)
    elif app_exists and not overwrite:
        raise DPError(f"App exists at given path {str(app_dir)} -- set `overwrite=True` to allow overwrite")

    assets_dir = app_dir / "assets"
    assets_dir.mkdir(parents=True)

    # write the app html and assets
    report_id: str = (
        Pipeline(view)
        .pipe(OptimiseAST())
        .pipe(
            ConvertXML(
                embedded=True,
                served=False,
                validate=True,
                file_entry_klass=GzipTmpFileEntry,
                dir_path=assets_dir,
            )
        )
        .pipe(ExportHTMLFileAssets(app_dir=app_dir, name=name, formatting=formatting))
        .result
    )


def save_report(
    view: View,
    path: str,
    open: bool = False,
    name: t.Optional[str] = None,
    formatting: t.Optional[AppFormatting] = None,
) -> None:
    """Save the app document to a local HTML file
    Args:
        view: The `View` object
        path: File path to store the document
        open: Open in your browser after creating (default: False)
        name: Name of the document (optional: uses path if not provided)
        formatting: Sets the basic app styling
    """

    report_id: str = (
        Pipeline(view)
        .pipe(OptimiseAST())
        .pipe(
            ConvertXML(
                embedded=True,
                served=False,
                validate=True,
                file_entry_klass=B64FileEntry,
            )
        )
        .pipe(ExportHTMLInlineAssets(path=path, open=open, name=name, formatting=formatting))
        .result
    )

    # TODO - now what? save the id?


def upload(
    view: View,
    name: str,
    description: str = "",
    source_url: str = "",
    publicly_visible: bool = False,
    tags: t.List[str] = None,
    project: t.Optional[str] = None,
    open: bool = False,
    formatting: t.Optional[AppFormatting] = None,
    overwrite: bool = False,
    **kwargs,
) -> App:
    """
    Upload the app, including its attached assets, to the logged-in Datapane Server.
    Args:
        view: The current View
        name: The document name - can include spaces, caps, symbols, etc., e.g. "Profit & Loss 2020"
        description: A high-level description for the document, this is displayed in searches and thumbnails
        source_url: A URL pointing to the source code for the document, e.g. a GitHub repo or a Colab notebook
        publicly_visible: Visible to anyone with the link
        tags: A list of tags (as strings) used to categorise your document
        project: Project to add the app to
        open: Open the file in your browser after creating
        formatting: Set the basic styling for your app
        overwrite: Overwrite the app
    """

    display_msg("Uploading app and associated data - *please wait...*")

    kwargs.update(
        name=name,
        description=description,
        tags=tags or [],
        source_url=source_url,
        publicly_visible=publicly_visible,
        project=project,
    )
    # additional formatting params
    if formatting:
        kwargs.update(
            width=formatting.width.value,
            style_header=(
                f'<style type="text/css">\n{formatting.to_css()}\n</style>' if c.config.is_org else formatting.to_css()
            ),
            is_light_prose=formatting.light_prose,
        )
    # current protocol is to strip all empty args and patch (via a post)
    kwargs = dict_drop_empty(kwargs)

    view_ast: ViewAST = (
        Pipeline(view)
        .pipe(OptimiseAST())
        .pipe(
            ConvertXML(
                embedded=True,
                served=False,
                validate=True,
                file_entry_klass=GzipTmpFileEntry,
            )
        )
        .pipe(PreUploadProcessor())
        .result
    )

    # attach the view and upload as an App
    files: FileAttachmentList = dict(attachments=view_ast.store.file_list)
    app = App.post_with_files(files, overwrite=overwrite, document=view_ast.view_xml, **kwargs)

    if open:
        webbrowser.open_new_tab(app.web_url)

    display_msg(
        "App successfully uploaded. View and share your app at {web_url:l}.",
        web_url=app.web_url,
    )
    return app

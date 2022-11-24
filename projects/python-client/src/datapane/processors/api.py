"""
Datapane Processors

API for serializing a View, rendering it locally and publishing to a remote server
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import typing as t
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from shutil import rmtree
from time import sleep

from lxml import etree

from datapane.blocks import View
from datapane.client import config as c
from datapane.client import DPClientError, display_msg
from datapane.common import NPath, dict_drop_empty, pushd
from datapane.common.viewxml_utils import local_report_def
from datapane.cloud_api.app import App, AppFormatting

from .file_store import B64FileEntry, GzipTmpFileEntry, SERVED_REPORT_ASSETS_DIR
from .pipeline import ConvertXML, ExportHTMLFileAssets, ExportHTMLInlineAssets, ExportHTMLStringInlineAssets, OptimiseAST, Pipeline, PreUploadProcessor, ViewAST

if t.TYPE_CHECKING:
    from datapane.cloud_api.common import FileAttachmentList


__all__ = ["upload", "save_report", "serve", "build", "stringify_report"]




local_post_xslt = etree.parse(str(local_report_def / "local_post_process.xslt"))
local_post_transform = etree.XSLT(local_post_xslt)

VUE_ESM_FILE = "vue.esm-browser.prod.js"


class CompressedAssetsHTTPHandler(SimpleHTTPRequestHandler):
    """
    Python HTTP server for served local apps,
    with correct encoding header set on compressed assets
    """

    def end_headers(self):
        if self.path.startswith(f"/{SERVED_REPORT_ASSETS_DIR}") and not self.path.endswith(VUE_ESM_FILE):
            self.send_header("Content-Encoding", "gzip")
        super().end_headers()


XFileHandler = t.List[Path]

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
        raise DPClientError(f"App exists at given path {str(app_dir)} -- set `overwrite=True` to allow overwrite")

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


def stringify_report(
    view: View,
    name: t.Optional[str] = None,
    formatting: t.Optional[AppFormatting] = None,
) -> str:
    """Stringify the app document to a HTML string

    Args:
        view: The `View` object
        name: Name of the document (optional: uses path if not provided)
        formatting: Sets the basic app styling
    """

    report_html: str = (
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
        .pipe(ExportHTMLStringInlineAssets(name=name, formatting=formatting))
        .result
    )

    return report_html


def upload(
    view: View,
    name: str,
    description: str = "",
    source_url: str = "",
    publicly_visible: t.Optional[bool] = None,
    tags: t.Optional[t.List[str]] = None,
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

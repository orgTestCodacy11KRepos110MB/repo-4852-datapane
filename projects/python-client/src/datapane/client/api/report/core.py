"""
Datapane Reports Object

Describes the `Report` object
"""

import dataclasses as dc
import os
import typing as t
from enum import Enum
from pathlib import Path
from uuid import uuid4

from datapane import __version__ as dp_version
from datapane.client.api.common import DPTmpFile
from datapane.client.api.dp_object import DPObjectRef

from .blocks import View

CDN_BASE: str = os.getenv("DATAPANE_CDN_BASE", f"https://datapane-cdn.com/v{dp_version}")

# only these types will be documented by default
__all__ = ["App", "AppWidth"]

__pdoc__ = {
    "App.endpoint": False,
}


class AppWidth(Enum):
    NARROW = "narrow"
    MEDIUM = "medium"
    FULL = "full"


class TextAlignment(Enum):
    JUSTIFY = "justify"
    LEFT = "left"
    RIGHT = "right"
    CENTER = "center"


class FontChoice(Enum):
    DEFAULT = "Inter var, ui-sans-serif, system-ui"
    SANS = "ui-sans-serif, sans-serif, system-ui"
    SERIF = "ui-serif, serif, system-ui"
    MONOSPACE = "ui-monospace, monospace, system-ui"


# TODO - remove?
class PageLayout(Enum):
    TOP = "top"
    SIDE = "side"


@dc.dataclass
class AppFormatting:
    """Sets the app styling and formatting"""

    bg_color: str = "#FFF"
    accent_color: str = "#4E46E5"
    font: t.Union[FontChoice, str] = FontChoice.DEFAULT
    text_alignment: TextAlignment = TextAlignment.JUSTIFY
    width: AppWidth = AppWidth.MEDIUM
    light_prose: bool = False

    def to_css(self) -> str:
        if isinstance(self.font, FontChoice):
            font = self.font.value
        else:
            font = self.font

        return f""":root {{
    --dp-accent-color: {self.accent_color};
    --dp-bg-color: {self.bg_color};
    --dp-text-align: {self.text_alignment.value};
    --dp-font-family: {font};
}}"""


# Used to detect a single display message once per VM invocation
# SKIP_DISPLAY_MSG = False


# TODO - this should be the return from upload...?
class App(DPObjectRef):
    """
    App documents collate plots, text, tables, and files into an interactive document that
    can be analysed and shared by users in their Browser
    """

    _tmp_report: t.Optional[Path] = None  # Temp local report
    _preview_file = DPTmpFile(f"{uuid4().hex}.html")
    list_fields: t.List[str] = ["name", "web_url", "project"]

    endpoint: str = "/reports/"
    # pages: t.List[Page]
    # page_layout: t.Optional[PageLayout]
    view: View

    # id_count: int = 1

    def __init__(
        self,
        view: View,
        /,
        **kwargs,
    ):
        """
        Args:
            *arg_blocks: Group to add to document
            blocks: Allows providing the document blocks as a single list

        Returns:
            A `App` document object that can be uploaded, saved, etc.

        ..tip:: Blocks can be passed using either arg parameters or the `blocks` kwarg, e.g.
          `dp.App(plot, table)` or `dp.App(blocks=[plot, table])`

        ..tip:: Create a list first to hold your blocks to edit them dynamically, for instance when using Jupyter, and use the `blocks` parameter
        """
        super().__init__(**kwargs)
        self.view = view

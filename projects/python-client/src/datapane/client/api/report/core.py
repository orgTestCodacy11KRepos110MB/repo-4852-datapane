"""
Datapane Reports Object

Describes the `Report` object
"""
from __future__ import annotations

import dataclasses as dc
import os
import typing as t
from enum import Enum

from datapane.client.api.dp_object import DPObjectRef

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


# NOTE - this is essentially a DPCloud App - we should split the App object and the DPObjectRef parts here...
class App(DPObjectRef):
    """
    App documents collate plots, text, tables, and files into an interactive document that
    can be analysed and shared by users in their Browser
    """

    # NOTE - uploading handled via the DPCloudUploader processor
    list_fields: t.List[str] = ["name", "web_url", "project"]
    endpoint: str = "/reports/"

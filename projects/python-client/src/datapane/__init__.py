# Copyright 2020 StackHut Limited (trading as Datapane)
# SPDX-License-Identifier: Apache-2.0
import sys
from pathlib import Path

try:
    from ._version import __rev__
except ImportError:
    # NOTE - could use subprocess to get from git?
    __rev__ = "local"

__version__ = "0.15.4"



# Other useful re-exports
from .client import DPMode, DPClientError, IN_PYTEST, enable_logging, set_dp_mode, get_dp_mode  # isort:skip  otherwise circular import issue
from .client.config import init

# Public API re-exports
from .cloud_api import (
    App,
    AppFormatting,
    AppWidth,
    File,
    FontChoice,
    TextAlignment,
    hello_world,
    login,
    logout,
    ping,
)
from .blocks import Attachment, BigNumber, Empty, DataTable, Media, Plot, Table, Select, SelectType, Formula, HTML, Code, Divider, Embed, Group, Text, Toggle, Interactive, View
from .processors import save_report, serve, upload, stringify_report, build
from . import builtins

__all__ = [
    "App",
    "AppFormatting",
    "AppWidth",
    "BigNumber",
    "Empty",
    "File",
    "FontChoice",
    "Interactive",
    "SelectType",
    "TextAlignment",
    "builtins",
    "hello_world",
    "login",
    "logout",
    "ping",
    "enable_logging",
    "load_params_from_command_line",
    "upload",
    "save_report",
    "serve",
    "build",
    "stringify_report"
]


script_name = sys.argv[0]
script_exe = Path(script_name).stem
by_datapane = False  # hardcode for now as not using legacy runner
if script_exe == "datapane" or script_name == "-m":  # or "pytest" in script_name:
    # argv[0] will be "-m" as client module as submodule of this module
    set_dp_mode(DPMode.SCRIPT)
elif by_datapane or script_exe == "dp-runner":
    set_dp_mode(DPMode.FRAMEWORK)
else:
    set_dp_mode(DPMode.LIBRARY)

# TODO - do we want to init only in jupyter / interactive / etc.
# only init fully in library-mode, as framework and app init explicitly
if get_dp_mode() == DPMode.LIBRARY and not IN_PYTEST:
    init()


def load_params_from_command_line() -> None:
    """Call this from your own scripts to read any CLI parameters into the global Params object"""
    pass
    # from .client.utils import parse_command_line
    #
    # config = parse_command_line()
    # Params.replace(config)

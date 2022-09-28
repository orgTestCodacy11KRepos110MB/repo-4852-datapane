"""This module provides a simple interface to capture analytics data"""
import os
import sys
import platform
from contextlib import suppress
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, cast

import posthog

from .utils import IN_PYTEST, ON_DATAPANE, log
from . import config as c

posthog.api_key = "phc_wxtD2Qxd3RMlmCCSYDC0rW1We22yh06cMcffnfSJTZy"
posthog.host = "https://events.datapane.com/"
_NO_ANALYTICS_FILE: Path = c.APP_DIR / "no_analytics"

IN_DPSERVER = "dp" in sys.modules
USING_CONDA = os.path.exists(os.path.join(sys.prefix, "conda-meta", "history"))


def is_analytics_disabled() -> bool:
    """Determine the initial state for analytics if not already set"""
    # disable if globally disabled or in certain envs
    if _NO_ANALYTICS_FILE.exists() or ON_DATAPANE or IN_PYTEST or IN_DPSERVER:
        log.debug("Analytics disabled")
        return True
    return False


_NO_ANALYTICS: bool = is_analytics_disabled()


from collections import namedtuple

SysProps = namedtuple("SysProps", "dp_version is_jupyter nb_env")

def _get_sys_props() -> SysProps:
    from datapane import __version__  # noqa
    from .ipython_utils import get_environment_type, is_jupyter  # noqa
    return SysProps(dp_version=__version__, is_jupyter=is_jupyter(), nb_env=get_environment_type())


def capture(event: str, config: Optional[c.Config] = None, **properties) -> None:
    # Used for capturing generic events with properties
    if _NO_ANALYTICS:
        return None
    config = config or c.get_config()

    sys_props = _get_sys_props()

    # run identify on first action, (NOTE - don't change the order here)
    if not config.completed_action:
        config.completed_action = True
        identify(config)
        config.save()

    properties.update(
        source="cli",
        dp_version=sys_props.dp_version,
        environment_type=sys_props.nb_env,
        in_jupyter=sys_props.is_jupyter,
        using_conda=USING_CONDA,
    )

    with suppress(Exception):
        posthog.capture(config.session_id, event, properties)


def identify(config: c.Config, **properties) -> None:
    if _NO_ANALYTICS:
        return None

    sys_props = _get_sys_props()

    properties.update(
        os=platform.system(),
        python_version=platform.python_version(),
        dp_version=sys_props.dp_version,
        environment_type=sys_props.nb_env,
        in_jupyter=sys_props.is_jupyter,
        using_conda=USING_CONDA,
    )
    with suppress(Exception):
        posthog.identify(config.session_id, properties)
    # Also generate a CLI identify event to help disambiguation
    capture("CLI Identify", config=config)


# def capture_init(config: c.Config) -> None:
#     # Generates an identify event on init
#     if _NO_ANALYTICS:
#         return None
#     identify(config.session_id)

# From the mypy docs ...https://mypy.readthedocs.io/en/stable/generics.html#declaring-decorators
F = TypeVar("F", bound=Callable[..., Any])


def capture_event(name: str) -> Callable[[F], F]:
    """Decorator to capture 'name' as analytics event when the function is called"""

    def _decorator(func: F) -> F:
        @wraps(func)
        def _wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            finally:
                capture(name)

        return cast(F, _wrapper)

    return _decorator

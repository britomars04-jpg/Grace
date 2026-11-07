"""Browser control for the Grace voice agent.

Exposes Playwright browser automation to the agent as a small set of tools.
See ``docs/browser.md`` for configuration and the two supported engines.
"""

from __future__ import annotations

from .config import BrowserConfig
from .controller import BrowserController, BrowserError
from .tools import BROWSER_TOOL_NAMES, build_browser_tools

__all__ = [
    "BROWSER_TOOL_NAMES",
    "BrowserConfig",
    "BrowserController",
    "BrowserError",
    "build_browser_tools",
]

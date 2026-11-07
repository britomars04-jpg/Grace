"""Configuration for the browser control subsystem.

All values are read from the environment so the same code runs locally (plain
Playwright on Windows/macOS/Linux) and in the Linux container on LiveKit Cloud
(the CEF-based ``livekit-plugins-browser`` engine, which also publishes the
browser into the room as a screenshare video track).

See ``docs/browser.md`` for the environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

EngineChoice = Literal["auto", "playwright", "cef"]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


@dataclass
class BrowserConfig:
    """Runtime configuration for :class:`BrowserController`."""

    #: Which engine to use. ``auto`` picks CEF where it is supported (Linux and
    #: macOS), and falls back to plain Playwright elsewhere (for example Windows).
    engine: EngineChoice = "auto"

    #: Start the browser headless. CEF always renders off-screen, so this only
    #: affects the Playwright engine. Set to False on a desktop to watch the
    #: agent browse in a real window.
    headless: bool = True

    #: Apply light anti-automation ("stealth") measures on the Playwright
    #: engine so ordinary sites and search engines are less likely to treat the
    #: session as a bot. Removes the ``navigator.webdriver`` flag and other
    #: automation giveaways. Has no effect on CEF.
    stealth: bool = True

    #: Browser user agent used by the Playwright engine. Empty means a current
    #: desktop Chrome string is used, which pairs with ``stealth``.
    user_agent: str = ""

    #: Chromium channel to launch (for example "chrome" or "msedge"). Empty
    #: uses the Chromium bundled with Playwright. Using a real installed
    #: browser looks less automated to sites that fingerprint Chromium builds.
    channel: str = ""

    #: Viewport size. Also the size of the published video track on CEF.
    width: int = 1280
    height: int = 720
    framerate: int = 24

    #: Page loaded when the browser starts. Kept blank so the agent decides
    #: where to go (and so the URL policy runs on every navigation).
    start_url: str = "about:blank"

    #: Timeouts, in seconds.
    action_timeout: float = 15.0
    nav_timeout: float = 30.0

    #: Cap on the number of interactive elements returned by ``browser_look``,
    #: and on the raw page text appended to it. Keeps the LLM context small.
    max_snapshot_refs: int = 120
    max_snapshot_text: int = 3000

    #: Publish the browser to the room as a screenshare track (CEF only).
    publish_video: bool = True

    #: Host policy. When ``allowed_hosts`` is empty the agent may reach any
    #: public host, subject to ``blocked_hosts`` and the private-address guard.
    #: Populate it to switch to a strict allowlist.
    allowed_hosts: list[str] = field(default_factory=list)
    blocked_hosts: list[str] = field(default_factory=list)

    #: Block requests that resolve to private, loopback, link-local or
    #: otherwise non-public addresses (SSRF protection).
    block_private_addresses: bool = True

    #: Require an explicit confirmation before "sensitive" actions such as
    #: submitting a form or clicking a button whose label looks destructive.
    confirm_sensitive_actions: bool = True

    @classmethod
    def from_env(cls) -> BrowserConfig:
        engine = os.environ.get("BROWSER_ENGINE", "auto").strip().lower()
        if engine not in {"auto", "playwright", "cef"}:
            engine = "auto"
        return cls(
            engine=engine,  # type: ignore[arg-type]
            headless=_env_bool("BROWSER_HEADLESS", True),
            stealth=_env_bool("BROWSER_STEALTH", True),
            user_agent=os.environ.get("BROWSER_USER_AGENT", "").strip(),
            channel=os.environ.get("BROWSER_CHANNEL", "").strip().lower(),
            width=_env_int("BROWSER_WIDTH", 1280),
            height=_env_int("BROWSER_HEIGHT", 720),
            framerate=_env_int("BROWSER_FRAMERATE", 24),
            start_url=os.environ.get("BROWSER_START_URL", "about:blank"),
            action_timeout=_env_float("BROWSER_ACTION_TIMEOUT", 15.0),
            nav_timeout=_env_float("BROWSER_NAV_TIMEOUT", 30.0),
            max_snapshot_refs=_env_int("BROWSER_MAX_SNAPSHOT_REFS", 120),
            max_snapshot_text=_env_int("BROWSER_MAX_SNAPSHOT_TEXT", 3000),
            publish_video=_env_bool("BROWSER_PUBLISH_VIDEO", True),
            allowed_hosts=_env_list("BROWSER_ALLOWED_HOSTS"),
            blocked_hosts=_env_list("BROWSER_BLOCKED_HOSTS"),
            block_private_addresses=_env_bool("BROWSER_BLOCK_PRIVATE", True),
            confirm_sensitive_actions=_env_bool("BROWSER_CONFIRM_SENSITIVE", True),
        )

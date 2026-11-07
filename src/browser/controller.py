"""Browser lifecycle and operations.

The controller owns a single :class:`playwright.async_api.Page` and exposes
coarse, speech-friendly operations on top of it. Both supported engines hand the
same Playwright ``Page`` to this class, so everything below is engine-agnostic:

* :class:`PlaywrightEngine` launches a headless Chromium. It works on Windows,
  macOS and Linux and is the default for local development and for tests.
* :class:`CefEngine` drives ``livekit-plugins-browser`` (Chromium Embedded
  Framework). CEF ships for Linux and macOS only, and additionally publishes the
  browser into the room as a screenshare video track so the user can watch and
  take over. This is the production engine in the Linux container.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
import tempfile
from contextlib import AsyncExitStack
from typing import Any

from playwright.async_api import Page, async_playwright

from .config import BrowserConfig
from .safety import PolicyError, ensure_url_allowed, normalize_url, sensitive_reason
from .snapshot import element_for_ref, ref_metadata, take_snapshot

logger = logging.getLogger("browser")


def _cef_supported() -> bool:
    return sys.platform.startswith("linux") or sys.platform.startswith("darwin")


class BrowserError(Exception):
    """A browser operation failed in a way the agent should report."""


class PlaywrightEngine:
    """Chromium via Playwright. No in-room video."""

    kind = "playwright"

    #: A current desktop Chrome UA. The bundled Chromium reports a "HeadlessChrome"
    #: style UA and an obvious automation surface; a normal UA plus the stealth
    #: init script below makes the session look like an ordinary browser, which
    #: matters for sites (Google, DuckDuckGo) that block obvious bots.
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    #: Runs before any page script. Hides the traits automation tools are
    #: detected by: the ``navigator.webdriver`` flag, the missing plugin list,
    #: and a headless-looking ``navigator.languages``/``chrome`` object.
    STEALTH_INIT_SCRIPT = """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5].map(i => ({ name: 'Plugin ' + i })),
        });
        window.chrome = window.chrome || { runtime: {} };
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        const originalQuery = window.navigator.permissions?.query;
        if (originalQuery) {
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters)
            );
        }
    """

    def __init__(self, config: BrowserConfig) -> None:
        self._config = config
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self.page: Page | None = None
        self.video_session: Any = None

    def _launch_args(self) -> list[str]:
        args = [
            "--disable-dev-shm-usage",
            "--hide-scrollbars",
            "--disable-blink-features=AutomationControlled",
        ]
        if self._config.stealth:
            # Drop the "Chrome is being controlled by automated software" bar and
            # the automation infobar, both of which are visible bot signals.
            args += [
                "--disable-infobars",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=IsolateOrigins,site-per-process",
            ]
        else:
            args.append("--disable-gpu")
        # Chromium's sandbox is unavailable in most containers; keep it off there
        # but let the sandbox run on a normal desktop.
        if not sys.platform.startswith("win32") and not sys.platform.startswith(
            "darwin"
        ):
            args.insert(0, "--no-sandbox")
        return args

    async def start(self) -> Page:
        self._pw = await async_playwright().start()
        launch_kwargs: dict[str, Any] = {
            "headless": self._config.headless,
            "args": self._launch_args(),
        }
        if self._config.channel:
            launch_kwargs["channel"] = self._config.channel
        self._browser = await self._pw.chromium.launch(**launch_kwargs)
        context_kwargs: dict[str, Any] = {
            "viewport": {"width": self._config.width, "height": self._config.height},
            "locale": "en-US",
        }
        if self._config.stealth:
            context_kwargs.update(
                {
                    "user_agent": self._config.user_agent or self.DEFAULT_USER_AGENT,
                    "timezone_id": "America/New_York",
                    "extra_http_headers": {"Accept-Language": "en-US,en;q=0.9"},
                }
            )
        elif self._config.user_agent:
            context_kwargs["user_agent"] = self._config.user_agent
        self._context = await self._browser.new_context(**context_kwargs)
        if self._config.stealth:
            await self._context.add_init_script(self.STEALTH_INIT_SCRIPT)
        timeout_ms = int(self._config.action_timeout * 1000)
        nav_timeout_ms = int(self._config.nav_timeout * 1000)
        self._context.set_default_timeout(timeout_ms)
        self._context.set_default_navigation_timeout(nav_timeout_ms)
        self.page = await self._context.new_page()
        return self.page

    async def close(self) -> None:
        for closer in (self._context, self._browser):
            if closer is not None:
                with contextlib.suppress(Exception):
                    await closer.close()
        if self._pw is not None:
            with contextlib.suppress(Exception):
                await self._pw.stop()


class CefEngine:
    """Chromium Embedded Framework via ``livekit-plugins-browser``.

    Also publishes the page into the room as a screenshare track, which enables
    the browser to be visible to the user and to accept human input.
    """

    kind = "cef"

    def __init__(self, config: BrowserConfig, room: Any | None) -> None:
        self._config = config
        self._room = room
        self._stack = AsyncExitStack()
        self._browser_ctx: Any = None
        self._cef_page: Any = None
        self.page: Page | None = None
        self.video_session: Any = None

    async def start(self) -> Page:
        # Imported lazily so Windows development (and unit tests) never needs CEF.
        from livekit.plugins.browser import BrowserContext, BrowserSession

        if not _cef_supported():
            raise BrowserError(
                f"the CEF engine does not support {sys.platform}; "
                "use BROWSER_ENGINE=playwright"
            )

        self._browser_ctx = BrowserContext(dev_mode=False)
        await self._browser_ctx.initialize()

        self._cef_page = await self._browser_ctx.new_page(
            url=self._config.start_url,
            width=self._config.width,
            height=self._config.height,
            framerate=self._config.framerate,
        )

        browser = await self._stack.enter_async_context(
            self._browser_ctx.playwright(self._config.nav_timeout)
        )
        pages = [page for context in browser.contexts for page in context.pages]
        if not pages:
            raise BrowserError("the CEF browser exposed no pages")
        self.page = pages[0]
        self.page.set_default_timeout(int(self._config.action_timeout * 1000))

        if self._room is not None and self._config.publish_video:
            self.video_session = BrowserSession(page=self._cef_page, room=self._room)
            await self.video_session.start()

        return self.page

    async def close(self) -> None:
        if self.video_session is not None:
            with contextlib.suppress(Exception):
                await self.video_session.aclose()
        with contextlib.suppress(Exception):
            await self._stack.aclose()
        if self._cef_page is not None:
            with contextlib.suppress(Exception):
                await self._cef_page.aclose()
        if self._browser_ctx is not None:
            with contextlib.suppress(Exception):
                await self._browser_ctx.aclose()


class BrowserController:
    """Owns one browser page and the operations the agent can perform on it."""

    def __init__(self, config: BrowserConfig, *, room: Any | None = None) -> None:
        self.config = config
        self._room = room
        self._engine: PlaywrightEngine | CefEngine | None = None
        self._page: Page | None = None
        self._lock = asyncio.Lock()
        self._started = False

    @property
    def page(self) -> Page:
        if self._page is None:
            raise BrowserError("the browser is not started yet")
        return self._page

    @property
    def engine_kind(self) -> str:
        return self._engine.kind if self._engine is not None else "none"

    @property
    def started(self) -> bool:
        return self._started

    @property
    def video_enabled(self) -> bool:
        return self._engine is not None and self._engine.video_session is not None

    async def start(self) -> None:
        if self._started:
            return

        choice = self.config.engine
        if choice == "auto":
            choice = "cef" if _cef_supported() else "playwright"

        if choice == "cef":
            try:
                engine: PlaywrightEngine | CefEngine = CefEngine(
                    self.config, self._room
                )
                self._page = await engine.start()
            except Exception:
                logger.exception(
                    "CEF engine failed to start, falling back to Playwright"
                )
                await engine.close()
                engine = PlaywrightEngine(self.config)
                self._page = await engine.start()
        else:
            engine = PlaywrightEngine(self.config)
            self._page = await engine.start()

        self._engine = engine
        self._started = True
        logger.info("browser started (engine=%s)", engine.kind)

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.close()
        self._engine = None
        self._page = None
        self._started = False
        logger.info("browser closed")

    async def _ensure_started(self) -> None:
        """Start the engine on first use. Safe to call repeatedly."""
        if not self._started:
            await self.start()

    # -- internal helpers -------------------------------------------------

    async def _settle(self, *, timeout: float | None = None) -> None:
        """Give the page a moment to finish reacting to an action."""

        budget = (
            timeout if timeout is not None else min(self.config.action_timeout, 10.0)
        )
        with contextlib.suppress(Exception):
            await self.page.wait_for_load_state(
                "domcontentloaded", timeout=budget * 1000
            )

    async def _describe(self) -> str:
        snapshot = await take_snapshot(
            self.page, max_refs=self.config.max_snapshot_refs
        )
        return snapshot.format(max_text=self.config.max_snapshot_text)

    async def _run(self, label: str, coro: Any) -> Any:
        await self._ensure_started()
        async with self._lock:
            try:
                return await coro
            except PolicyError:
                raise
            except BrowserError:
                raise
            except Exception as err:
                logger.warning("browser action %s failed: %s", label, err)
                raise BrowserError(f"{label} failed: {err}") from err

    # -- operations -------------------------------------------------------

    async def look(self) -> str:
        async def _op() -> str:
            return await self._describe()

        return await self._run("look", _op())

    async def open(self, url: str) -> str:
        target = normalize_url(url)
        await ensure_url_allowed(target, self.config)

        async def _op() -> str:
            await self.page.goto(target, wait_until="domcontentloaded")
            await self._settle()
            return await self._describe()

        return await self._run(f"open {target}", _op())

    async def click(self, ref: str, *, confirm: bool = False) -> str:
        async def _op() -> str:
            metadata = await ref_metadata(self.page, ref)
            label = str(metadata.get("text", ""))
            is_submit = metadata.get("type") == "submit"
            reason = sensitive_reason(label, is_submit=is_submit)

            if reason and self.config.confirm_sensitive_actions and not confirm:
                return (
                    f"'{label or ref}' may {reason}. Read it back to the user, "
                    "get their go-ahead, then call browser_click again with "
                    "confirm=true."
                )

            locator = element_for_ref(self.page, ref)
            await locator.scroll_into_view_if_needed(timeout=5000)
            await locator.click()
            await self._settle()
            return await self._describe()

        return await self._run(f"click {ref}", _op())

    async def type_text(self, ref: str, text: str, *, submit: bool = False) -> str:
        async def _op() -> str:
            metadata = await ref_metadata(self.page, ref)
            if metadata.get("type") == "password":
                return (
                    "That field is a password input. I will not type credentials "
                    "into a page."
                )

            locator = element_for_ref(self.page, ref)
            await locator.scroll_into_view_if_needed(timeout=5000)
            await locator.fill(text)
            if submit:
                await locator.press("Enter")
            await self._settle()
            return await self._describe()

        return await self._run(f"type into {ref}", _op())

    async def press(self, key: str) -> str:
        async def _op() -> str:
            await self.page.keyboard.press(key)
            await self._settle()
            return await self._describe()

        return await self._run(f"press {key}", _op())

    async def select(self, ref: str, option: str) -> str:
        async def _op() -> str:
            locator = element_for_ref(self.page, ref)
            await locator.select_option(label=option)
            await self._settle()
            return await self._describe()

        return await self._run(f"select {option} in {ref}", _op())

    async def scroll(self, direction: str, amount: int) -> str:
        axis = {"down": (0, 1), "up": (0, -1), "right": (1, 0), "left": (-1, 0)}
        if direction not in axis:
            raise BrowserError("direction must be up, down, left or right")
        dx, dy = axis[direction]
        step = max(1, min(amount, 20)) * 400

        async def _op() -> str:
            await self.page.evaluate(
                "([x, y]) => window.scrollBy(x, y)", [dx * step, dy * step]
            )
            await asyncio.sleep(0.3)
            return await self._describe()

        return await self._run(f"scroll {direction}", _op())

    async def history(self, action: str) -> str:
        async def _op() -> str:
            if action == "back":
                await self.page.go_back(wait_until="domcontentloaded")
            elif action == "forward":
                await self.page.go_forward(wait_until="domcontentloaded")
            elif action == "reload":
                await self.page.reload(wait_until="domcontentloaded")
            else:
                raise BrowserError("action must be back, forward or reload")
            await self._settle()
            return await self._describe()

        return await self._run(f"history {action}", _op())

    async def wait_for(self, kind: str, value: str, timeout: float) -> str:
        seconds = max(1.0, min(timeout, 60.0))

        async def _op() -> str:
            if kind == "text" and value:
                await self.page.get_by_text(value, exact=False).first.wait_for(
                    state="visible", timeout=seconds * 1000
                )
            elif kind == "selector" and value:
                await self.page.wait_for_selector(value, timeout=seconds * 1000)
            elif kind == "networkidle":
                await self.page.wait_for_load_state(
                    "networkidle", timeout=seconds * 1000
                )
            elif kind == "time":
                await asyncio.sleep(seconds)
            else:
                raise BrowserError("kind must be text, selector, networkidle or time")
            return await self._describe()

        return await self._run(f"wait_for {kind}", _op())

    async def read(self, max_chars: int) -> str:
        limit = max(200, min(max_chars, 20000))

        async def _op() -> str:
            text = await self.page.evaluate(
                "() => (document.body ? document.body.innerText : '')"
            )
            collapsed = " ".join(str(text).split())
            if len(collapsed) > limit:
                collapsed = collapsed[:limit] + " …[truncated]"
            return collapsed or "(the page has no readable text)"

        return await self._run("read", _op())

    async def tabs(self, action: str, index: int) -> str:
        async def _op() -> str:
            context = self.page.context
            if action == "list":
                lines = []
                for position, tab in enumerate(context.pages):
                    marker = " (active)" if tab is self.page else ""
                    title = "(untitled)"
                    with contextlib.suppress(Exception):
                        title = await tab.title()
                    lines.append(f"{position}: {title} {tab.url}{marker}")
                return "Open tabs:\n" + "\n".join(lines)
            if action == "open":
                new_tab = await context.new_page()
                await new_tab.goto("about:blank")
                await new_tab.bring_to_front()
                self._page = new_tab
                return await self._describe()
            if action == "switch":
                pages = context.pages
                if index < 0 or index >= len(pages):
                    return f"There is no tab at index {index}."
                self._page = pages[index]
                await self._page.bring_to_front()
                return await self._describe()
            if action == "close":
                if len(context.pages) <= 1:
                    return "That is the only tab, so I left it open."
                await self.page.close()
                self._page = context.pages[0]
                await self._page.bring_to_front()
                return await self._describe()
            raise BrowserError("action must be list, open, switch or close")

        return await self._run(f"tabs {action}", _op())

    async def screenshot(self) -> str:
        async def _op() -> str:
            png = await self.page.screenshot(full_page=False)
            with tempfile.NamedTemporaryFile(
                prefix="grace-shot-", suffix=".png", delete=False
            ) as handle:
                handle.write(png)
                path = handle.name
            return (
                f"Screenshot saved to {path} ({len(png)} bytes). The model cannot "
                "view images yet; use browser_look instead."
            )

        return await self._run("screenshot", _op())

    async def evaluate(self, expression: str) -> str:
        async def _op() -> str:
            result = await self.page.evaluate(expression)
            text = repr(result)
            if len(text) > 4000:
                text = text[:4000] + " …[truncated]"
            return text

        return await self._run("evaluate", _op())

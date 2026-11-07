"""The browser tools exposed to the agent.

``build_browser_tools`` returns ``@function_tool`` callables bound to a single
:class:`~browser.controller.BrowserController`. The agent's ``Assistant`` builds
them once per job and adds them to its tool list on demand, so the browsing
surface is only in the prompt while a browsing task is active.
"""

from __future__ import annotations

from livekit.agents import RunContext, function_tool

from .controller import BrowserController, BrowserError

BROWSER_TOOL_NAMES = (
    "browser_open",
    "browser_look",
    "browser_click",
    "browser_type",
    "browser_press",
    "browser_select",
    "browser_scroll",
    "browser_history",
    "browser_wait_for",
    "browser_read",
    "browser_tabs",
    "browser_screenshot",
    "browser_close",
    "browser_eval",
)


def build_browser_tools(controller: BrowserController) -> list:
    """Create the browser tool set bound to ``controller``."""

    @function_tool()
    async def browser_open(context: RunContext, url: str) -> str:
        """Open a web page in the browser and describe what is on it.

        Call this whenever the user asks to go to a site or look something up
        online. Accepts a full URL or a bare domain such as "example.com".
        After it returns, use the numbered element references (ref=e1, e2, …)
        to interact with the page.

        Args:
            url: The address to open, for example "news.ycombinator.com".

        Returns:
            The page URL, title, its interactive elements, and visible text.
        """
        try:
            return await controller.open(url)
        except BrowserError as err:
            return str(err)

    @function_tool()
    async def browser_look(context: RunContext) -> str:
        """Describe the page that is currently open, with fresh element refs.

        Call this any time you are unsure what is on screen, and after an action
        whose result you were not already told. Refreshes the ref=eN handles, so
        always look again before clicking after a page change.

        Returns:
            The page URL, title, interactive elements, and visible text.
        """
        try:
            return await controller.look()
        except BrowserError as err:
            return str(err)

    @function_tool()
    async def browser_click(
        context: RunContext, ref: str, confirm: bool = False
    ) -> str:
        """Click an element on the page, identified by its ref from browser_look.

        Use this for links, buttons, checkboxes, tabs, and similar controls.

        Args:
            ref: The element reference from the latest browser_look, e.g. "e3".
            confirm: Set true only when the user has already approved a
                sensitive click (submitting, paying, deleting, and so on).
                Leave false the first time; the tool will ask you to confirm.

        Returns:
            The page after the click.
        """
        try:
            return await controller.click(ref, confirm=confirm)
        except BrowserError as err:
            return str(err)

    @function_tool()
    async def browser_type(
        context: RunContext, ref: str, text: str, submit: bool = False
    ) -> str:
        """Type text into a text field, identified by its ref from browser_look.

        Use this to fill in searches and form fields. Never type passwords or
        payment details; those fields are refused.

        Args:
            ref: The field reference from the latest browser_look, e.g. "e2".
            text: The text to enter, exactly as it should appear.
            submit: Set true to press Enter after typing, to run the search or
                submit the field.

        Returns:
            The page after typing.
        """
        try:
            return await controller.type_text(ref, text, submit=submit)
        except BrowserError as err:
            return str(err)

    @function_tool()
    async def browser_press(context: RunContext, key: str) -> str:
        """Press a single key, such as Enter, Tab, Escape, PageDown or ArrowDown.

        Use this after browser_type when you need a key the field did not send,
        or to dismiss a dialog with Escape.

        Args:
            key: The key name, for example "Enter" or "Escape".

        Returns:
            The page after the key press.
        """
        try:
            return await controller.press(key)
        except BrowserError as err:
            return str(err)

    @function_tool()
    async def browser_select(context: RunContext, ref: str, option: str) -> str:
        """Choose an option in a dropdown, identified by its ref from browser_look.

        Args:
            ref: The dropdown reference from the latest browser_look.
            option: The visible text of the option to select.

        Returns:
            The page after selecting.
        """
        try:
            return await controller.select(ref, option)
        except BrowserError as err:
            return str(err)

    @function_tool()
    async def browser_scroll(
        context: RunContext, direction: str, amount: int = 3
    ) -> str:
        """Scroll the page to reveal more content.

        Args:
            direction: One of "down", "up", "left" or "right".
            amount: How far to scroll, roughly in screens. Defaults to 3.

        Returns:
            The page after scrolling.
        """
        try:
            return await controller.scroll(direction, amount)
        except BrowserError as err:
            return str(err)

    @function_tool()
    async def browser_history(context: RunContext, action: str) -> str:
        """Move through the browser's history.

        Args:
            action: One of "back", "forward" or "reload".

        Returns:
            The page after navigating history.
        """
        try:
            return await controller.history(action)
        except BrowserError as err:
            return str(err)

    @function_tool()
    async def browser_wait_for(
        context: RunContext, kind: str, value: str = "", timeout: float = 15.0
    ) -> str:
        """Wait for something to happen on the page, such as a slow load.

        Args:
            kind: One of "text" (wait for some text to appear), "selector"
                (wait for a CSS selector), "networkidle" (wait for the network
                to go quiet) or "time" (just wait).
            value: The text or selector to wait for, when kind is text or
                selector. Ignored otherwise.
            timeout: Maximum seconds to wait, between 1 and 60.

        Returns:
            The page once the wait finishes or times out.
        """
        try:
            return await controller.wait_for(kind, value, timeout)
        except BrowserError as err:
            return str(err)

    @function_tool()
    async def browser_read(context: RunContext, max_chars: int = 4000) -> str:
        """Read the visible text of the current page.

        Use this to quote or summarise page content, especially long articles
        where you do not need the element list.

        Args:
            max_chars: Maximum characters to return, between 200 and 20000.

        Returns:
            The visible text of the page.
        """
        try:
            return await controller.read(max_chars)
        except BrowserError as err:
            return str(err)

    @function_tool()
    async def browser_tabs(context: RunContext, action: str, index: int = 0) -> str:
        """Manage browser tabs.

        Args:
            action: One of "list", "open", "switch" or "close".
            index: The tab index for "switch". Ignored otherwise.

        Returns:
            The list of tabs, or the page after the action.
        """
        try:
            return await controller.tabs(action, index)
        except BrowserError as err:
            return str(err)

    @function_tool()
    async def browser_screenshot(context: RunContext) -> str:
        """Capture a screenshot of the current page for debugging.

        Prefer browser_look for reading the page; screenshots are not yet sent
        to the model.

        Returns:
            A short confirmation.
        """
        try:
            return await controller.screenshot()
        except BrowserError as err:
            return str(err)

    @function_tool()
    async def browser_close(context: RunContext) -> str:
        """Close the browser once the browsing task is finished.

        Call this when the user is done with the browser to free its resources.

        Returns:
            A short confirmation.
        """
        try:
            if not controller.started:
                return "The browser is not open."
            await controller.close()
            return "The browser is closed."
        except BrowserError as err:
            return str(err)

    @function_tool()
    async def browser_eval(context: RunContext, expression: str) -> str:
        """Run a JavaScript expression in the page and return its value.

        This is an escape hatch for advanced cases the other tools do not cover.
        Prefer the dedicated tools. The expression runs in the page context and
        must be a single expression, for example
        "document.querySelectorAll('a').length".

        Args:
            expression: A JavaScript expression to evaluate.

        Returns:
            The value the expression produced, as text.
        """
        try:
            return await controller.evaluate(expression)
        except BrowserError as err:
            return str(err)

    return [
        browser_open,
        browser_look,
        browser_click,
        browser_type,
        browser_press,
        browser_select,
        browser_scroll,
        browser_history,
        browser_wait_for,
        browser_read,
        browser_tabs,
        browser_screenshot,
        browser_close,
        browser_eval,
    ]

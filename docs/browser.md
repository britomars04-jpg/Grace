# Browser control

Grace can drive a real web browser. This document explains how it works, how to
configure it, and what is not finished yet.

## How it fits together

```
Assistant (src/agent.py)
  └─ browser/* tools           # browser_open, browser_click, ...
       └─ BrowserController (src/browser/controller.py)
            └─ engine           # CEF or Playwright -> one Playwright Page
```

Two engines produce the **same** `playwright.async_api.Page`, so the tool layer is
identical on both:

| Engine | Where it works | In-room video | Notes |
| --- | --- | --- | --- |
| `cef` (`livekit-plugins-browser`) | Linux, macOS | Yes, as a screenshare track with human takeover | Production engine in the container. **Not supported on Windows.** |
| `playwright` (headless Chromium) | Windows, Linux, macOS | No | Default on Windows and in CI, and the local dev engine. |

`BROWSER_ENGINE=auto` picks CEF on Linux/macOS and Playwright everywhere else,
and falls back to Playwright if CEF fails to start.

> Important: `livekit-browser` ships CEF binaries for Linux and macOS only.
> `get_resources_dir()` raises `RuntimeError: Unsupported platform` on Windows.
> Development on Windows therefore uses the Playwright engine; the CEF engine is
> exercised in the Linux container.

## The tools

All fifteen tools are registered when the session starts. They are deliberately
registered up front rather than added mid-conversation: the Google realtime model
reconnects its session when the tool list changes, and in testing that reconnect
timed out (`generate_reply timed out waiting for generation_created event`).
Static registration avoids it. Renaming the tools so the browser set is clearly
grouped (everything is prefixed `browser_`) keeps selection reliable without a
mid-session update.

The browser itself is created per job but launched **lazily**, on the first
browser tool call, so sessions that never browse pay no startup cost.

| Tool | Purpose |
| --- | --- |
| `browser_open` | Go to a URL and describe the page. |
| `browser_look` | Re-describe the page with fresh refs. |
| `browser_click` | Click an element by ref. |
| `browser_type` | Fill a text field by ref, optionally submit. |
| `browser_press` | Press a key such as Enter or Escape. |
| `browser_select` | Choose a dropdown option. |
| `browser_scroll` | Scroll the page. |
| `browser_history` | Back, forward, reload. |
| `browser_wait_for` | Wait for text, a selector, or network idle. |
| `browser_read` | Read the page's visible text. |
| `browser_tabs` | List, open, switch, close tabs. |
| `browser_screenshot` | Save a PNG for debugging. |
| `browser_close` | Close the browser. |
| `browser_eval` | Escape hatch: run a JavaScript expression. |

### Why refs instead of coordinates

`browser_look` tags every visible, interactive element with a `data-lk-ref`
attribute and returns lines like:

```
[ref=e3] button "Continue"
[ref=e2] textbox "Password" value='(hidden)'
[ref=e5] link "Next page" -> https://example.com/next
```

The model acts on `ref=e3`; the controller resolves it to a DOM locator. This is
far more reliable for a language model than pixel coordinates, and it is what
makes the same tool set work over both engines.

Refs are refreshed on every `browser_look`, so always look after the page changes.

## Safety

- **URL policy** (`src/browser/safety.py`): only `http`/`https`; `file:`,
  `javascript:`, `data:`, `chrome:`, `view-source:` and friends are refused.
  Hosts that resolve to private, loopback or link-local addresses are blocked
  (SSRF protection), including `169.254.169.254`.
- **Allowlist**: set `BROWSER_ALLOWED_HOSTS` to restrict browsing to specific
  sites. Empty means *any public site*, which suits an assistant that looks
  things up.
- **Sensitive actions**: clicking something that looks like it submits, pays,
  buys or deletes returns a request to confirm instead of acting. The model must
  read it back to the user and retry with `confirm=true`.
- **Credentials**: password fields are refused outright.
- **Ephemeral profile**: the CEF engine uses a fresh temporary profile per
  `BrowserContext` and deletes it on close, so no logged-in session persists.

## Configuration

All via environment (see `.env.example`): `BROWSER_ENGINE`, `BROWSER_HEADLESS`,
`BROWSER_WIDTH`/`BROWSER_HEIGHT`, `BROWSER_ALLOWED_HOSTS`,
`BROWSER_BLOCKED_HOSTS`, `BROWSER_BLOCK_PRIVATE`, `BROWSER_CONFIRM_SENSITIVE`,
`BROWSER_ACTION_TIMEOUT`, `BROWSER_NAV_TIMEOUT`.

## Local development

```console
uv sync
uv run playwright install chromium   # once
uv run python scripts/smoke_browser.py
uv run pytest tests/test_browser_policy.py tests/test_browser_page.py
```

The smoke script drives a real browser end to end: navigation, snapshot refs,
clicking by ref, typing, the sensitive-action gate and the URL policy.

## Deployment

The `Dockerfile` installs Chromium's runtime libraries in the production stage and
sets `XDG_CACHE_HOME=/app/.cache`, so the CEF engine downloaded during
`uv run --module livekit.agents download-files` in the build stage is carried into
the final image instead of being fetched at runtime.

## Not finished yet

- **Vision**: `browser_screenshot` saves a PNG but the image is not sent to the
  model. Screenshots are diagnostic only; grounding is DOM/refs. Wiring the
  screenshot into a multimodal turn is a follow-up.
- **Identity gate**: Grace's identity handling lives in her prompt. A hard
  "verified caller" gate on browser tools should be added once an identity flow
  exists; the hook would live in `src/browser/safety.py`.
- **Frames**: the snapshot only inspects the main frame, not cross-origin
  iframes.
- **CEF in the container**: the Dockerfile has the runtime libraries, but the
  image should be built once to confirm CEF starts as the non-root `appuser`
  (sandbox and `chrome-sandbox` ownership may need attention).

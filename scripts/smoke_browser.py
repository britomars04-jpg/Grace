"""Manual smoke test for the browser subsystem.

Runs the plain Playwright engine end to end without a LiveKit room:

    uv run python scripts/smoke_browser.py

Exercises: engine startup, navigation, the accessibility snapshot and its refs,
clicking by ref, typing into a field, and the URL policy.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

for stream in (sys.stdout, sys.stderr):
    with __import__("contextlib").suppress(Exception):
        stream.reconfigure(encoding="utf-8", errors="replace")

from browser.config import BrowserConfig  # noqa: E402
from browser.controller import BrowserController  # noqa: E402
from browser.safety import PolicyError, ensure_url_allowed  # noqa: E402

FORM_HTML = """
<!doctype html>
<html><head><title>Grace form test</title></head>
<body>
  <h1>Sign in</h1>
  <label for="user">Username</label>
  <input id="user" type="text" placeholder="Your username">
  <label for="pw">Password</label>
  <input id="pw" type="password">
  <button id="go" onclick="document.title='Clicked!'">Continue</button>
  <button id="danger" onclick="document.title='Deleted!'">Delete account</button>
  <a href="https://example.com/next">Next page</a>
</body></html>
"""


async def main() -> int:
    config = BrowserConfig.from_env()
    config.engine = "playwright"
    controller = BrowserController(config)

    print(f"engine requested: {config.engine}")
    await controller.start()
    print(f"engine started:   {controller.engine_kind}")

    print("\n=== 1. open a real site ===")
    described = await controller.open("example.com")
    print(described[:800])

    print("\n=== 2. deterministic form page ===")
    await controller.page.set_content(FORM_HTML)
    described = await controller.look()
    print(described)

    import re

    refs = dict(re.findall(r"\[ref=(e\d+)\] (\w+)", described))
    text_field = next(r for r, role in refs.items() if role == "textbox")
    buttons = [r for r, role in refs.items() if role == "button"]

    print(f"\nrefs found: {refs}")
    print(f"using text field {text_field}, buttons {buttons}")

    print("\n=== 3. type into the field ===")
    await controller.type_text(text_field, "nicholas")
    print(f"typed; title still: {await controller.page.title()!r}")

    print("\n=== 4. click Continue ===")
    await controller.click(buttons[0])
    title_after = await controller.page.title()
    print(f"title after click: {title_after!r}")
    assert title_after == "Clicked!", title_after

    print("\n=== 5. sensitive action must be gated ===")
    gated = await controller.click(buttons[1])
    print(gated.splitlines()[0])
    assert "confirm=true" in gated, "delete should be gated"
    print(
        f"title before confirming (should not be 'Deleted!'): "
        f"{await controller.page.title()!r}"
    )

    print("\n=== 6. password field must be refused ===")
    # Re-look to refresh refs after the earlier snapshot mutated nothing.
    described = await controller.look()
    pw_refs = re.findall(r"\[ref=(e\d+)\] textbox", described)
    pw_ref = pw_refs[-1] if len(pw_refs) > 1 else None
    if pw_ref:
        # Mark it as the password field for the check by evaluating the type.
        ptype = await controller.page.evaluate(
            f"() => document.querySelector('[data-lk-ref=\"{pw_ref}\"]').type"
        )
        print(f"pw candidate {pw_ref} type={ptype}")
        if ptype == "password":
            refused = await controller.type_text(pw_ref, "hunter2")
            print(refused)
            assert "will not type credentials" in refused

    print("\n=== 7. URL policy ===")
    for bad in [
        "file:///etc/passwd",
        "http://localhost:8080",
        "http://169.254.169.254/",
    ]:
        try:
            await ensure_url_allowed(bad, config)
            print(f"  ALLOWED (unexpected): {bad}")
        except PolicyError as err:
            print(f"  blocked {bad!r}: {err}")

    await controller.close()
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

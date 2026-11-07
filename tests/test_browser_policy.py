"""Unit tests for the browser URL policy and action guardrails.

These are hermetic: they touch no network and launch no browser. The private
address checks use literal IPs, ``localhost`` and ``.local`` names so no DNS
lookup is required.
"""

from __future__ import annotations

import pytest

from browser.config import BrowserConfig
from browser.safety import (
    PolicyError,
    ensure_url_allowed,
    normalize_url,
    sensitive_reason,
)


def _config(**overrides: object) -> BrowserConfig:
    base = BrowserConfig()
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_normalize_url_adds_scheme() -> None:
    assert normalize_url("example.com") == "https://example.com"
    assert normalize_url("  example.com  ") == "https://example.com"


def test_normalize_url_keeps_existing_scheme_and_blank() -> None:
    assert normalize_url("http://example.com") == "http://example.com"
    assert normalize_url("about:blank") == "about:blank"
    assert normalize_url("") == ""


async def test_blank_page_is_allowed() -> None:
    await ensure_url_allowed("about:blank", _config())


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<h1>hi</h1>",
        "chrome://settings",
        "view-source:https://example.com",
    ],
)
async def test_dangerous_schemes_are_blocked(url: str) -> None:
    with pytest.raises(PolicyError):
        await ensure_url_allowed(url, _config())


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8080/admin",
        "http://localhost.localdomain/",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://router.local/",
    ],
)
async def test_private_and_link_local_addresses_are_blocked(url: str) -> None:
    with pytest.raises(PolicyError):
        await ensure_url_allowed(url, _config())


async def test_private_addresses_allowed_when_guard_disabled() -> None:
    await ensure_url_allowed(
        "http://127.0.0.1:3000/", _config(block_private_addresses=False)
    )


async def test_allowlist_restricts_hosts() -> None:
    config = _config(allowed_hosts=["example.com"])
    await ensure_url_allowed("https://example.com/page", config)
    await ensure_url_allowed("https://www.example.com/page", config)
    with pytest.raises(PolicyError):
        await ensure_url_allowed("https://example.org/", config)


async def test_allowlist_does_not_exempt_blocked_hosts() -> None:
    config = _config(allowed_hosts=["example.com"], blocked_hosts=["example.com"])
    with pytest.raises(PolicyError):
        await ensure_url_allowed("https://example.com/", config)


async def test_blocked_hosts_apply_without_allowlist() -> None:
    config = _config(blocked_hosts=["ads.example.com"])
    with pytest.raises(PolicyError):
        await ensure_url_allowed("https://tracker.ads.example.com/px", config)


async def test_bare_host_and_port_is_not_mistaken_for_a_scheme() -> None:
    config = _config(allowed_hosts=["example.com"])
    await ensure_url_allowed("example.com:8080/path", config)
    await ensure_url_allowed("https://example.com:8443/path", config)


@pytest.mark.parametrize(
    ("label", "is_submit", "expected"),
    [
        ("Delete account", False, True),
        ("Buy now", False, True),
        ("Place order", False, True),
        ("Submit", False, True),
        ("Continue", True, True),
        ("Next page", False, False),
        ("Read more", False, False),
    ],
)
def test_sensitive_reason(label: str, is_submit: bool, expected: bool) -> None:
    reason = sensitive_reason(label, is_submit=is_submit)
    assert (reason is not None) is expected
    if reason is not None:
        # The reason is interpolated after "may", so it must read as a verb.
        assert reason[0].islower()

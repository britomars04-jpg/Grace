"""URL policy and guardrails for the browser subsystem.

Two independent protections:

* :func:`ensure_url_allowed` runs before every navigation. It enforces the
  scheme allowlist, the optional host allowlist/blocklist, and (by default)
  refuses hosts that resolve to private or otherwise non-public addresses,
  which is the main SSRF risk for an agent that can fetch arbitrary URLs.
* :func:`sensitive_reason` inspects an element the model is about to interact
  with and, for actions that change state or spend money, returns a
  human-readable reason so the tool can require an explicit confirmation.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlsplit

from .config import BrowserConfig

ALLOWED_SCHEMES = {"http", "https"}

# Schemes that stay blocked even though they are reachable in a browser.
_BLOCKED_SCHEME_PREFIXES = ("chrome", "devtools", "view-source", "javascript")

#: Words that, when they appear in an element's label, mark the action as
#: sensitive enough to need an explicit confirmation.
SENSITIVE_PATTERN = re.compile(
    r"\b("
    r"pay|payment|purchase|buy|checkout|order|place order|subscribe|donate|"
    r"transfer|send money|withdraw|deposit|confirm|submit|delete|remove|"
    r"unsubscribe|cancel account|close account|sign out|log out|logout|"
    r"delete account|change password|reset password"
    r")\b",
    re.IGNORECASE,
)


class PolicyError(Exception):
    """Raised when a URL or action is refused by policy."""


def _host_matches(host: str, pattern: str) -> bool:
    host = host.lower().rstrip(".")
    pattern = pattern.lower().rstrip(".")
    if not pattern:
        return False
    if pattern.startswith("*."):
        return host.endswith(pattern[1:]) and host != pattern[2:]
    return host == pattern or host.endswith("." + pattern)


def _is_non_public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _resolves_to_non_public(host: str) -> bool:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        # Unresolvable hosts are rejected by the browser itself; let it try so
        # the agent can report a normal navigation error.
        return False
    for info in infos:
        sockaddr = info[4]
        if sockaddr and _is_non_public(str(sockaddr[0])):
            return True
    return False


async def ensure_url_allowed(url: str, config: BrowserConfig) -> None:
    """Raise :class:`PolicyError` if ``url`` must not be loaded."""

    candidate = (url or "").strip()
    if not candidate:
        raise PolicyError("No URL was provided.")

    # Allow the neutral start page and explicit blank pages.
    if candidate in {"about:blank", "about:newtab"}:
        return

    lower = candidate.lower()
    for prefix in _BLOCKED_SCHEME_PREFIXES:
        if lower.startswith(prefix + ":"):
            raise PolicyError(f"The '{prefix}' scheme is not allowed.")

    # Reject a non-http scheme *before* normalising, because adding "https://"
    # in front of "data:..." or "javascript:..." would hide the real scheme.
    # A bare "host:port" is not a scheme, even though urlsplit would call the
    # host part one, so only treat it as a scheme when the rest is not a port.
    match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):", candidate)
    if match:
        scheme = match.group(1).lower()
        rest = candidate[match.end() :]
        looks_like_port = rest.split("/", 1)[0].isdigit() and "." in scheme
        if scheme not in ALLOWED_SCHEMES and not looks_like_port:
            raise PolicyError(f"Only http and https URLs are allowed, not '{scheme}'.")

    parts = urlsplit(normalize_url(candidate))
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise PolicyError(f"Only http and https URLs are allowed, not '{scheme}'.")

    host = (parts.hostname or "").lower()
    if not host:
        raise PolicyError("The URL has no host.")

    for pattern in config.blocked_hosts:
        if _host_matches(host, pattern):
            raise PolicyError(f"{host} is on the blocked list.")

    if config.allowed_hosts:
        if not any(_host_matches(host, pattern) for pattern in config.allowed_hosts):
            raise PolicyError(
                f"{host} is not on the allowed list. Ask the user before "
                "visiting other sites."
            )
        return

    if config.block_private_addresses:
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            raise PolicyError(f"{host} resolves to a private address.")
        if _is_non_public(host) or await _resolves_to_non_public(host):
            raise PolicyError(
                f"{host} resolves to a private or non-public address, which is "
                "not allowed."
            )


def normalize_url(url: str) -> str:
    """Add a scheme when the model supplies a bare host."""

    candidate = (url or "").strip()
    if not candidate:
        return candidate
    if candidate in {"about:blank", "about:newtab"}:
        return candidate
    if "://" not in candidate:
        return "https://" + candidate
    return candidate


def sensitive_reason(label: str, *, is_submit: bool = False) -> str | None:
    """Return why an action looks sensitive, or ``None`` if it is safe.

    The returned string is phrased to follow "may", e.g. "submit a form".
    """

    if is_submit:
        return "submit a form"
    match = SENSITIVE_PATTERN.search(label or "")
    if match:
        return (
            "change something important (its label mentions "
            f"'{match.group(1).lower()}')"
        )
    return None

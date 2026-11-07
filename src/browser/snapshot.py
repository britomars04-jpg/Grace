"""Turn a live page into a compact, reference-annotated description.

The agent should never guess pixel coordinates. Instead we tag every visible,
interactive element with a stable ``data-lk-ref`` attribute and hand the model a
short list of ``[ref=eN] role "name"`` lines. Tools then act on a ref. This is
the same idea as the accessibility snapshot in Playwright's own MCP server, and
it is what makes DOM-level control reliable for a language model.

The tagging runs inside the page, so it behaves identically on the plain
Playwright engine and on the CEF engine, which only differ in how the
``playwright.async_api.Page`` is obtained.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playwright.async_api import Locator, Page

REF_ATTR = "data-lk-ref"

#: Assigns refs and returns a JSON-serialisable description of the page.
_SNAPSHOT_JS = r"""
(maxRefs) => {
  const ATTR = 'data-lk-ref';
  const MAX = maxRefs || 120;

  document.querySelectorAll('[' + ATTR + ']').forEach((el) => el.removeAttribute(ATTR));

  const clean = (value, limit) => {
    const text = (value || '').replace(/\s+/g, ' ').trim();
    const cap = limit || 120;
    return text.length > cap ? text.slice(0, cap) + '…' : text;
  };

  const isVisible = (el) => {
    if (!el.isConnected) return false;
    if (el.getClientRects().length === 0) return false;
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') return false;
    if (style.opacity && parseFloat(style.opacity) === 0) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 1 && rect.height > 1;
  };

  const roleOf = (el) => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return el.hasAttribute('href') ? 'link' : 'generic';
    if (tag === 'button') return 'button';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'summary') return 'button';
    if (tag === 'input') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      if (['submit', 'button', 'reset', 'image'].includes(type)) return 'button';
      if (type === 'search') return 'searchbox';
      return 'textbox';
    }
    return 'generic';
  };

  const nameOf = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria) return clean(aria);
    const labelledby = el.getAttribute('aria-labelledby');
    if (labelledby) {
      const joined = labelledby
        .split(/\s+/)
        .map((id) => {
          const node = document.getElementById(id);
          return node ? node.innerText : '';
        })
        .join(' ');
      const result = clean(joined);
      if (result) return result;
    }
    const tag = el.tagName.toLowerCase();
    if (tag === 'input') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      if (['submit', 'button', 'reset'].includes(type)) {
        return clean(el.value || el.getAttribute('value'));
      }
      const placeholder = el.getAttribute('placeholder');
      if (placeholder) return clean(placeholder);
    }
    if (tag === 'img') return clean(el.getAttribute('alt'));
    const title = el.getAttribute('title');
    if (title) return clean(title);
    if (['input', 'select', 'textarea'].includes(tag)) {
      if (el.id) {
        const label = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
        if (label) return clean(label.innerText);
      }
      const wrapper = el.closest('label');
      if (wrapper) return clean(wrapper.innerText);
    }
    return clean(el.innerText || el.textContent);
  };

  const isInteractive = (el) => {
    const tag = el.tagName.toLowerCase();
    if (['a', 'button', 'input', 'select', 'textarea', 'summary'].includes(tag)) {
      if (tag === 'a' && !el.hasAttribute('href')) return false;
      return !el.disabled;
    }
    const role = el.getAttribute('role');
    if (role) {
      const interactiveRoles = [
        'button', 'link', 'checkbox', 'radio', 'tab', 'menuitem', 'option',
        'switch', 'textbox', 'searchbox', 'combobox',
      ];
      if (interactiveRoles.includes(role)) return true;
    }
    if (el.hasAttribute('onclick')) return true;
    const tabindex = el.getAttribute('tabindex');
    if (tabindex !== null && parseInt(tabindex, 10) >= 0) return true;
    return el.isContentEditable === true;
  };

  const elements = [];
  let count = 0;
  const candidates = document.querySelectorAll(
    'a,button,input,select,textarea,summary,[role],[onclick],[tabindex],[contenteditable]',
  );

  for (const el of candidates) {
    if (count >= MAX) break;
    if (!isVisible(el) || !isInteractive(el)) continue;
    count += 1;
    const ref = 'e' + count;
    el.setAttribute(ATTR, ref);

    const tag = el.tagName.toLowerCase();
    const entry = { ref: ref, role: roleOf(el), name: nameOf(el) };

    if (tag === 'input') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      entry.type = type;
      if (type === 'password') {
        entry.value = '(hidden)';
      } else if (type === 'checkbox' || type === 'radio') {
        entry.state = el.checked ? 'checked' : 'unchecked';
      } else if (el.value) {
        entry.value = clean(el.value, 80);
      }
    } else if (tag === 'select') {
      entry.value = clean(el.value, 80);
      entry.options = Array.from(el.options)
        .slice(0, 25)
        .map((option) => clean(option.text, 40));
    } else if (tag === 'textarea' && el.value) {
      entry.value = clean(el.value, 80);
    }

    if (tag === 'a') {
      const href = el.getAttribute('href');
      if (href) entry.href = clean(href, 140);
    }
    elements.push(entry);
  }

  let text = '';
  try {
    text = clean(document.body ? document.body.innerText : '', 100000);
  } catch (err) {
    text = '';
  }

  return {
    url: location.href,
    title: document.title,
    count: elements.length,
    truncated: elements.length >= MAX,
    elements: elements,
    text: text,
  };
}
"""


@dataclass
class PageSnapshot:
    url: str
    title: str
    truncated: bool
    elements: list[dict[str, Any]]
    text: str

    def format(self, *, max_text: int = 3000) -> str:
        """Render a speech- and token-friendly description for the LLM."""

        lines = [f"URL: {self.url}", f"Title: {self.title or '(none)'}", ""]

        if self.elements:
            lines.append("Interactive elements:")
            for element in self.elements:
                lines.append("  " + _format_element(element))
            if self.truncated:
                lines.append("  (more elements exist; scroll or refine to see them)")
        else:
            lines.append("Interactive elements: none found.")

        if self.text:
            text = self.text.strip()
            if len(text) > max_text:
                text = text[:max_text] + " …[truncated]"
            lines.append("")
            lines.append("Visible text:")
            lines.append(text)

        return "\n".join(lines)


def _format_element(element: dict[str, Any]) -> str:
    ref = element.get("ref", "?")
    role = element.get("role", "generic")
    name = element.get("name") or "(unnamed)"
    parts = [f'[ref={ref}] {role} "{name}"']

    if element.get("value"):
        parts.append(f"value={element['value']!r}")
    if element.get("state"):
        parts.append(f"({element['state']})")
    if element.get("href"):
        parts.append(f"-> {element['href']}")
    if element.get("options"):
        options = ", ".join(element["options"])
        parts.append(f"options=[{options}]")
    return " ".join(parts)


async def take_snapshot(page: Page, *, max_refs: int = 120) -> PageSnapshot:
    """Run the tagging script and return a structured snapshot."""

    data = await page.evaluate(_SNAPSHOT_JS, max_refs)
    return PageSnapshot(
        url=str(data.get("url", "")),
        title=str(data.get("title", "")),
        truncated=bool(data.get("truncated", False)),
        elements=list(data.get("elements", [])),
        text=str(data.get("text", "")),
    )


def element_for_ref(page: Page, ref: str) -> Locator:
    """Return a locator for a ref produced by :func:`take_snapshot`."""

    clean = (ref or "").strip()
    if not clean:
        raise ValueError("No element reference was provided.")
    if not clean.startswith("e") or not clean[1:].isdigit():
        raise ValueError(
            f"'{ref}' is not a valid reference. Call browser_look first to "
            "get fresh references like e1, e2, …"
        )
    return page.locator(f'[{REF_ATTR}="{clean}"]')


async def ref_metadata(page: Page, ref: str) -> dict[str, Any]:
    """Read back the label/role of a ref, for confirmation prompts."""

    clean = (ref or "").strip()
    if not clean.startswith("e") or not clean[1:].isdigit():
        return {}
    return await page.evaluate(
        """(ref) => {
            const el = document.querySelector('[data-lk-ref="' + ref + '"]');
            if (!el) return {};
            return {
              tag: el.tagName.toLowerCase(),
              type: (el.getAttribute('type') || '').toLowerCase(),
              text: (el.innerText || el.value || el.getAttribute('aria-label') || '')
                .replace(/\\s+/g, ' ').trim().slice(0, 120),
            };
        }""",
        clean,
    )

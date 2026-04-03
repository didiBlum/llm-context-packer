"""HTML → semantic markdown. Strips boilerplate, extracts content + metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md


@dataclass
class CleanResult:
    markdown: str
    title: str
    description: str


# CSS selectors for boilerplate elements to remove
_BOILERPLATE_SELECTORS = [
    "nav", "footer", "header",
    "[role='navigation']", "[role='banner']", "[role='contentinfo']",
    ".sidebar", ".ad", ".advertisement", ".social-share",
    ".cookie-banner", ".popup", ".modal", ".newsletter-signup",
    "#comments", ".comments-section", ".comment-form",
    ".breadcrumb", ".pagination",
    "[class*='share']", "[class*='social']",
    "[class*='cookie']", "[class*='newsletter']",
    "[class*='popup']", "[class*='modal']",
    "[class*='advert']", "[class*='sponsor']",
    "[id*='sidebar']", "[id*='footer']",
]

# Elements that are always noise
_REMOVE_TAGS = ["script", "style", "noscript", "iframe", "svg", "object", "embed"]


def clean_html(html: str) -> CleanResult:
    """Convert raw HTML to clean, semantic markdown."""
    soup = BeautifulSoup(html, "html.parser")

    # Extract metadata before cleaning
    title = _extract_title(soup)
    description = _extract_description(soup)

    # Remove noise tags
    for tag_name in _REMOVE_TAGS:
        for el in soup.find_all(tag_name):
            el.decompose()

    # Remove boilerplate by CSS selector
    for selector in _BOILERPLATE_SELECTORS:
        for el in soup.select(selector):
            el.decompose()

    # Find the content node
    content_node = _find_content_node(soup)

    # Strip images, keep alt text
    for img in content_node.find_all("img"):
        alt = img.get("alt", "").strip()
        if alt:
            img.replace_with(f"[Image: {alt}]")
        else:
            img.decompose()

    # Convert to markdown
    raw_md = md(
        str(content_node),
        heading_style="ATX",
        bullets="-",
        code_language_callback=_detect_code_lang,
        strip=["a"] if False else [],  # keep links
    )

    # Post-process markdown
    cleaned = _post_process_markdown(raw_md)

    return CleanResult(markdown=cleaned, title=title, description=description)


def _find_content_node(soup: BeautifulSoup) -> Tag:
    """Find the main content node using semantic tags + text density scoring."""
    # Try semantic elements first
    for selector in ["article", "main", "[role='main']", ".post-content", ".entry-content", ".article-body"]:
        node = soup.select_one(selector)
        if node and len(node.get_text(strip=True)) > 200:
            return node

    # Fallback: score divs by text density
    best_node = soup.body or soup
    best_score = 0

    for div in soup.find_all("div"):
        text = div.get_text(strip=True)
        if len(text) < 200:
            continue

        html_len = len(str(div))
        if html_len == 0:
            continue

        # Text density = ratio of text to HTML
        density = len(text) / html_len
        # Bonus for longer content
        score = density * min(len(text), 10000)

        if score > best_score:
            best_score = score
            best_node = div

    return best_node


def _extract_title(soup: BeautifulSoup) -> str:
    """Extract page title from meta, og:title, or <title> tag."""
    # Open Graph title (usually most accurate)
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()

    # <title> tag
    if soup.title and soup.title.string:
        return soup.title.string.strip()

    # First h1
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)

    return ""


def _extract_description(soup: BeautifulSoup) -> str:
    """Extract page description from meta tags."""
    for attr in [{"name": "description"}, {"property": "og:description"}]:
        tag = soup.find("meta", attrs=attr)
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def _detect_code_lang(el) -> str | None:
    """Try to detect code language from class attributes."""
    classes = el.get("class", []) if hasattr(el, "get") else []
    for cls in classes:
        if isinstance(cls, str):
            if cls.startswith("language-"):
                return cls[9:]
            if cls.startswith("lang-"):
                return cls[5:]
            if cls.startswith("highlight-"):
                return cls[10:]
    return None


def _post_process_markdown(text: str) -> str:
    """Clean up markdown artifacts."""
    # Collapse multiple blank lines to one
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove lines that are just whitespace
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)

    # Remove leading/trailing whitespace
    text = text.strip()

    return text

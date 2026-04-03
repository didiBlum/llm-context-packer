"""3-tier semantic compression: structural → linguistic → aggressive."""

from __future__ import annotations

import re

# ── Structural compression (always applied) ──────────────────────────────

_FILLER_SECTIONS_RE = re.compile(
    r"^#{1,3}\s*(Table of Contents|Contents|Share This|Related Posts|"
    r"Related Articles|Share on|Follow Us|About the Author|"
    r"Leave a Comment|Comments|Subscribe|Newsletter).*?(?=^#{1,3}\s|\Z)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

_ATTRIBUTION_RE = re.compile(
    r"^(?:Photo|Image|Credit|Source|Via|Originally published).*$",
    re.MULTILINE | re.IGNORECASE,
)

_HR_RE = re.compile(r"^[\s]*[-*_]{3,}[\s]*$", re.MULTILINE)


def structural_compress(text: str) -> str:
    """Remove structural noise: ToC, sharing sections, attribution, HRs."""
    text = _FILLER_SECTIONS_RE.sub("", text)
    text = _ATTRIBUTION_RE.sub("", text)
    text = _HR_RE.sub("", text)

    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Normalize unicode whitespace
    text = text.replace("\u00a0", " ")  # non-breaking space
    text = text.replace("\u2003", " ")  # em space
    text = text.replace("\u2002", " ")  # en space

    # Normalize smart quotes to ASCII
    for smart, plain in [("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"')]:
        text = text.replace(smart, plain)

    return text.strip()


# ── Linguistic compression ───────────────────────────────────────────────

_HEDGE_PHRASES = [
    "it is worth noting that ",
    "it's worth noting that ",
    "it should be noted that ",
    "as we all know, ",
    "as you may know, ",
    "in this article, we will ",
    "in this post, we will ",
    "in this guide, we will ",
    "let's take a look at ",
    "let's dive into ",
    "let's explore ",
    "without further ado, ",
    "as mentioned earlier, ",
    "as discussed above, ",
    "needless to say, ",
    "it goes without saying that ",
    "at the end of the day, ",
    "when all is said and done, ",
]

_TRANSITION_WORDS = [
    "Furthermore, ",
    "Moreover, ",
    "Additionally, ",
    "In addition, ",
    "Consequently, ",
    "Subsequently, ",
    "Nevertheless, ",
    "Nonetheless, ",
    "Accordingly, ",
    "Henceforth, ",
]

# Regex for detecting "information-dense" tokens
_TECHNICAL_TOKEN_RE = re.compile(
    r"[A-Z][a-z]+[A-Z]"  # camelCase
    r"|[a-z]+_[a-z]+"     # snake_case
    r"|\d+\.?\d*"         # numbers
    r"|https?://\S+"      # URLs
    r"|`[^`]+`"           # inline code
    r"|[A-Z]{2,}"         # acronyms
)


def linguistic_compress(text: str) -> str:
    """Remove filler sentences and hedging phrases."""
    # Remove hedging phrases
    lower = text
    for phrase in _HEDGE_PHRASES:
        # Case-insensitive removal, preserving the rest of the sentence
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        lower = pattern.sub("", lower)
    text = lower

    # Remove transition words at sentence starts
    for word in _TRANSITION_WORDS:
        text = text.replace(word, "")
        text = text.replace(word.lower(), "")

    # Remove low-information-density sentences
    lines = text.split("\n")
    result = []
    for line in lines:
        # Skip empty or very short lines
        if not line.strip():
            result.append(line)
            continue

        # Don't touch headings, code blocks, or list items
        stripped = line.strip()
        if stripped.startswith(("#", "-", "*", ">", "`", "|", "1.", "2.", "3.")):
            result.append(line)
            continue

        # Score sentence by information density
        words = stripped.split()
        if len(words) > 12:
            technical_matches = len(_TECHNICAL_TOKEN_RE.findall(stripped))
            density = technical_matches / len(words) if words else 0

            if density < 0.03 and len(words) > 15:
                # Low-density filler sentence — skip it
                continue

        result.append(line)

    text = "\n".join(result)

    # Deduplicate near-identical lines
    text = _dedup_lines(text)

    return text.strip()


def _dedup_lines(text: str) -> str:
    """Remove near-duplicate lines (Jaccard similarity > 0.8)."""
    lines = text.split("\n")
    seen_word_sets: list[set[str]] = []
    result = []

    for line in lines:
        words = set(line.lower().split())
        if len(words) < 5:
            result.append(line)
            seen_word_sets.append(words)
            continue

        is_dup = False
        for seen in seen_word_sets:
            if not seen:
                continue
            intersection = words & seen
            union = words | seen
            if union and len(intersection) / len(union) > 0.8:
                is_dup = True
                break

        if not is_dup:
            result.append(line)
            seen_word_sets.append(words)

    return "\n".join(result)


# ── Aggressive compression ───────────────────────────────────────────────

def aggressive_compress(text: str) -> str:
    """Heavy compression: summarize lists, prune examples, trim quotes."""
    lines = text.split("\n")
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Compress long lists: if >8 consecutive list items, keep first 3 + last 1
        if _is_list_item(line):
            list_items = []
            while i < len(lines) and _is_list_item(lines[i]):
                list_items.append(lines[i])
                i += 1

            if len(list_items) > 8:
                result.extend(list_items[:3])
                result.append(f"- ... ({len(list_items) - 4} more items)")
                result.append(list_items[-1])
            else:
                result.extend(list_items)
            continue

        # Truncate long blockquotes to first sentence
        if line.strip().startswith(">") and len(line) > 200:
            first_sentence_end = line.find(". ", 2)
            if first_sentence_end > 0:
                line = line[: first_sentence_end + 1] + ' [...]"'

        # Remove "for example" repetitions after the first
        if re.match(r"(?:for example|for instance|e\.g\.|another example)", line.strip(), re.I):
            # Check if we already have an example in recent lines
            recent = "\n".join(result[-5:]).lower()
            if "for example" in recent or "for instance" in recent or "e.g." in recent:
                i += 1
                continue

        # Remove long parenthetical asides
        line = re.sub(r"\([^)]{80,}\)", "(...)", line)

        result.append(line)
        i += 1

    return "\n".join(result).strip()


def _is_list_item(line: str) -> bool:
    stripped = line.strip()
    return bool(
        stripped.startswith("- ")
        or stripped.startswith("* ")
        or re.match(r"^\d+\.\s", stripped)
    )


# ── Pipeline composition ─────────────────────────────────────────────────

COMPRESSION_PIPELINES: dict[str, list] = {
    "speed": [structural_compress],
    "quality": [structural_compress, linguistic_compress],
    "compression": [structural_compress, linguistic_compress, aggressive_compress],
}


def compress(text: str, priority: str = "quality") -> str:
    """Run the compression pipeline for the given priority."""
    pipeline = COMPRESSION_PIPELINES.get(priority, COMPRESSION_PIPELINES["quality"])
    for step in pipeline:
        text = step(text)
    return text

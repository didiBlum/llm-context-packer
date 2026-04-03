"""Token budget allocation and intelligent truncation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.pipeline.tokenizer import count_tokens
from app.pipeline.compressor import compress


@dataclass
class BudgetResult:
    content: str
    token_count: int
    was_truncated: bool


def fit_to_budget(
    content: str,
    max_tokens: int | None,
    model: str = "gpt-4o",
    priority: str = "quality",
) -> BudgetResult:
    """Fit content to a token budget, compressing/truncating as needed."""
    if max_tokens is None:
        tokens = count_tokens(content, model)
        return BudgetResult(content=content, token_count=tokens, was_truncated=False)

    tokens = count_tokens(content, model)

    # Fits already
    if tokens <= max_tokens:
        return BudgetResult(content=content, token_count=tokens, was_truncated=False)

    # Try escalating compression if not already at max
    if priority != "compression":
        compressed = compress(content, "compression")
        tokens = count_tokens(compressed, model)
        if tokens <= max_tokens:
            return BudgetResult(content=compressed, token_count=tokens, was_truncated=False)
        content = compressed

    # Intelligent truncation by sections
    truncated = _truncate_by_sections(content, max_tokens, model)
    tokens = count_tokens(truncated, model)
    return BudgetResult(content=truncated, token_count=tokens, was_truncated=True)


def allocate_budgets(
    token_counts: list[int],
    total_budget: int,
    min_per_url: int = 200,
) -> list[int | None]:
    """Allocate token budget proportionally across multiple URLs.

    Returns a list of budgets. None means the URL was dropped (couldn't meet minimum).
    """
    total_tokens = sum(token_counts)
    if total_tokens == 0:
        return [total_budget // len(token_counts)] * len(token_counts)

    n = len(token_counts)
    budgets: list[int | None] = [None] * n

    # Check if everything fits without budget
    if total_tokens <= total_budget:
        return [None] * n  # None = no budget constraint needed

    # Proportional allocation
    for i, tc in enumerate(token_counts):
        allocated = int(total_budget * (tc / total_tokens))
        if allocated < min_per_url:
            budgets[i] = None  # will be dropped
        else:
            budgets[i] = allocated

    # Redistribute budget from dropped URLs
    active = [(i, budgets[i]) for i in range(n) if budgets[i] is not None]
    if not active:
        # All dropped — give everything to the largest
        largest_idx = token_counts.index(max(token_counts))
        budgets[largest_idx] = total_budget
        return budgets

    dropped_budget = sum(
        int(total_budget * (token_counts[i] / total_tokens))
        for i in range(n)
        if budgets[i] is None
    )

    if dropped_budget > 0:
        active_total = sum(b for _, b in active if b)
        for i, b in active:
            if b and active_total > 0:
                budgets[i] = b + int(dropped_budget * (b / active_total))

    return budgets


def _truncate_by_sections(text: str, max_tokens: int, model: str) -> str:
    """Split by headings, score sections, include best ones within budget."""
    sections = _split_into_sections(text)

    if not sections:
        # No headings — simple token-based truncation
        return _simple_truncate(text, max_tokens, model)

    # Score each section
    scored = []
    for i, (heading, body) in enumerate(sections):
        score = _score_section(body, is_first=(i == 0))
        tokens = count_tokens(heading + "\n" + body, model)
        scored.append((score, i, heading, body, tokens))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Greedily include sections within budget, respecting original order
    selected_indices = set()
    remaining = max_tokens - 50  # reserve for truncation notice

    for score, idx, heading, body, tokens in scored:
        if tokens <= remaining:
            selected_indices.add(idx)
            remaining -= tokens

    # Rebuild in original order
    result_parts = []
    for i, (heading, body) in enumerate(sections):
        if i in selected_indices:
            result_parts.append(heading + "\n" + body if heading else body)

    result = "\n\n".join(result_parts)

    original_tokens = count_tokens(text, model)
    result += f"\n\n[Content truncated. Original: {original_tokens} tokens, showing: {max_tokens - remaining} tokens]"

    return result


def _split_into_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown by headings into (heading, body) pairs."""
    lines = text.split("\n")
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_body: list[str] = []

    for line in lines:
        if re.match(r"^#{1,4}\s", line):
            if current_heading or current_body:
                sections.append((current_heading, "\n".join(current_body).strip()))
            current_heading = line
            current_body = []
        else:
            current_body.append(line)

    # Last section
    if current_heading or current_body:
        sections.append((current_heading, "\n".join(current_body).strip()))

    return sections


def _score_section(body: str, is_first: bool = False) -> float:
    """Score a section by information density. Higher = more important."""
    score = 0.0

    # First section (intro) always gets a bonus
    if is_first:
        score += 50

    # Code blocks are high-value
    score += body.count("```") * 20

    # Numbers and data points
    score += len(re.findall(r"\d+\.?\d*", body)) * 2

    # Technical terms (camelCase, snake_case, URLs)
    score += len(re.findall(r"[A-Z][a-z]+[A-Z]|[a-z]+_[a-z]+|https?://", body)) * 3

    # Length contributes but with diminishing returns
    words = len(body.split())
    score += min(words, 200) * 0.1

    return score


def _simple_truncate(text: str, max_tokens: int, model: str) -> str:
    """Fallback: truncate by words when there are no heading-based sections."""
    words = text.split()
    # Binary search for the right word count
    lo, hi = 0, len(words)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        candidate = " ".join(words[:mid])
        if count_tokens(candidate, model) <= max_tokens - 30:
            lo = mid
        else:
            hi = mid - 1

    result = " ".join(words[:lo])
    original_tokens = count_tokens(text, model)
    result += f"\n\n[Truncated. Original: {original_tokens} tokens]"
    return result

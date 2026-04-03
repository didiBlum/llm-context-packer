"""Tiktoken wrapper with cached encoding objects."""

from __future__ import annotations

import tiktoken

# Cache encoding objects — they're expensive to instantiate
_encodings: dict[str, tiktoken.Encoding] = {}

# Map model names to tiktoken encoding names
_MODEL_ENCODING_MAP: dict[str, str] = {
    "gpt-4o": "o200k_base",
    "gpt-4o-mini": "o200k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-4": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    # Non-OpenAI models: cl100k_base is a reasonable approximation (~5-10% variance)
    "claude-3": "cl100k_base",
    "claude-4": "cl100k_base",
    "gemini": "cl100k_base",
}

_DEFAULT_ENCODING = "cl100k_base"


def _get_encoding(model: str) -> tiktoken.Encoding:
    encoding_name = _MODEL_ENCODING_MAP.get(model, _DEFAULT_ENCODING)
    if encoding_name not in _encodings:
        _encodings[encoding_name] = tiktoken.get_encoding(encoding_name)
    return _encodings[encoding_name]


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count tokens for the given text using the model's tokenizer."""
    return len(_get_encoding(model).encode(text))


def is_exact_model(model: str) -> bool:
    """Whether token count is exact (OpenAI) or approximate (other models)."""
    return model in _MODEL_ENCODING_MAP and "claude" not in model and "gemini" not in model

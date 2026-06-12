"""The single Anthropic call site.

Everything that talks to Claude goes through here so the model id, adaptive thinking,
prompt caching, and structured-output conventions live in one place (see CLAUDE.md).

Conventions (from the /claude-api skill):
- model ``claude-opus-4-8``
- adaptive thinking: ``thinking={"type": "adaptive"}`` (never ``budget_tokens``)
- cache the stable schema/glossary/few-shot prefix with ``cache_control={"type":"ephemeral"}``
- strict JSON via ``output_config={"format": {"type": "json_schema", ...}}`` (sent through
  ``extra_body`` so it works regardless of the installed SDK's typed params)
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import anthropic

from . import config

# Keep individual calls snappy for an interactive CLI; correctness here comes from the
# verifier + executor, not from maximal thinking depth.
_EFFORT = "medium"


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return anthropic.Anthropic()


def _text(response: Any) -> str:
    """Concatenate the text blocks of a message response (skip thinking blocks)."""
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text")


def complete(
    system: list[dict] | str,
    user: str,
    *,
    max_tokens: int = 1500,
    json_schema: dict | None = None,
) -> str | dict:
    """One Claude turn.

    Args:
        system: cached system blocks (list of ``{"type":"text", ...}``) or a plain string.
        user: the user message.
        max_tokens: output cap.
        json_schema: if given, constrain output to this JSON schema and return a parsed dict.

    Returns:
        Parsed dict when ``json_schema`` is set, else the response text.
    """
    output_config: dict[str, Any] = {"effort": _EFFORT}
    if json_schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": json_schema}

    response = _client().messages.create(
        model=config.MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": user}],
        extra_body={"output_config": output_config},
    )

    text = _text(response).strip()
    if json_schema is None:
        return text
    return json.loads(text)


def cached_system(blocks: list[str], *, cache_last: bool = True) -> list[dict]:
    """Build system blocks, caching the stable prefix.

    The final block carries ``cache_control`` so the whole (large, stable) prefix is cached
    and reused across requests.
    """
    out: list[dict] = []
    for i, text in enumerate(blocks):
        block: dict[str, Any] = {"type": "text", "text": text}
        if cache_last and i == len(blocks) - 1:
            block["cache_control"] = {"type": "ephemeral"}
        out.append(block)
    return out

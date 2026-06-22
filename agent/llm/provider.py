"""
Unified LLM provider — supports OpenAI and Anthropic.
Set LLM_PROVIDER=openai or LLM_PROVIDER=anthropic in .env.
Defaults to openai if OPENAI_API_KEY is set, otherwise anthropic.
"""

import os
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    tokens_used: int
    model: str


def get_provider() -> str:
    explicit = os.getenv("LLM_PROVIDER", "").lower()
    if explicit in ("openai", "anthropic"):
        return explicit
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    raise RuntimeError(
        "No LLM provider configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env"
    )


def complete(
    system: str,
    user: str,
    max_tokens: int = 2048,
    fast: bool = False,        # fast=True uses cheaper/faster model (for synthesis)
) -> LLMResponse:
    """
    Single entry point for all LLM calls across the agent.
    fast=True → use smaller model (gpt-4o-mini / haiku)
    fast=False → use capable model (gpt-4o / sonnet)
    """
    provider = get_provider()
    if provider == "openai":
        return _openai_complete(system, user, max_tokens, fast)
    return _anthropic_complete(system, user, max_tokens, fast)


# --- OpenAI ---

_openai_client = None

OPENAI_CAPABLE = "gpt-4o"
OPENAI_FAST    = "gpt-4o-mini"


def _get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    return _openai_client


def _openai_complete(system: str, user: str, max_tokens: int, fast: bool) -> LLMResponse:
    model = OPENAI_FAST if fast else OPENAI_CAPABLE
    client = _get_openai()
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    text   = response.choices[0].message.content or ""
    tokens = response.usage.total_tokens if response.usage else 0
    return LLMResponse(text=text.strip(), tokens_used=tokens, model=model)


# --- Anthropic ---

_anthropic_client = None

ANTHROPIC_CAPABLE = "claude-sonnet-4-6"
ANTHROPIC_FAST    = "claude-haiku-4-5-20251001"


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    return _anthropic_client


def _anthropic_complete(system: str, user: str, max_tokens: int, fast: bool) -> LLMResponse:
    model = ANTHROPIC_FAST if fast else ANTHROPIC_CAPABLE
    client = _get_anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text   = response.content[0].text
    tokens = response.usage.input_tokens + response.usage.output_tokens
    return LLMResponse(text=text.strip(), tokens_used=tokens, model=model)

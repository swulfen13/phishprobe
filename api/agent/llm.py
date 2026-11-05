"""The single choke point for LLM calls. Every model call in PhishProbe goes
through here, and it only ever talks to Vultr Serverless Inference (an
OpenAI-compatible endpoint). The API key lives in this process's environment
and is never exposed to a sandbox container.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from openai import AsyncOpenAI


class LLMUnavailable(RuntimeError):
    """Raised when no Vultr key is configured — callers degrade gracefully."""


_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    key = os.getenv("VULTR_INFERENCE_API_KEY", "").strip()
    if not key or key.startswith("your-"):
        raise LLMUnavailable("VULTR_INFERENCE_API_KEY is not set")
    if _client is None:
        base_url = os.getenv("VULTR_INFERENCE_BASE_URL", "https://api.vultrinference.com/v1").strip()
        _client = AsyncOpenAI(api_key=key, base_url=base_url, timeout=60.0, max_retries=1)
    return _client


def is_configured() -> bool:
    try:
        _get_client()
        return True
    except LLMUnavailable:
        return False


def model_text() -> str:
    return os.getenv("MODEL_TEXT", "llama-3.3-70b-instruct").strip()


def model_vision() -> str:
    return os.getenv("MODEL_VISION", "qwen2.5-vl-72b-instruct").strip()


async def chat_json(
    *,
    model: str,
    system: str,
    user_content: Any,
    max_tokens: int = 900,
    temperature: float = 0.1,
) -> dict:
    """Call the model and parse its reply as JSON.

    `user_content` is either a string or an OpenAI-style content array (for
    vision). Raises on transport errors; raises ValueError if the reply is not
    valid JSON so the caller can retry once.
    """
    client = _get_client()
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    text = resp.choices[0].message.content or ""
    return _parse_json(text)


def _parse_json(text: str) -> dict:
    text = text.strip()
    # Some models wrap JSON in ```json fences despite json_object mode.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            return json.loads(text[start : end + 1])
        raise ValueError(f"model did not return JSON: {text[:200]!r}")

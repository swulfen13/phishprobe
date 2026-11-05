"""Allowed action schema and the strict verdict format.

The LLM may only ever return a `Verdict`. The agent may only ever ask the
sandbox for an action from `AllowedAction`. Anything else is rejected — the
page content can never widen what the agent is permitted to do.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class AllowedAction(str, Enum):
    """The only actions the orchestrator will send to the sandbox."""

    SCAN = "scan"
    SUBMIT_FAKE = "submit_fake"  # only after explicit human approval


Severity = Literal["low", "medium", "high"]
VerdictLevel = Literal["safe", "suspicious", "phishing"]


class Signal(BaseModel):
    type: str = Field(max_length=60)
    detail: str = Field(max_length=400)
    severity: Severity = "low"


class Verdict(BaseModel):
    verdict: VerdictLevel
    risk_score: int = Field(ge=0, le=100)
    impersonated_brand: Optional[str] = None
    signals: list[Signal] = Field(default_factory=list)
    explanation_de: str = ""
    explanation_en: str = ""

    @field_validator("impersonated_brand", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str) and v.strip().lower() in ("", "null", "none", "n/a"):
            return None
        return v


class VisionResult(BaseModel):
    """Structured output of the screenshot analysis."""

    impersonated_brand: Optional[str] = None
    looks_like_login: bool = False
    looks_like_payment: bool = False
    description_en: str = ""

    @field_validator("impersonated_brand", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str) and v.strip().lower() in ("", "null", "none", "n/a", "unknown"):
            return None
        return v

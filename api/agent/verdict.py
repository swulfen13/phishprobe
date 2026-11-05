"""Verdict engine: turn raw observations + LLM analysis into the final,
schema-validated verdict. Deterministic signals set hard floors so a page can
never talk the model out of an obvious red flag (prompt-injection defence).
"""

from __future__ import annotations

from pydantic import ValidationError

from . import llm, prompts
from .actions import Signal, Verdict, VisionResult


def collect_deterministic_signals(quick: dict, scan: dict) -> list[dict]:
    """Signals we assert ourselves, regardless of what the model says."""
    signals: list[dict] = list(quick.get("signals", []))
    dom = scan.get("dom_summary", {}) or {}

    if dom.get("password_field_count", 0) > 0:
        signals.append({"type": "password_form", "detail": "Page contains a password field", "severity": "medium"})
    if dom.get("has_card_field"):
        signals.append({"type": "card_form", "detail": "Page asks for card / payment details", "severity": "high"})
    if dom.get("external_form_action"):
        signals.append({"type": "external_form", "detail": "A form submits to a different domain than the page", "severity": "high"})

    redirects = scan.get("redirects", []) or []
    if len(redirects) >= 3:
        hops = " -> ".join(r.get("url", "") for r in redirects)
        signals.append({"type": "redirect_chain", "detail": f"{len(redirects)} redirect hops: {hops}"[:380], "severity": "medium"})

    if scan.get("downloads_blocked"):
        signals.append({"type": "auto_download", "detail": "Page tried to trigger a file download (blocked)", "severity": "high"})

    if dom.get("injection_matches"):
        signals.append({
            "type": "prompt_injection",
            "detail": "Page contains text aimed at manipulating an AI reviewer: " + ", ".join(dom["injection_matches"][:5]),
            "severity": "high",
        })

    for ev in scan.get("containment_events", []) or []:
        if ev.get("type") == "blocked_internal_ip":
            signals.append({"type": "ssrf_attempt", "detail": ev.get("detail", "request to internal address blocked"), "severity": "high"})

    return signals


async def run_vision(scan: dict) -> VisionResult | None:
    """Analyse the desktop screenshot with the Vultr vision model."""
    if not llm.is_configured():
        return None
    shot = scan.get("screenshot_desktop_b64") or scan.get("screenshot_mobile_b64")
    if not shot:
        return None
    content = [
        {"type": "text", "text": "Analyse this page screenshot. Return the JSON described in the system prompt."},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{shot}"}},
    ]
    try:
        data = await llm.chat_json(
            model=llm.model_vision(),
            system=prompts.VISION_SYSTEM,
            user_content=content,
            max_tokens=1200,
        )
        return VisionResult.model_validate(data)
    except (ValueError, ValidationError, Exception):
        return None


async def decide(quick: dict, scan: dict, vision: VisionResult | None) -> tuple[Verdict, bool]:
    """Produce the final verdict. Returns (verdict, used_llm)."""
    det_signals = collect_deterministic_signals(quick, scan)
    dom = scan.get("dom_summary", {}) or {}

    context = {
        "final_url": scan.get("final_url") or quick.get("host"),
        "registered_domain": quick.get("registered_domain"),
        "redirects": scan.get("redirects"),
        "requested_domains": scan.get("requested_domains"),
        "forms": dom.get("forms"),
        "has_password_field": dom.get("password_field_count", 0) > 0,
        "has_card_field": dom.get("has_card_field"),
        "external_form_action": dom.get("external_form_action"),
        "title": dom.get("title"),
        "visible_text": dom.get("visible_text"),
        "brand_texts": dom.get("brand_texts"),
        "injection_matches": dom.get("injection_matches"),
        "downloads_blocked": scan.get("downloads_blocked"),
        "console_errors": scan.get("console_errors"),
        "vision": vision.model_dump() if vision else None,
        "deterministic_signals": det_signals,
    }

    verdict = await _llm_verdict(context)
    used_llm = verdict is not None
    if verdict is None:
        verdict = _heuristic_verdict(quick, scan, det_signals, vision)

    verdict = _apply_hard_floors(verdict, det_signals, dom)
    return verdict, used_llm


async def _llm_verdict(context: dict) -> Verdict | None:
    if not llm.is_configured():
        return None
    user_content = prompts.build_verdict_user_content(context)
    for attempt in range(2):
        try:
            data = await llm.chat_json(
                model=llm.model_text(),
                system=prompts.VERDICT_SYSTEM,
                user_content=user_content,
                max_tokens=2000,
            )
            return Verdict.model_validate(data)
        except (ValueError, ValidationError):
            if attempt == 0:
                continue
            return None
        except Exception:
            return None
    return None


def _apply_hard_floors(verdict: Verdict, det_signals: list[dict], dom: dict) -> Verdict:
    """Deterministic signals override an over-optimistic model."""
    # Merge deterministic signals in (dedup by type+detail).
    seen = {(s.type, s.detail) for s in verdict.signals}
    for s in det_signals:
        key = (s["type"], s["detail"])
        if key not in seen:
            try:
                verdict.signals.append(Signal.model_validate(s))
                seen.add(key)
            except ValidationError:
                pass

    # Prompt injection => phishing, no matter what the model concluded.
    if dom.get("injection_matches"):
        verdict.verdict = "phishing"
        verdict.risk_score = max(verdict.risk_score, 90)
        note = "Diese Seite versucht, die KI-Prüfung zu täuschen – ein klares Warnsignal."
        if note not in verdict.explanation_de:
            verdict.explanation_de = (note + " " + verdict.explanation_de).strip()

    # Card field + brand impersonation => at least suspicious.
    if dom.get("has_card_field") and verdict.verdict == "safe":
        verdict.verdict = "suspicious"
        verdict.risk_score = max(verdict.risk_score, 45)

    # Keep score and label roughly consistent.
    if verdict.verdict == "phishing":
        verdict.risk_score = max(verdict.risk_score, 70)
    elif verdict.verdict == "safe":
        verdict.risk_score = min(verdict.risk_score, 29)
    return verdict


def _heuristic_verdict(quick: dict, scan: dict, det_signals: list[dict], vision: VisionResult | None) -> Verdict:
    """Fallback when the LLM is unavailable or keeps returning invalid JSON."""
    from quickcheck.heuristics import level_from_score

    score = sum({"low": 8, "medium": 20, "high": 38}.get(s["severity"], 10) for s in det_signals)
    score = max(0, min(100, score))
    level = level_from_score(score)

    brand = vision.impersonated_brand if vision else None
    de = "Automatische Einschätzung ohne KI-Modell (nur Signal-Heuristik). "
    en = "Automated estimate without the AI model (signal heuristics only). "
    if level == "phishing":
        de += "Mehrere starke Warnsignale gefunden."
        en += "Multiple strong warning signals found."
    elif level == "suspicious":
        de += "Einige Auffälligkeiten gefunden."
        en += "Some irregularities found."
    elif det_signals:
        de += "Nur schwache Hinweise, nichts Eindeutiges – ohne die KI-Analyse ist keine sichere Aussage möglich."
        en += "Only weak hints, nothing conclusive — without the AI analysis no firm statement is possible."
    else:
        de += "Keine Auffälligkeiten in der Schnellprüfung."
        en += "No irregularities in the quick analysis."

    signals = [Signal.model_validate(s) for s in det_signals]
    return Verdict(
        verdict=level,
        risk_score=score,
        impersonated_brand=brand,
        signals=signals,
        explanation_de=de,
        explanation_en=en,
    )

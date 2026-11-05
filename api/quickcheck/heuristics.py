"""Stage 1: fast URL heuristics (<1s, no browser).

Pure string/structure analysis of the URL plus a few well-known lists. Returns
a provisional risk estimate and a list of signals that the deep scan and the
final verdict reuse. Deliberately cheap so the (future) browser extension can
call it on every link.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

import tldextract

# TLDs disproportionately abused by phishing / throwaway campaigns.
SUSPICIOUS_TLDS = {
    "zip", "mov", "xyz", "top", "click", "country", "kim", "work", "gq", "ml",
    "cf", "ga", "tk", "rest", "fit", "live", "link", "monster", "cam", "quest",
    "sbs", "cfd", "lol", "icu", "online", "support", "security",
}

# Common URL shorteners — a shortener hides the real destination.
URL_SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly",
    "cutt.ly", "rb.gy", "shorturl.at", "rebrand.ly", "t.ly", "s.id",
}

# Brand / service words often abused in phishing hostnames (EN + DE).
LURE_WORDS = [
    "secure", "account", "login", "verify", "update", "confirm", "signin",
    "bank", "paypal", "wallet", "delivery", "parcel", "package", "customs",
    "invoice", "payment", "billing", "support", "service", "unlock", "reset",
    # German — the primary target audience receives German-language scams.
    "paket", "zustellung", "verfolgung", "sendung", "zoll", "konto",
    "anmelden", "bestaetigen", "bestatigen", "aktualisieren", "sicherheit",
    "kundenservice", "zahlung", "rechnung", "freischalten",
]

# Characters that look like ASCII letters (homoglyph swaps).
HOMOGLYPHS = {
    "0": "o", "1": "l", "3": "e", "5": "s", "4": "a", "rn": "m", "vv": "w",
}


def _signal(stype: str, detail: str, severity: str) -> dict:
    return {"type": stype, "detail": detail, "severity": severity}


def quick_check(url: str) -> dict:
    """Return {score, level, signals, host, registered_domain, is_shortener}."""
    url = (url or "").strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", url):
        url = "http://" + url  # tolerate pasted bare domains

    signals: list[dict] = []
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    ext = tldextract.extract(host)
    registered_domain = ext.registered_domain or host
    tld = (ext.suffix.split(".")[-1] if ext.suffix else "").lower()

    if not host:
        return {
            "score": 50,
            "level": "suspicious",
            "signals": [_signal("parse", "URL could not be parsed", "medium")],
            "host": "",
            "registered_domain": "",
            "is_shortener": False,
        }

    # IP address instead of a domain name.
    is_ip = False
    try:
        ipaddress.ip_address(host)
        is_ip = True
        signals.append(_signal("ip_host", f"Uses a raw IP address ({host}) instead of a domain", "high"))
    except ValueError:
        pass

    # Punycode / IDN homograph.
    if "xn--" in host:
        signals.append(_signal("punycode", f"Internationalized (punycode) domain: {host}", "high"))

    # Homoglyph digits inside the registered domain label (paypa1, g00gle...).
    label = ext.domain or ""
    if re.search(r"[a-z][0-9]|[0-9][a-z]", label) and any(
        lure in host for lure in LURE_WORDS
    ):
        signals.append(_signal("homoglyph", f"Brand-like label mixes letters and digits: '{label}'", "medium"))

    # Suspicious TLD.
    if tld in SUSPICIOUS_TLDS:
        signals.append(_signal("suspicious_tld", f"Low-trust top-level domain: .{tld}", "medium"))

    # URL shortener.
    is_shortener = registered_domain in URL_SHORTENERS
    if is_shortener:
        signals.append(_signal("shortener", f"URL shortener hides the real destination ({registered_domain})", "medium"))

    # Excessive / lure-y subdomains (dhl-paket.secure-login.example.xyz).
    sub = ext.subdomain or ""
    sub_parts = [p for p in sub.split(".") if p]
    if len(sub_parts) >= 3:
        signals.append(_signal("deep_subdomain", f"Unusually deep subdomain chain ({sub})", "medium"))
    lure_hits = sorted({w for w in LURE_WORDS if w in host})
    if lure_hits and not is_ip:
        # Lure words are only mildly suspicious on their own.
        signals.append(_signal("lure_words", f"Hostname contains lure words: {', '.join(lure_hits)}", "low"))

    # Hyphen-stuffed hostnames (dhl-paket-zustellung-verfolgung).
    if host.count("-") >= 3:
        signals.append(_signal("hyphen_stuffing", f"Many hyphens in hostname ({host.count('-')})", "low"))

    # Very long hostname.
    if len(host) > 40:
        signals.append(_signal("long_host", f"Hostname is unusually long ({len(host)} chars)", "low"))

    # @ in authority or credentials in URL.
    if "@" in (parsed.netloc or ""):
        signals.append(_signal("userinfo", "URL embeds credentials/userinfo before the host (@)", "high"))

    score = _score_from_signals(signals)
    return {
        "score": score,
        "level": level_from_score(score),
        "signals": signals,
        "host": host,
        "registered_domain": registered_domain,
        "is_shortener": is_shortener,
    }


SEVERITY_WEIGHT = {"low": 8, "medium": 20, "high": 38}


def _score_from_signals(signals: list[dict]) -> int:
    score = sum(SEVERITY_WEIGHT.get(s["severity"], 10) for s in signals)
    return max(0, min(100, score))


def level_from_score(score: int) -> str:
    if score >= 65:
        return "phishing"
    if score >= 30:
        return "suspicious"
    return "safe"

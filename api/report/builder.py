"""Standalone, self-contained HTML report for a finished scan. Same-origin
screenshot URLs are embedded; the page is print-styled so the browser's
"Print -> Save as PDF" produces a real, shareable PDF with zero server-side
PDF dependencies.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

VERDICT_META = {
    "safe": ("🟢", "Keine Auffälligkeiten", "#15803d"),
    "suspicious": ("🟡", "Verdächtig", "#b45309"),
    "phishing": ("🔴", "Phishing / gefährlich", "#b91c1c"),
}
SEVERITY_COLOR = {"low": "#64748b", "medium": "#b45309", "high": "#b91c1c"}


def _esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def build_report_html(scan: dict) -> str:
    verdict = scan.get("verdict") or {}
    level = verdict.get("verdict", "suspicious")
    emoji, label, color = VERDICT_META.get(level, VERDICT_META["suspicious"])
    score = verdict.get("risk_score", 0)
    brand = verdict.get("impersonated_brand")
    scan_data = scan.get("scan_data") or {}
    created = datetime.fromtimestamp(scan.get("created_at", 0), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    signals_html = "".join(
        f'<li><span class="sev" style="background:{SEVERITY_COLOR.get(s.get("severity","low"),"#64748b")}">'
        f'{_esc(s.get("severity","low"))}</span> <strong>{_esc(s.get("type"))}</strong>: {_esc(s.get("detail"))}</li>'
        for s in verdict.get("signals", [])
    ) or "<li>Keine Signale erfasst.</li>"

    redirects = scan_data.get("redirects", [])
    redirect_html = "".join(
        f'<li><code>{_esc(r.get("status"))}</code> {_esc(r.get("url"))}</li>' for r in redirects
    ) or "<li>Keine Weiterleitungen.</li>"

    containment = scan_data.get("containment_events", [])
    containment_html = "".join(
        f'<li><strong>{_esc(c.get("type"))}</strong>: {_esc(c.get("detail"))}</li>' for c in containment
    ) or "<li>Keine Containment-Ereignisse.</li>"

    domains = scan_data.get("requested_domains", [])
    domains_html = ", ".join(_esc(d) for d in domains[:30]) or "–"

    desktop = scan_data.get("screenshot_desktop_path")
    mobile = scan_data.get("screenshot_mobile_path")
    shots = ""
    if desktop:
        shots += f'<figure><img src="{_esc(desktop)}" alt="Desktop-Screenshot"><figcaption>Desktop</figcaption></figure>'
    if mobile:
        shots += f'<figure><img src="{_esc(mobile)}" alt="Mobile-Screenshot"><figcaption>Mobile</figcaption></figure>'

    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PhishProbe Report – {_esc(scan.get('url'))}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ font: 15px/1.6 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; color:#0f172a; margin:0; background:#f8fafc; }}
  .wrap {{ max-width: 820px; margin: 0 auto; padding: 32px 20px 64px; }}
  header.brand {{ display:flex; align-items:center; gap:10px; font-weight:700; letter-spacing:-.02em; margin-bottom:24px; }}
  .verdict {{ border:1px solid #e2e8f0; border-radius:16px; background:#fff; padding:24px; display:flex; gap:20px; align-items:center; }}
  .verdict .emoji {{ font-size:48px; }}
  .verdict h1 {{ margin:0; font-size:24px; color:{color}; }}
  .score {{ margin-left:auto; text-align:center; }}
  .score b {{ font-size:34px; color:{color}; }}
  section {{ background:#fff; border:1px solid #e2e8f0; border-radius:16px; padding:20px 24px; margin-top:20px; }}
  h2 {{ font-size:16px; margin:0 0 12px; }}
  ul {{ margin:0; padding-left:0; list-style:none; }}
  li {{ padding:6px 0; border-bottom:1px solid #f1f5f9; }}
  li:last-child {{ border-bottom:none; }}
  .sev {{ color:#fff; font-size:11px; padding:2px 7px; border-radius:999px; text-transform:uppercase; }}
  code {{ background:#f1f5f9; padding:1px 6px; border-radius:6px; font-size:13px; }}
  figure {{ margin:0; }}
  .shots {{ display:flex; gap:16px; flex-wrap:wrap; }}
  .shots img {{ max-width:360px; width:100%; border:1px solid #e2e8f0; border-radius:10px; }}
  figcaption {{ font-size:13px; color:#64748b; margin-top:6px; }}
  .meta {{ color:#64748b; font-size:13px; }}
  .disclaimer {{ font-size:12px; color:#64748b; margin-top:28px; }}
  @media print {{ body {{ background:#fff; }} section, .verdict {{ break-inside: avoid; }} }}
</style></head>
<body><div class="wrap">
  <header class="brand">🛡️ PhishProbe</header>
  <div class="verdict">
    <div class="emoji">{emoji}</div>
    <div>
      <h1>{_esc(label)}</h1>
      <div class="meta">Geprüft: <code>{_esc(scan.get('url'))}</code></div>
      {f'<div class="meta">Imitiert vermutlich: <strong>{_esc(brand)}</strong></div>' if brand else ''}
    </div>
    <div class="score"><div class="meta">Risiko</div><b>{_esc(score)}</b><div class="meta">/ 100</div></div>
  </div>

  <section><h2>Erklärung</h2><p>{_esc(verdict.get('explanation_de'))}</p>
  <p class="meta">{_esc(verdict.get('explanation_en'))}</p></section>

  <section><h2>Gefundene Signale</h2><ul>{signals_html}</ul></section>

  {f'<section><h2>Screenshots</h2><div class="shots">{shots}</div></section>' if shots else ''}

  <section><h2>Weiterleitungskette</h2><ul>{redirect_html}</ul></section>

  <section><h2>Containment-Ereignisse</h2><ul>{containment_html}</ul>
  <p class="meta">Angefragte Domains: {domains_html}</p></section>

  <p class="meta">Scan-ID: {_esc(scan.get('id'))} · {created}</p>
  <p class="disclaimer">PhishProbe ist ein Hilfsmittel und gibt keine Sicherheitsgarantie.
  „Keine Auffälligkeiten" bedeutet nicht „garantiert sicher". Demo-Seiten in der
  Präsentation nutzen eine frei erfundene Marke.</p>
</div></body></html>"""

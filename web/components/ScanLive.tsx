"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  API_BASE,
  approveScan,
  cancelScan,
  getScan,
  reportUrl,
  subscribeEvents,
  type QuickResult,
  type ScanEvent,
  type Signal,
  type Verdict,
} from "@/lib/api";
import VerdictBadge from "@/components/VerdictBadge";
import SignalList from "@/components/SignalList";

interface Redirect {
  url: string;
  status: number;
}
interface Containment {
  type: string;
  detail: string;
}

export default function ScanLive({ id }: { id: string }) {
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState("Lade …");
  const [quick, setQuick] = useState<QuickResult | null>(null);
  const [redirects, setRedirects] = useState<Redirect[]>([]);
  const [domains, setDomains] = useState<string[]>([]);
  const [containment, setContainment] = useState<Containment[]>([]);
  const [shots, setShots] = useState<{ desktop?: string; mobile?: string }>({});
  const [vision, setVision] = useState<any>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [approval, setApproval] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    let unsub = () => {};
    (async () => {
      try {
        const rec = await getScan(id);
        setUrl(rec.url);
        setQuick(rec.quick_result);
        if (rec.scan_data?.redirects) setRedirects(rec.scan_data.redirects);
        if (rec.verdict) setVerdict(rec.verdict);
        if (rec.status === "done" || rec.status === "cancelled" || rec.status === "error") {
          setDone(true);
          if (rec.scan_data) hydrateFromScanData(rec.scan_data);
          return; // nothing live to stream
        }
      } catch {
        setNotFound(true);
        return;
      }

      unsub = subscribeEvents(id, onEvent, () => setStatus("Verbindung unterbrochen – lade die Seite neu."));
    })();

    return () => unsub();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  function hydrateFromScanData(sd: any) {
    if (sd.requested_domains) setDomains(sd.requested_domains);
    if (sd.containment_events) setContainment(sd.containment_events);
    const s: { desktop?: string; mobile?: string } = {};
    if (sd.screenshot_desktop_path) s.desktop = sd.screenshot_desktop_path;
    if (sd.screenshot_mobile_path) s.mobile = sd.screenshot_mobile_path;
    setShots(s);
  }

  function onEvent(e: ScanEvent) {
    switch (e.type) {
      case "status":
        if (e.payload.message) setStatus(e.payload.message);
        break;
      case "redirects":
        setRedirects(e.payload.redirects || []);
        break;
      case "network":
        setDomains(e.payload.requested_domains || []);
        break;
      case "containment":
        setContainment((c) => [...c, e.payload]);
        break;
      case "screenshots":
        setShots({ desktop: e.payload.desktop, mobile: e.payload.mobile });
        break;
      case "vision":
        setVision(e.payload);
        break;
      case "signals":
        setSignals(e.payload.signals || []);
        break;
      case "approval_request":
        setApproval(e.payload.message);
        break;
      case "approval_result":
        setApproval(null);
        setStatus(e.payload.message);
        break;
      case "verdict":
        setVerdict(e.payload);
        break;
      case "error":
        setStatus("Fehler: " + e.payload.message);
        break;
      case "done":
        setDone(true);
        break;
    }
  }

  async function decide(approved: boolean) {
    setApproval(null);
    await approveScan(id, approved);
  }

  const shownSignals = verdict?.signals?.length ? verdict.signals : signals;

  if (notFound) {
    return (
      <main className="text-center">
        <p className="text-slate-400">Dieser Scan wurde nicht gefunden.</p>
        <a href="/" className="mt-4 inline-block text-sky-400 hover:underline">← Neuen Link prüfen</a>
      </main>
    );
  }

  return (
    <main className="space-y-6">
      <div className="flex items-center gap-3">
        <a href="/" className="text-sm text-sky-400 hover:underline">← Neuer Scan</a>
        <p className="ml-auto truncate font-mono text-xs text-slate-500" title={url}>{url}</p>
      </div>

      {/* Live status / progress */}
      {!done && (
        <div className="flex items-center gap-3 rounded-xl border border-edge bg-panel/60 p-4">
          <Spinner />
          <span className="text-sm text-slate-300">{status}</span>
          <button onClick={() => cancelScan(id)} className="ml-auto text-xs text-slate-500 hover:text-phishing">
            Abbrechen
          </button>
        </div>
      )}

      {/* Quick-check provisional result */}
      {quick && !verdict && (
        <Panel title="Schnell-Check (Stufe 1)">
          <p className="mb-3 text-sm text-slate-400">
            Vorab-Einschätzung aus der URL – der Tiefen-Scan in der Sandbox läuft noch.
          </p>
          <SignalList signals={quick.signals} />
        </Panel>
      )}

      {/* Approval dialog */}
      {approval && (
        <div className="animate-slidein rounded-xl border border-suspicious/50 bg-suspicious/10 p-4">
          <p className="font-semibold text-suspicious">Freigabe nötig</p>
          <p className="mt-1 text-sm text-slate-200">{approval}</p>
          <div className="mt-3 flex gap-2">
            <button onClick={() => decide(true)} className="rounded-lg bg-suspicious px-4 py-2 text-sm font-semibold text-black hover:brightness-110">
              Freigeben
            </button>
            <button onClick={() => decide(false)} className="rounded-lg border border-edge px-4 py-2 text-sm text-slate-300 hover:bg-panel">
              Ablehnen
            </button>
          </div>
        </div>
      )}

      {/* Final verdict */}
      {verdict && (
        <div className="animate-slidein">
          <VerdictBadge verdict={verdict} />
        </div>
      )}

      {/* Screenshots */}
      {(shots.desktop || shots.mobile) && (
        <Panel title="Screenshots (in der Sandbox aufgenommen)">
          <div className="flex flex-wrap gap-4">
            {shots.desktop && <Shot src={abs(shots.desktop)} label="Desktop" />}
            {shots.mobile && <Shot src={abs(shots.mobile)} label="Mobile" />}
          </div>
        </Panel>
      )}

      {/* Signals */}
      {shownSignals.length > 0 && (
        <Panel title="Gefundene Signale">
          <SignalList signals={shownSignals} />
        </Panel>
      )}

      {/* Vision */}
      {vision && (
        <Panel title="Bild-Analyse (Vision-Modell)">
          <p className="text-sm text-slate-300">{vision.description_en}</p>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-400">
            {vision.impersonated_brand && <Tag>Marke: {vision.impersonated_brand}</Tag>}
            {vision.looks_like_login && <Tag>Login-Seite</Tag>}
            {vision.looks_like_payment && <Tag>Zahlungsseite</Tag>}
          </div>
        </Panel>
      )}

      {/* Redirect chain */}
      {redirects.length > 0 && (
        <Panel title="Weiterleitungskette">
          <ol className="space-y-1">
            {redirects.map((r, i) => (
              <li key={i} className="animate-slidein font-mono text-xs text-slate-300">
                <span className="mr-2 rounded bg-canvas px-1.5 py-0.5 text-slate-400">{r.status}</span>
                {r.url}
              </li>
            ))}
          </ol>
        </Panel>
      )}

      {/* Containment events — the heart of the challenge */}
      {containment.length > 0 && (
        <Panel title="🛡️ Containment-Ereignisse">
          <ul className="space-y-2">
            {containment.map((c, i) => (
              <li key={i} className="animate-slidein rounded-lg border border-phishing/30 bg-phishing/5 p-2 text-sm">
                <span className="font-mono text-xs text-phishing">{c.type}</span>
                <p className="text-slate-200">{c.detail}</p>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {domains.length > 0 && (
        <Panel title="Angefragte Domains">
          <p className="break-words font-mono text-xs text-slate-400">{domains.join(" · ")}</p>
        </Panel>
      )}

      {/* Report actions */}
      {done && verdict && (
        <div className="flex flex-wrap gap-3 pt-2">
          <a
            href={reportUrl(id)}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-sky-400"
          >
            Report öffnen (als PDF druckbar)
          </a>
          <button
            onClick={() => navigator.clipboard?.writeText(window.location.href)}
            className="rounded-xl border border-edge px-5 py-2.5 text-sm text-slate-300 hover:bg-panel"
          >
            Teilbaren Link kopieren
          </button>
        </div>
      )}
    </main>
  );
}

function abs(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  // API_BASE may be absolute (dev) or "/api" (prod same-origin).
  if (API_BASE.startsWith("http")) {
    const origin = new URL(API_BASE).origin;
    return origin + path;
  }
  return path;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="animate-slidein rounded-xl border border-edge bg-panel/60 p-5">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">{title}</h3>
      {children}
    </section>
  );
}

function Shot({ src, label }: { src: string; label: string }) {
  return (
    <figure className="min-w-0">
      <img src={src} alt={`${label}-Screenshot`} className="max-w-[340px] rounded-lg border border-edge" />
      <figcaption className="mt-1 text-xs text-slate-500">{label}</figcaption>
    </figure>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full border border-edge bg-canvas px-2 py-0.5">{children}</span>;
}

function Spinner() {
  return (
    <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-sky-500 border-t-transparent" aria-hidden />
  );
}

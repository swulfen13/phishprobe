// Thin client for the PhishProbe orchestrator. In production everything is
// same-origin behind Caddy (/api). For local dev set NEXT_PUBLIC_API_BASE to
// e.g. http://localhost:8000/api.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "/api";

export type Severity = "low" | "medium" | "high";
export type VerdictLevel = "safe" | "suspicious" | "phishing";

export interface Signal {
  type: string;
  detail: string;
  severity: Severity;
}

export interface QuickResult {
  score: number;
  level: VerdictLevel;
  signals: Signal[];
  host: string;
  registered_domain: string;
  is_shortener: boolean;
}

export interface Verdict {
  verdict: VerdictLevel;
  risk_score: number;
  impersonated_brand: string | null;
  signals: Signal[];
  explanation_de: string;
  explanation_en: string;
  used_llm?: boolean;
}

export interface CreateScanResponse {
  scan_id: string;
  quick_result: QuickResult;
  cached: boolean;
  verdict?: Verdict;
}

export async function createScan(url: string, deep = true): Promise<CreateScanResponse> {
  const res = await fetch(`${API_BASE}/scans`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, deep }),
  });
  if (!res.ok) throw new Error(`Scan konnte nicht gestartet werden (${res.status})`);
  return res.json();
}

export interface ScanRecord {
  id: string;
  url: string;
  status: string;
  deep: boolean;
  quick_result: QuickResult | null;
  verdict: Verdict | null;
  scan_data: any;
}

export async function getScan(scanId: string): Promise<ScanRecord> {
  const res = await fetch(`${API_BASE}/scans/${scanId}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Scan nicht gefunden (${res.status})`);
  return res.json();
}

export async function quickCheck(url: string): Promise<QuickResult> {
  const res = await fetch(`${API_BASE}/quick?url=${encodeURIComponent(url)}`);
  if (!res.ok) throw new Error(`Schnell-Check fehlgeschlagen (${res.status})`);
  return res.json();
}

export async function approveScan(scanId: string, approved: boolean): Promise<void> {
  await fetch(`${API_BASE}/scans/${scanId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved }),
  });
}

export async function cancelScan(scanId: string): Promise<void> {
  await fetch(`${API_BASE}/scans/${scanId}/cancel`, { method: "POST" });
}

export function reportUrl(scanId: string): string {
  return `${API_BASE}/scans/${scanId}/report.html`;
}

export interface ScanEvent {
  type: string;
  payload: any;
}

// Subscribe to the live SSE stream. Returns an unsubscribe function.
export function subscribeEvents(
  scanId: string,
  onEvent: (e: ScanEvent) => void,
  onError?: () => void
): () => void {
  const es = new EventSource(`${API_BASE}/scans/${scanId}/events`);
  const types = [
    "status", "redirects", "network", "containment", "screenshots",
    "vision", "signals", "approval_request", "approval_result",
    "deep_result", "verdict", "error", "done",
  ];
  for (const t of types) {
    es.addEventListener(t, (ev) => {
      try {
        onEvent({ type: t, payload: JSON.parse((ev as MessageEvent).data) });
      } catch {
        /* ignore malformed frame */
      }
      if (t === "done") es.close();
    });
  }
  es.onerror = () => {
    onError?.();
  };
  return () => es.close();
}

import type { Signal, Severity } from "@/lib/api";

const SEV: Record<Severity, { label: string; cls: string }> = {
  low: { label: "niedrig", cls: "bg-slate-600 text-slate-100" },
  medium: { label: "mittel", cls: "bg-suspicious/80 text-black" },
  high: { label: "hoch", cls: "bg-phishing text-white" },
};

export default function SignalList({ signals }: { signals: Signal[] }) {
  if (!signals?.length) {
    return <p className="text-sm text-slate-500">Keine Signale erfasst.</p>;
  }
  // Show strongest signals first.
  const order: Severity[] = ["high", "medium", "low"];
  const sorted = [...signals].sort((a, b) => order.indexOf(a.severity) - order.indexOf(b.severity));
  return (
    <ul className="space-y-2">
      {sorted.map((s, i) => (
        <li key={i} className="flex gap-3 rounded-lg border border-edge bg-canvas/50 p-3">
          <span className={`h-fit shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase ${SEV[s.severity].cls}`}>
            {SEV[s.severity].label}
          </span>
          <span className="min-w-0">
            <span className="font-mono text-xs text-slate-400">{s.type}</span>
            <p className="text-sm text-slate-200">{s.detail}</p>
          </span>
        </li>
      ))}
    </ul>
  );
}

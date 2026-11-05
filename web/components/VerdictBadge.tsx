import type { Verdict, VerdictLevel } from "@/lib/api";

const META: Record<VerdictLevel, { emoji: string; label: string; ring: string; text: string; bar: string }> = {
  safe: { emoji: "🟢", label: "Keine Auffälligkeiten", ring: "ring-safe/40", text: "text-safe", bar: "bg-safe" },
  suspicious: { emoji: "🟡", label: "Verdächtig", ring: "ring-suspicious/40", text: "text-suspicious", bar: "bg-suspicious" },
  phishing: { emoji: "🔴", label: "Phishing / gefährlich", ring: "ring-phishing/50", text: "text-phishing", bar: "bg-phishing" },
};

export default function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const m = META[verdict.verdict];
  return (
    <div className={`rounded-2xl border border-edge bg-panel p-6 shadow-panel ring-1 ${m.ring}`}>
      <div className="flex items-center gap-5">
        <div className="text-5xl" aria-hidden>{m.emoji}</div>
        <div className="min-w-0">
          <h2 className={`text-2xl font-bold ${m.text}`}>{m.label}</h2>
          {verdict.impersonated_brand && (
            <p className="mt-1 text-sm text-slate-400">
              Imitiert vermutlich: <span className="font-semibold text-slate-200">{verdict.impersonated_brand}</span>
            </p>
          )}
        </div>
        <div className="ml-auto text-center">
          <div className="text-xs uppercase tracking-wide text-slate-500">Risiko</div>
          <div className={`text-4xl font-black ${m.text}`}>{verdict.risk_score}</div>
          <div className="text-xs text-slate-500">/ 100</div>
        </div>
      </div>

      <div className="mt-4 h-2 overflow-hidden rounded-full bg-canvas">
        <div className={`h-full ${m.bar}`} style={{ width: `${Math.max(3, verdict.risk_score)}%` }} />
      </div>

      {verdict.explanation_de && (
        <p className="mt-4 text-[15px] leading-relaxed text-slate-200">{verdict.explanation_de}</p>
      )}
      {verdict.used_llm === false && (
        <p className="mt-2 text-xs text-slate-500">
          Hinweis: KI-Modell war nicht verfügbar – Einschätzung beruht nur auf Signal-Heuristik.
        </p>
      )}
    </div>
  );
}

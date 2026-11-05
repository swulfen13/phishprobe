"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createScan } from "@/lib/api";

const EXAMPLES: { label: string; url: string; note: string }[] = [
  { label: "🐦 Fake-Paketdienst (Demo)", url: "/demo/fake-phish/parcel/index.html", note: "Kartendaten-Formular" },
  { label: "🪤 Prompt-Injection (Demo)", url: "/demo/fake-phish/injection/index.html", note: "täuscht die KI" },
  { label: "↪️ Redirect-Kette (Demo)", url: "/demo/fake-phish/redirect/1.html", note: "4 Hops" },
  { label: "📥 Auto-Download (Demo)", url: "/demo/fake-phish/auto-download/index.html", note: "blockiert" },
  { label: "✅ Wikipedia (harmlos)", url: "https://en.wikipedia.org/wiki/Phishing", note: "zum Vergleich" },
];

export default function Home() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start(target: string) {
    const value = target.trim();
    if (!value) return;
    // Resolve relative demo paths against the current origin.
    const absolute = value.startsWith("/") ? `${window.location.origin}${value}` : value;
    setLoading(true);
    setError(null);
    try {
      const res = await createScan(absolute, true);
      router.push(`/scans/${res.scan_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unbekannter Fehler");
      setLoading(false);
    }
  }

  return (
    <main>
      <section className="text-center">
        <h1 className="text-balance text-3xl font-bold tracking-tight sm:text-4xl">
          Verdächtigen Link prüfen – ohne ihn selbst zu öffnen
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-pretty text-slate-400">
          PhishProbe öffnet den Link in einer Wegwerf-Sandbox auf Vultr, folgt allen
          Weiterleitungen, macht Screenshots und gibt ein Urteil mit Erklärung ab.
        </p>
      </section>

      <form
        className="mt-8"
        onSubmit={(e) => {
          e.preventDefault();
          start(url);
        }}
      >
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            type="text"
            inputMode="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Link aus SMS, Mail oder WhatsApp einfügen …"
            aria-label="Zu prüfender Link"
            className="w-full rounded-xl border border-edge bg-panel px-4 py-3 text-slate-100 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/30"
          />
          <button
            type="submit"
            disabled={loading || !url.trim()}
            className="shrink-0 rounded-xl bg-sky-500 px-6 py-3 font-semibold text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Starte …" : "Prüfen"}
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-phishing">{error}</p>}
      </form>

      <div className="mt-6">
        <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">Beispiele</p>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex.url}
              type="button"
              onClick={() => start(ex.url)}
              disabled={loading}
              className="group rounded-full border border-edge bg-panel px-3 py-1.5 text-sm text-slate-300 transition hover:border-sky-500/50 hover:text-white disabled:opacity-50"
              title={ex.note}
            >
              {ex.label}
              <span className="ml-1 text-xs text-slate-500 group-hover:text-slate-400">· {ex.note}</span>
            </button>
          ))}
        </div>
      </div>

      <ol className="mt-12 grid gap-4 sm:grid-cols-3">
        {[
          ["1", "Link einfügen", "Du kopierst den verdächtigen Link hierher."],
          ["2", "Agent öffnet ihn sicher", "In einer isolierten Sandbox auf Vultr – getrennt von deinem Gerät."],
          ["3", "Urteil mit Erklärung", "🟢 / 🟡 / 🔴 plus Begründung in einfacher Sprache."],
        ].map(([n, title, body]) => (
          <li key={n} className="rounded-xl border border-edge bg-panel/60 p-4">
            <div className="mb-2 flex h-7 w-7 items-center justify-center rounded-full bg-sky-500/20 text-sm font-bold text-sky-400">
              {n}
            </div>
            <h3 className="font-semibold text-slate-100">{title}</h3>
            <p className="mt-1 text-sm text-slate-400">{body}</p>
          </li>
        ))}
      </ol>
    </main>
  );
}

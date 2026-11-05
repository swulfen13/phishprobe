import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PhishProbe – Links sicher prüfen",
  description:
    "Prüft verdächtige Links in einer Wegwerf-Sandbox auf Vultr, ohne dass du sie selbst öffnen musst.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de">
      <body className="text-slate-200 antialiased">
        <div className="mx-auto max-w-3xl px-4 py-8 sm:py-12">
          <header className="mb-10 flex items-center gap-2">
            <a href="/" className="flex items-center gap-2 text-lg font-bold tracking-tight">
              <span aria-hidden>🛡️</span> PhishProbe
            </a>
            <span className="ml-auto text-xs text-slate-500">läuft auf Vultr</span>
          </header>
          {children}
          <footer className="mt-16 border-t border-edge pt-6 text-xs text-slate-500">
            PhishProbe ist ein Hilfsmittel und gibt keine Sicherheitsgarantie.
            „Keine Auffälligkeiten" bedeutet nicht „garantiert sicher".
          </footer>
        </div>
      </body>
    </html>
  );
}

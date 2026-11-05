import type { Config } from "tailwindcss";

// Design thesis: a calm, trustworthy security tool. Deep slate canvas, one
// accent per verdict (green/amber/red), generous whitespace, system sans.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#0b1120",
        panel: "#111a2e",
        edge: "#1e2a44",
        safe: "#22c55e",
        suspicious: "#f59e0b",
        phishing: "#ef4444",
      },
      boxShadow: {
        panel: "0 10px 40px -12px rgba(0,0,0,0.5)",
      },
    },
  },
  plugins: [],
};
export default config;

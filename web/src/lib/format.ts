export const pct = (v: number | null | undefined, digits = 0) =>
  v == null ? "–" : `${(v * 100).toFixed(digits)}%`;

export const pts = (v: number | null | undefined) =>
  v == null ? "–" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)} pts`;

export const num = (v: number | null | undefined, digits = 1) =>
  v == null ? "–" : v.toFixed(digits);

export const usd = (v: number | null | undefined) =>
  v == null ? "not priced" : `$${v < 1 ? v.toFixed(4) : v.toFixed(2)}`;

export const ms = (v: number | null | undefined) =>
  v == null ? "–" : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`;

export function when(iso: string | null | undefined) {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export const shortId = (id: string | null | undefined) => (id ? id.slice(0, 8) : "–");

export const humanise = (s: string | null | undefined) =>
  s ? s.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase()) : "–";

export const PROVIDER_LABEL: Record<string, string> = {
  perplexity: "Perplexity",
  openai: "ChatGPT",
  gemini: "Gemini",
};

export const providerLabel = (p: string) => PROVIDER_LABEL[p] ?? p;

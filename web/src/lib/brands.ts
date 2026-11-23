// Each brand is a swatch colour used everywhere it appears (charts, chips, highlights).
// Values are CSS variables so they follow light/dark mode.

const SWATCH: Record<string, string> = {
  "Sephora India": "var(--brand-sephora)",
  Nykaa: "var(--brand-nykaa)",
  Tira: "var(--brand-tira)",
};

const FALLBACK = ["var(--chart-4)", "var(--chart-5)"];

export function brandColor(brand: string, i = 0): string {
  return SWATCH[brand] ?? FALLBACK[i % FALLBACK.length];
}

export const BRAND_ORDER = ["Sephora India", "Nykaa", "Tira"];

export function sortBrands<T extends { brand: string }>(rows: T[]): T[] {
  const rank = (b: string) => {
    const i = BRAND_ORDER.indexOf(b);
    return i === -1 ? 99 : i;
  };
  return [...rows].sort((a, b) => rank(a.brand) - rank(b.brand));
}

export const DOMAIN_TYPE_COLOR: Record<string, string> = {
  brand_owned: "var(--brand-sephora)",
  competitor: "var(--brand-nykaa)",
  retailer: "var(--brand-tira)",
  editorial: "var(--chart-4)",
  ugc: "#7c8bd9",
  video: "#d97c7c",
  unclassified: "var(--chart-5)",
};

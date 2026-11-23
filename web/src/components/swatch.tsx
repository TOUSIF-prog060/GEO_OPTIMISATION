"use client";

import { brandColor, sortBrands } from "@/lib/brands";
import { pct } from "@/lib/format";

/** Share of voice as a strip of brand swatches: each brand's width is its share. */
export function SwatchStrip({
  rows,
  label,
  note,
}: {
  rows: { brand: string; value: number | null }[];
  label: string;
  note?: string;
}) {
  const parts = sortBrands(rows).filter((r) => (r.value ?? 0) > 0);
  const total = parts.reduce((s, r) => s + (r.value ?? 0), 0) || 1;
  return (
    <figure className="min-w-0">
      <figcaption className="mb-2 flex items-baseline justify-between gap-3 text-sm">
        <span className="font-medium">{label}</span>
        {note && <span className="text-xs text-muted-foreground">{note}</span>}
      </figcaption>
      <div
        className="swatch-in flex h-12 w-full overflow-hidden rounded-md"
        role="img"
        aria-label={`${label}: ${parts.map((p) => `${p.brand} ${pct(p.value)}`).join(", ")}`}
      >
        {parts.map((p, i) => (
          <div
            key={p.brand}
            className="relative flex items-end px-2.5 pb-1.5 text-xs font-medium text-white"
            style={{
              width: `${((p.value ?? 0) / total) * 100}%`,
              background: brandColor(p.brand),
              boxShadow: i ? "inset 1px 0 0 rgba(255,255,255,0.35)" : undefined,
            }}
          >
            <span className="num truncate drop-shadow-[0_1px_1px_rgba(0,0,0,0.25)]">
              {pct(p.value)}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {parts.map((p) => (
          <span key={p.brand} className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-[2px]" style={{ background: brandColor(p.brand) }} />
            {p.brand}
          </span>
        ))}
      </div>
    </figure>
  );
}

/** Brand × category grid; cell strength = mention rate in that brand's colour. */
export function Heatmap({
  rows,
  brands,
}: {
  rows: { category: string; brand: string; value: number | null; n: number }[];
  brands: string[];
}) {
  const cats = [...new Set(rows.map((r) => r.category))].sort();
  const get = (c: string, b: string) => rows.find((r) => r.category === c && r.brand === b);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[420px] table-fixed border-separate border-spacing-1 text-sm">
        <thead>
          <tr>
            <th className="w-40 text-left text-xs font-normal text-muted-foreground">Category</th>
            {brands.map((b) => (
              <th key={b} className="text-left text-xs font-medium">
                {b}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cats.map((c) => (
            <tr key={c}>
              <td className="pr-2 capitalize text-muted-foreground">{c.replaceAll("_", " ")}</td>
              {brands.map((b) => {
                const cell = get(c, b);
                const v = cell?.value ?? null;
                return (
                  <td key={b} className="p-0">
                    <div
                      className="relative h-9 overflow-hidden rounded-[4px] bg-muted"
                      title={cell ? `${b} · ${c}: ${pct(v)} of ${cell.n} answers` : "no data"}
                    >
                      {v != null && (
                        <div
                          className="absolute inset-0"
                          style={{ background: brandColor(b), opacity: 0.12 + v * 0.88 }}
                        />
                      )}
                      <span
                        className={`num relative grid h-full place-items-center text-xs font-medium ${
                          v != null && v > 0.5 ? "text-white" : ""
                        }`}
                      >
                        {v == null ? "–" : pct(v)}
                      </span>
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

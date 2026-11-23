import { brandColor } from "@/lib/brands";

// Names to mark in answer text, and the brand each belongs to. Display only: the measured
// mentions come from the diagnostics parser (aliases in configs/beauty_india.yaml).
const ALIASES: [string, string][] = [
  ["Sephora India", "Sephora India"],
  ["sephora.in", "Sephora India"],
  ["Sephora", "Sephora India"],
  ["Nykaa Fashion", "Nykaa"],
  ["nykaa.com", "Nykaa"],
  ["Nykaa", "Nykaa"],
  ["Tira Beauty", "Tira"],
  ["tirabeauty.com", "Tira"],
  ["Tira", "Tira"],
];

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const RE = new RegExp(`\\b(${ALIASES.map(([a]) => escape(a)).join("|")})\\b`, "gi");

export function Highlighted({ text }: { text: string }) {
  const parts = text.split(RE);
  return (
    <>
      {parts.map((part, i) => {
        const hit = ALIASES.find(([a]) => a.toLowerCase() === part.toLowerCase());
        if (!hit) return part;
        return (
          <mark
            key={i}
            title={hit[1]}
            className="rounded-[3px] px-0.5 font-medium text-inherit"
            style={{ background: `color-mix(in oklch, ${brandColor(hit[1])} 22%, transparent)` }}
          >
            {part}
          </mark>
        );
      })}
    </>
  );
}

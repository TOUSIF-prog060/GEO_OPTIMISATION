"use client";

import { ChevronDown, CircleHelp, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { GLOSSARY } from "@/lib/glossary";
import { useLocal, writeLocal } from "@/lib/local-store";
import { cn } from "@/lib/utils";

export type HelpStep = { icon: React.ComponentType<{ className?: string }>; title: string; text: string };

/** "How this works": three steps that light up in turn, with a track filling between them.
 *  Collapsible; the choice is remembered per page. */
export function HowItWorks({ id, steps }: { id: string; steps: HelpStep[] }) {
  const key = `bsb.help.${id}`;
  const closed = useLocal(key) === "closed";
  const cycle = 7.5; // seconds, matches .step-cycle in globals.css
  return (
    <section className="rounded-xl border bg-card" data-tour="how-it-works">
      <button
        type="button"
        onClick={() => writeLocal(key, closed ? null : "closed")}
        aria-expanded={!closed}
        className="flex w-full items-center gap-2 rounded-xl px-5 py-3.5 text-left text-sm font-medium focus-visible:outline-2 focus-visible:outline-ring"
      >
        <CircleHelp className="size-4 text-primary" />
        How this works
        <span className="ml-auto text-xs font-normal text-muted-foreground">{closed ? "Show" : "Hide"}</span>
        <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", !closed && "rotate-180")} />
      </button>
      {!closed && (
        <ol className="relative grid gap-5 px-5 pb-5 sm:grid-cols-3 sm:gap-6">
          {/* the track behind the step markers (desktop only) */}
          <span aria-hidden className="absolute top-[1.15rem] right-[16.6%] left-[16.6%] hidden h-0.5 bg-border sm:block">
            <span className="track-fill absolute inset-0 bg-primary/60" />
          </span>
          {steps.map((s, i) => (
            <li
              key={s.title}
              className="step-cycle relative flex gap-3 sm:flex-col sm:items-center sm:text-center"
              style={{ animationDelay: `${-(((steps.length - i) % steps.length) * cycle) / steps.length}s` }}
            >
              <span
                className="step-dot relative z-10 grid size-9 shrink-0 place-items-center rounded-full border border-primary/40 bg-card text-primary"
                style={{ animationDelay: `${-(((steps.length - i) % steps.length) * cycle) / steps.length}s` }}
              >
                <s.icon className="size-4" />
              </span>
              <span>
                <span className="block text-sm font-semibold">
                  <span className="text-muted-foreground">{i + 1}. </span>
                  {s.title}
                </span>
                <span className="mt-0.5 block max-w-[34ch] text-[0.82rem] leading-relaxed text-muted-foreground">
                  {s.text}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/** A small "?" that opens a plain-language definition from the glossary. */
export function Explain({ term, className }: { term: keyof typeof GLOSSARY | string; className?: string }) {
  const def = GLOSSARY[term];
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  if (!def) return null;
  return (
    <span ref={ref} className={cn("relative inline-flex align-middle", className)}>
      <button
        type="button"
        aria-label={`What is "${def.title}"?`}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "grid size-[1.15rem] place-items-center rounded-full border text-[0.65rem] font-semibold text-muted-foreground transition-colors",
          "hover:border-primary hover:text-primary focus-visible:outline-2 focus-visible:outline-ring",
          open && "border-primary bg-primary text-primary-foreground hover:text-primary-foreground",
        )}
      >
        ?
      </button>
      {open && (
        <span
          id={id}
          role="dialog"
          aria-label={def.title}
          className="rise-in absolute top-full left-1/2 z-40 mt-2 w-72 -translate-x-1/2 rounded-lg border bg-popover p-3.5 text-left text-sm font-normal normal-case tracking-normal text-popover-foreground shadow-lg"
        >
          <span className="flex items-start gap-2">
            <span className="flex-1 font-semibold">{def.title}</span>
            <button
              type="button"
              aria-label="Close"
              onClick={() => setOpen(false)}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="size-3.5" />
            </button>
          </span>
          <span className="mt-1 block leading-relaxed text-muted-foreground">{def.meaning}</span>
          {def.example && (
            <span className="mt-2 block rounded-md bg-muted px-2.5 py-1.5 text-xs leading-relaxed">
              {def.example}
            </span>
          )}
        </span>
      )}
    </span>
  );
}

/** A label followed by its "?" explainer. */
export function Term({ children, term }: { children: React.ReactNode; term: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {children}
      <Explain term={term} />
    </span>
  );
}

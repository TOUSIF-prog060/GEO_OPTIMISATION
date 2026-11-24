"use client";

import { ArrowLeft, ArrowRight, Sparkles, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { useLocal, writeLocal } from "@/lib/local-store";

type Stop = { target?: string; title: string; text: string };

// Each stop points at an element marked data-tour="<target>". If the element is not on
// screen (for example the sidebar on a phone), the card is shown in the middle instead.
const STOPS: Stop[] = [
  {
    title: "Welcome",
    text: "This app shows how AI assistants like ChatGPT and Gemini talk about Sephora India compared with Nykaa and Tira, and helps you improve it. This short tour takes under a minute.",
  },
  {
    target: "next-step",
    title: "Start here every time",
    text: "This card always tells you the one thing to do next, based on what has been done so far. Click its button to go straight there.",
  },
  {
    target: "nav-ask",
    title: "1. Ask AI",
    text: "Send shopping questions to the AI engines, like a customer would. You can type your own question or tick ready-made ones.",
  },
  {
    target: "nav-results",
    title: "2. See results",
    text: "How often each brand is named, on which engine and for which products, and what makes Sephora show up.",
  },
  {
    target: "nav-fix",
    title: "3. Fix gaps",
    text: "Where competitors beat Sephora, what to do about it, and website content drafted for you to approve.",
  },
  {
    target: "nav-check",
    title: "4. Check it worked",
    text: "Ask the same questions again after changes, and check how accurate the measurements are.",
  },
  {
    target: "help-legend",
    title: "Help is everywhere",
    text: "Look for “How this works” at the top of each page, a “?” next to any number, and hover over any button to see what it does.",
  },
  {
    target: "tour-button",
    title: "Take the tour again any time",
    text: "That's it. Click here whenever you want this walkthrough again.",
  },
];

const KEY = "bsb.tour";
const listeners = new Set<(open: boolean) => void>();

/** Start the tour from anywhere (for example the sidebar button). */
export function startTour() {
  listeners.forEach((l) => l(true));
}

type Box = { top: number; left: number; width: number; height: number } | null;

function findTarget(id?: string): HTMLElement | null {
  if (!id) return null;
  const els = Array.from(document.querySelectorAll<HTMLElement>(`[data-tour="${id}"]`));
  return els.find((el) => el.getClientRects().length > 0 && el.getBoundingClientRect().width > 0) ?? null;
}

export function Tour() {
  const path = usePathname();
  const seen = useLocal(KEY, "done") === "done";
  const [manual, setManual] = useState<boolean | null>(null);
  const [i, setI] = useState(0);
  const [box, setBox] = useState<Box>(null);
  const nextRef = useRef<HTMLButtonElement>(null);

  // First visit to the home page opens the tour automatically.
  const open = manual ?? (!seen && path === "/");

  useEffect(() => {
    const l = (v: boolean) => {
      setI(0);
      setManual(v);
    };
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  }, []);

  const stop = STOPS[i];

  useEffect(() => {
    if (!open) return;
    let raf = 0;
    const el = findTarget(stop.target);
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
    const update = () => {
      const t = findTarget(stop.target);
      if (!t) return setBox(null);
      const r = t.getBoundingClientRect();
      const pad = 6;
      setBox({ top: r.top - pad, left: r.left - pad, width: r.width + pad * 2, height: r.height + pad * 2 });
    };
    const schedule = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(update);
    };
    schedule();
    const settle = window.setTimeout(schedule, 450); // after smooth scrolling
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true);
    nextRef.current?.focus();
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(settle);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
    };
  }, [open, stop.target]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") finish();
      if (e.key === "ArrowRight") setI((x) => Math.min(x + 1, STOPS.length - 1));
      if (e.key === "ArrowLeft") setI((x) => Math.max(x - 1, 0));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  function finish() {
    writeLocal(KEY, "done");
    setManual(false);
    setI(0);
  }

  if (!open) return null;

  // Card position: beside the highlight when there is room, else below it, else centred.
  const vw = typeof window !== "undefined" ? window.innerWidth : 1200;
  const vh = typeof window !== "undefined" ? window.innerHeight : 800;
  const cardW = Math.min(340, vw - 32);
  let cardStyle: React.CSSProperties = { left: (vw - cardW) / 2, top: Math.max(16, vh / 2 - 120) };
  if (box) {
    const right = box.left + box.width + 16;
    if (right + cardW < vw - 16) cardStyle = { left: right, top: Math.min(Math.max(16, box.top), vh - 260) };
    else
      cardStyle = {
        left: Math.min(Math.max(16, box.left), vw - cardW - 16),
        top: box.top + box.height + 16 < vh - 240 ? box.top + box.height + 16 : Math.max(16, box.top - 236),
      };
  }

  const last = i === STOPS.length - 1;
  return (
    <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true" aria-label="Guided tour">
      {box ? (
        <div
          className="tour-spot tour-pulse pointer-events-none fixed rounded-lg"
          style={{ top: box.top, left: box.left, width: box.width, height: box.height }}
        />
      ) : (
        <div className="fixed inset-0 bg-foreground/55" />
      )}
      <div
        key={i}
        className="rise-in fixed rounded-xl border bg-popover p-5 text-popover-foreground shadow-2xl"
        style={{ ...cardStyle, width: cardW }}
      >
        <div className="flex items-start gap-3">
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground">
            <Sparkles className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xs text-muted-foreground">
              Step {i + 1} of {STOPS.length}
            </p>
            <h2 className="mt-0.5 text-lg font-semibold">{stop.title}</h2>
          </div>
          <button
            type="button"
            onClick={finish}
            aria-label="Close the tour"
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{stop.text}</p>
        <div className="mt-5 flex items-center gap-2">
          <div className="flex flex-1 gap-1" aria-hidden>
            {STOPS.map((_, k) => (
              <span
                key={k}
                className={`h-1.5 rounded-full transition-all ${k === i ? "w-5 bg-primary" : "w-1.5 bg-border"}`}
              />
            ))}
          </div>
          {i > 0 && (
            <Button variant="ghost" size="sm" onClick={() => setI(i - 1)}>
              <ArrowLeft /> Back
            </Button>
          )}
          <Button ref={nextRef} size="sm" onClick={() => (last ? finish() : setI(i + 1))}>
            {last ? "Finish" : "Next"} {!last && <ArrowRight />}
          </Button>
        </div>
        {i === 0 && (
          <button
            type="button"
            onClick={finish}
            className="mt-3 text-xs text-muted-foreground underline-offset-2 hover:underline"
          >
            Skip the tour
          </button>
        )}
      </div>
    </div>
  );
}

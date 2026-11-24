"use client";

import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  BadgeCheck,
  ChevronDown,
  Flag,
  MessagesSquare,
  ShieldCheck,
  Trophy,
  Wrench,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Empty, ErrorNote, Loading, StatusPill } from "@/components/bits";
import { Explain, Term } from "@/components/help";
import { ReportButton } from "@/components/report-button";
import { Heatmap } from "@/components/swatch";
import { Button } from "@/components/ui/button";
import { useApi } from "@/hooks/use-api";
import type { HistoryRow, Overview, Status } from "@/lib/api";
import { BRAND_ORDER, brandColor } from "@/lib/brands";
import { ms, pct, providerLabel, usd, when } from "@/lib/format";
import { cn } from "@/lib/utils";

// ---------- helpers ----------

function latestByProvider(history: HistoryRow[]) {
  const out = new Map<string, HistoryRow[]>();
  for (const p of new Set(history.map((h) => h.provider))) {
    const rows = history.filter((h) => h.provider === p);
    const last = rows.reduce((m, h) => (h.started_at > m ? h.started_at : m), "");
    out.set(p, rows.filter((h) => h.started_at === last));
  }
  return out;
}

/** Number that counts up once when it appears (skipped for people who prefer less motion). */
function CountUp({ value, format }: { value: number; format: (v: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let raf = 0;
    const start = performance.now();
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / 900);
      el.textContent = format(value * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, format]);
  return <span ref={ref}>{format(value)}</span>;
}

const asPct = (v: number) => `${Math.round(v * 100)}%`;
const asInt = (v: number) => `${Math.round(v)}`;

// ---------- next step ----------

type Next = { step: number; title: string; text: string; href: string; action: string };

function nextStep(c: Record<string, number>): Next {
  if (!c.runs)
    return { step: 1, title: "Ask AI your first questions", text: "Nothing has been measured yet. Start by sending shopping questions to the AI engines.", href: "/ask", action: "Ask AI" };
  if (!c.opportunities)
    return { step: 2, title: "See where Sephora stands", text: "You have answers. Look at the results, then find the gaps where competitors are ahead.", href: "/results", action: "See results" };
  if (!c.recs_approved)
    return { step: 3, title: "Review the gaps", text: `${c.opportunities} gap${c.opportunities === 1 ? "" : "s"} found. Approve the fixes worth doing.`, href: "/fix", action: "Review gaps" };
  if (!c.drafts)
    return { step: 3, title: "Draft the content", text: "Fixes are approved. Let the assistant write website content from your facts.", href: "/fix?tab=write", action: "Write content" };
  if (!c.drafts_approved)
    return { step: 3, title: "Approve the drafts", text: `${c.drafts} draft${c.drafts === 1 ? "" : "s"} waiting. Check them before anything goes live.`, href: "/fix?tab=write", action: "Review drafts" };
  if (!c.experiments_done)
    return { step: 4, title: "Check it worked", text: "Once the content is live, ask the same questions again and compare.", href: "/check", action: "Re-test" };
  return { step: 4, title: "Check the numbers can be trusted", text: "The cycle is complete. Review accuracy, or start a new round of questions.", href: "/check?tab=accuracy", action: "Check accuracy" };
}

const TRACK = [
  { icon: MessagesSquare, label: "Ask AI" },
  { icon: BarChart3, label: "See results" },
  { icon: Wrench, label: "Fix gaps" },
  { icon: ShieldCheck, label: "Check it worked" },
];

function NextStep({ next }: { next: Next }) {
  return (
    <section
      data-tour="next-step"
      className="rise-in overflow-hidden rounded-2xl border border-primary/30 bg-card"
      style={{ animationDelay: "60ms" }}
    >
      <div className="grid gap-6 p-6 sm:p-7 lg:grid-cols-[1.2fr_1fr] lg:items-center">
        <div>
          <p className="text-sm font-medium text-primary">Your next step</p>
          <h2 className="mt-1 text-2xl font-semibold">{next.title}</h2>
          <p className="mt-2 max-w-[52ch] leading-relaxed text-muted-foreground">{next.text}</p>
          <Button asChild size="lg" className="mt-5 h-10 px-4" hint={`Opens step ${next.step}: ${TRACK[next.step - 1].label}.`}>
            <Link href={next.href}>
              {next.action} <ArrowRight />
            </Link>
          </Button>
        </div>
        <ol className="grid grid-cols-4 gap-2" aria-label="Progress through the four steps">
          {TRACK.map((t, i) => {
            const n = i + 1;
            const state = n < next.step ? "done" : n === next.step ? "now" : "later";
            return (
              <li key={t.label} className="flex flex-col items-center gap-2 text-center">
                <div className="relative flex w-full items-center">
                  <span className={cn("h-0.5 flex-1", i === 0 ? "opacity-0" : n <= next.step ? "bg-primary" : "bg-border")} />
                  <span
                    className={cn(
                      "grid size-10 shrink-0 place-items-center rounded-full border-2 transition-colors",
                      state === "done" && "border-primary bg-primary text-primary-foreground",
                      state === "now" && "tour-pulse border-primary bg-accent text-primary",
                      state === "later" && "border-border bg-card text-muted-foreground",
                    )}
                  >
                    {state === "done" ? <BadgeCheck className="size-4" /> : <t.icon className="size-4" />}
                  </span>
                  <span className={cn("h-0.5 flex-1", i === 3 ? "opacity-0" : n < next.step ? "bg-primary" : "bg-border")} />
                </div>
                <span className={cn("text-xs leading-tight", state === "now" ? "font-semibold" : "text-muted-foreground")}>
                  {t.label}
                  <span className="block font-normal text-muted-foreground">
                    {state === "done" ? "Done" : state === "now" ? "You are here" : "Later"}
                  </span>
                </span>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}

// ---------- at a glance ----------

function Stat({
  icon: Icon,
  label,
  term,
  children,
  note,
  delay,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  term: string;
  children: React.ReactNode;
  note: React.ReactNode;
  delay: number;
}) {
  return (
    <div className="rise-in rounded-xl border bg-card p-5" style={{ animationDelay: `${delay}ms` }}>
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Icon className="size-4 text-primary" />
        <Term term={term}>{label}</Term>
      </p>
      <p className="num mt-2 font-[family-name:var(--font-bricolage)] text-4xl font-semibold">{children}</p>
      <p className="mt-1.5 text-sm text-muted-foreground">{note}</p>
    </div>
  );
}

/** Brands side by side as simple horizontal bars, biggest first. */
function BrandRows({ rows, target }: { rows: HistoryRow[]; target: string }) {
  const sorted = [...rows].sort((a, b) => (b.mention_rate ?? 0) - (a.mention_rate ?? 0));
  return (
    <ul className="space-y-3.5">
      {sorted.map((r) => (
        <li key={r.brand} className="grid grid-cols-[7.5rem_1fr_3.5rem] items-center gap-3">
          <span className={cn("truncate text-sm", r.brand === target && "font-semibold")}>{r.brand}</span>
          <div className="h-7 overflow-hidden rounded-md bg-muted">
            <div
              className="swatch-in h-full rounded-md"
              style={{ width: `${(r.mention_rate ?? 0) * 100}%`, background: brandColor(r.brand) }}
            />
          </div>
          <span className="num text-right font-medium">{pct(r.mention_rate)}</span>
        </li>
      ))}
    </ul>
  );
}

// ---------- page ----------

export default function HomePage() {
  const { data, error, loading } = useApi<Overview>("/overview");
  const { data: status } = useApi<Status>("/status");
  const [engine, setEngine] = useState<string>();

  const latest = useMemo(() => latestByProvider(data?.history ?? []), [data]);
  const target = status?.project.target ?? "Sephora India";
  const brands = useMemo(() => {
    const seen = new Set((data?.history ?? []).map((h) => h.brand));
    return BRAND_ORDER.filter((b) => seen.has(b)).concat([...seen].filter((b) => !BRAND_ORDER.includes(b)));
  }, [data]);

  if (error) return <ErrorNote message={error} />;
  if (loading || !data) return <Loading rows={4} />;

  const c = data.counts;
  const next = nextStep(c);
  // Default to the engine with the most answers, so the headline rests on the biggest sample.
  const providers = [...latest.entries()].sort((a, b) => (b[1][0]?.n_responses ?? 0) - (a[1][0]?.n_responses ?? 0));
  const ep = engine ?? providers[0]?.[0];
  const rows = latest.get(ep ?? "") ?? [];
  const me = rows.find((r) => r.brand === target);
  const leader = [...rows].sort((a, b) => (b.mention_rate ?? 0) - (a.mention_rate ?? 0))[0];
  const heat = data.categories
    .filter((x) => x.provider === ep)
    .map((x) => ({ category: x.category, brand: x.brand, value: x.mention_rate, n: x.n_responses }));

  return (
    <div className="space-y-8">
      <header className="rise-in max-w-3xl">
        <p className="text-sm font-medium text-primary">Home</p>
        {me && leader ? (
          <h1 className="mt-1 font-[family-name:var(--font-bricolage)] text-[1.9rem] font-medium leading-[1.15] tracking-tight sm:text-[2.5rem]">
            On {providerLabel(ep!)}, AI names {target} in{" "}
            <span className="num" style={{ color: brandColor(target) }}>
              {Math.round((me.mention_rate ?? 0) * 100)} of every 100
            </span>{" "}
            answers.{" "}
            {leader.brand !== target && (
              <span className="text-muted-foreground">
                {leader.brand} is named in{" "}
                <span className="num" style={{ color: brandColor(leader.brand) }}>
                  {Math.round((leader.mention_rate ?? 0) * 100)}
                </span>
                .
              </span>
            )}
          </h1>
        ) : (
          <h1 className="mt-1 text-3xl font-semibold sm:text-[2.4rem]">How AI assistants talk about {target}</h1>
        )}
        <p className="mt-3 leading-relaxed text-muted-foreground">
          This app asks AI assistants the questions shoppers ask, measures how often each brand is recommended, and
          helps you close the gaps.
        </p>
      </header>

      <NextStep next={next} />

      {!data.history.length ? (
        <Empty title="No results yet">Your numbers appear here after the first round of questions.</Empty>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <Stat icon={BarChart3} label={`${target} named`} term="mention_rate" delay={120}
              note={`in ${rows[0]?.n_responses ?? 0} answers on ${providerLabel(ep!)}`}>
              <CountUp value={me?.mention_rate ?? 0} format={asPct} />
            </Stat>
            <Stat icon={Trophy} label="Most named brand" term="mention_rate" delay={180}
              note={leader ? `named in ${pct(leader.mention_rate)} of answers` : "–"}>
              <span className="text-3xl" style={{ color: leader ? brandColor(leader.brand) : undefined }}>
                {leader?.brand ?? "–"}
              </span>
            </Stat>
            <Stat icon={Flag} label="Gaps to fix" term="gap" delay={240}
              note={c.opportunities ? "places where a competitor is ahead" : "none found yet"}>
              <CountUp value={c.opportunities ?? 0} format={asInt} />
            </Stat>
          </div>

          <section className="rise-in rounded-xl border bg-card p-6" style={{ animationDelay: "300ms" }}>
            <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">
                  <Term term="mention_rate">How the brands compare</Term>
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Share of answers that name each brand, from the latest round on {providerLabel(ep!)}.
                </p>
              </div>
              {providers.length > 1 && (
                <div className="flex flex-wrap gap-1.5" role="group" aria-label="Choose an AI engine">
                  {providers.map(([p]) => (
                    <Button key={p} size="sm" variant={p === ep ? "default" : "outline"} onClick={() => setEngine(p)}
                      hint={`Show results from ${providerLabel(p)}`}>
                      {providerLabel(p)}
                    </Button>
                  ))}
                </div>
              )}
            </div>
            <BrandRows rows={rows} target={target} />
          </section>

          {heat.length > 0 && (
            <section className="rise-in rounded-xl border bg-card p-6" style={{ animationDelay: "360ms" }}>
              <h2 className="text-lg font-semibold">Which products each brand is named for</h2>
              <p className="mt-1 mb-5 text-sm text-muted-foreground">
                Darker means named more often. Hover a cell to see how many answers it is based on.
              </p>
              <Heatmap rows={heat} brands={brands} />
            </section>
          )}

          <details className="group rounded-xl border bg-card">
            <summary className="flex cursor-pointer list-none items-center gap-2 px-6 py-4 font-medium">
              Details for analysts
              <span className="text-sm font-normal text-muted-foreground">recent rounds, cost, speed, PDF</span>
              <ChevronDown className="ml-auto size-4 text-muted-foreground transition-transform group-open:rotate-180" />
            </summary>
            <div className="space-y-5 border-t px-6 py-5">
              <div className="flex flex-wrap items-center gap-3">
                <ReportButton
                  kind="run"
                  runId={rows[0]?.run_id}
                  label="Download this round as PDF"
                />
                <span className="text-sm text-muted-foreground">
                  <Term term="round">A printable report of the latest round</Term>
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-sm">
                  <thead className="text-left text-xs text-muted-foreground">
                    <tr className="border-b">
                      <th className="py-2 font-normal">Started</th>
                      <th className="font-normal">AI engine</th>
                      <th className="font-normal">Status</th>
                      <th className="text-right font-normal">Questions</th>
                      <th className="text-right font-normal">Failed</th>
                      <th className="text-right font-normal">Cost</th>
                      <th className="text-right font-normal">Avg answer time</th>
                    </tr>
                  </thead>
                  <tbody className="num">
                    {data.ops.map((o) => (
                      <tr key={o.run_id} className="border-b last:border-0">
                        <td className="py-2.5">{when(o.started_at)}</td>
                        <td>{providerLabel(o.provider)}</td>
                        <td>
                          <StatusPill status={o.status} />
                        </td>
                        <td className="text-right">{o.calls}</td>
                        <td className={cn("text-right", o.errors && "text-loss")}>{o.errors}</td>
                        <td className="text-right text-muted-foreground">{usd(o.cost_usd)}</td>
                        <td className="text-right">{ms(o.avg_latency_ms)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs leading-relaxed text-muted-foreground">
                Figures describe the questions, engines and dates measured, nothing wider. AI answers vary between
                rounds, so repeat rounds before drawing conclusions. <Explain term="round" />
              </p>
            </div>
          </details>
        </>
      )}
    </div>
  );
}

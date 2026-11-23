"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Delta, Empty, ErrorNote, Loading, Panel, StatusPill } from "@/components/bits";
import { BrandBars, TrendLines } from "@/components/charts";
import { Heatmap, SwatchStrip } from "@/components/swatch";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi } from "@/hooks/use-api";
import type { HistoryRow, Overview, Status } from "@/lib/api";
import { BRAND_ORDER, brandColor } from "@/lib/brands";
import { humanise, ms, num, pct, providerLabel, usd, when } from "@/lib/format";

function latestByProvider(history: HistoryRow[]) {
  const out = new Map<string, HistoryRow[]>();
  for (const p of new Set(history.map((h) => h.provider))) {
    const rows = history.filter((h) => h.provider === p);
    const last = rows.reduce((m, h) => (h.started_at > m ? h.started_at : m), "");
    out.set(p, rows.filter((h) => h.started_at === last));
  }
  return out;
}

function Headline({ latest, target }: { latest: Map<string, HistoryRow[]>; target: string }) {
  // Pick the provider with the most answers so the sentence rests on the biggest sample.
  const [provider, rows] = [...latest.entries()].sort(
    (a, b) => (b[1][0]?.n_responses ?? 0) - (a[1][0]?.n_responses ?? 0),
  )[0];
  const me = rows.find((r) => r.brand === target);
  const leader = [...rows].sort((a, b) => (b.mention_rate ?? 0) - (a.mention_rate ?? 0))[0];
  const mine = me?.mention_rate ?? 0;
  const leads = leader.brand === target;
  return (
    <p className="max-w-3xl font-[family-name:var(--font-bricolage)] text-[1.9rem] font-medium leading-[1.15] tracking-tight sm:text-[2.6rem]">
      On {providerLabel(provider)}, {target} appears in{" "}
      <span className="num" style={{ color: brandColor(target) }}>
        {pct(mine)}
      </span>{" "}
      of answers.{" "}
      {leads ? (
        <span className="text-muted-foreground">That leads every competitor measured.</span>
      ) : (
        <span className="text-muted-foreground">
          {leader.brand} leads at{" "}
          <span className="num" style={{ color: brandColor(leader.brand) }}>
            {pct(leader.mention_rate)}
          </span>
          .
        </span>
      )}
    </p>
  );
}

export default function OverviewPage() {
  const { data, error, loading } = useApi<Overview>("/overview");
  const { data: status } = useApi<Status>("/status");
  const [trendProvider, setTrendProvider] = useState<string>();
  const [heatProvider, setHeatProvider] = useState<string>();

  const latest = useMemo(() => latestByProvider(data?.history ?? []), [data]);
  const providers = [...latest.keys()];
  const target = status?.project.target ?? "Sephora India";
  const brands = useMemo(() => {
    const seen = new Set((data?.history ?? []).map((h) => h.brand));
    return BRAND_ORDER.filter((b) => seen.has(b)).concat([...seen].filter((b) => !BRAND_ORDER.includes(b)));
  }, [data]);

  if (error) return <ErrorNote message={error} />;
  if (loading || !data) return <Loading rows={4} />;

  const tp = trendProvider ?? providers[0];
  const hp = heatProvider ?? providers[0];
  const trend = (() => {
    const rows = data.history.filter((h) => h.provider === tp);
    const runs = [...new Set(rows.map((r) => r.started_at))].sort();
    return runs.map((t) => {
      const row: Record<string, string | number | null> = { label: when(t) };
      for (const r of rows.filter((x) => x.started_at === t)) row[r.brand] = r.mention_rate;
      return row;
    });
  })();
  const byEngine = providers.map((p) => {
    const row: Record<string, string | number | null> = { engine: providerLabel(p) };
    for (const r of latest.get(p) ?? []) row[r.brand] = r.mention_rate;
    return row;
  });
  const heat = data.categories
    .filter((c) => c.provider === hp)
    .map((c) => ({ category: c.category, brand: c.brand, value: c.mention_rate, n: c.n_responses }));
  const c = data.counts;

  if (!data.history.length) {
    return (
      <div className="space-y-8">
        <p className="max-w-2xl font-[family-name:var(--font-bricolage)] text-[2.2rem] font-medium leading-tight">
          No answers measured yet. Ask the AI engines your prompt panel to see where {target} stands.
        </p>
        <Button asChild size="lg">
          <Link href="/discovery">Ask the engines</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-12">
      <section className="space-y-8">
        <Headline latest={latest} target={target} />
        <div
          className={
            providers.length === 1
              ? "max-w-3xl"
              : "grid gap-x-10 gap-y-8 md:grid-cols-2 xl:grid-cols-3"
          }
        >
          {providers.map((p) => {
            const rows = latest.get(p) ?? [];
            const k = data.kpis.find((x) => x.provider === p);
            return (
              <div key={p} className="space-y-3">
                <SwatchStrip
                  label={`Share of voice on ${providerLabel(p)}`}
                  note={`${rows[0]?.n_responses ?? 0} answers · ${when(rows[0]?.started_at)}`}
                  rows={rows.map((r) => ({ brand: r.brand, value: r.share_of_voice }))}
                />
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  {target} mention rate <span className="num font-medium text-foreground">{pct(k?.value)}</span>
                  <Delta value={k?.delta} />
                </p>
              </div>
            );
          })}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-5">
        <Panel
          className="lg:col-span-3"
          title="Mention rate over time"
          note="Share of answers that name each brand, per run."
          action={
            providers.length > 1 && (
              <Tabs value={tp} onValueChange={setTrendProvider}>
                <TabsList>
                  {providers.map((p) => (
                    <TabsTrigger key={p} value={p}>
                      {providerLabel(p)}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
            )
          }
        >
          {trend.length < 2 ? (
            <div className="space-y-2">
              <BrandBars data={trend} x="label" series={brands} height={240} />
              <p className="text-xs text-muted-foreground">
                One run so far. Run discovery again to see a trend line.
              </p>
            </div>
          ) : (
            <TrendLines data={trend} series={brands} />
          )}
        </Panel>
        <Panel className="lg:col-span-2" title="By engine" note="Latest run on each engine.">
          <BrandBars data={byEngine} x="engine" series={brands} height={240} />
        </Panel>
      </div>

      <Panel
        title="Where each brand shows up"
        note="Mention rate by product category. Small categories have few answers; hover a cell for n."
        action={
          providers.length > 1 && (
            <Tabs value={hp} onValueChange={setHeatProvider}>
              <TabsList>
                {providers.map((p) => (
                  <TabsTrigger key={p} value={p}>
                    {providerLabel(p)}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          )
        }
      >
        {heat.length ? <Heatmap rows={heat} brands={brands} /> : <Empty title="No category data yet" />}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel
          title="Biggest gaps"
          note="Ranked by priority: severity × confidence ÷ effort."
          action={
            <Button asChild variant="outline" size="sm">
              <Link href="/opportunities">All gaps</Link>
            </Button>
          }
        >
          {data.top_opportunities.length ? (
            <ol className="divide-y">
              {data.top_opportunities.map((o, i) => (
                <li key={i} className="flex items-start gap-4 py-3 first:pt-0 last:pb-0">
                  <span className="num w-10 shrink-0 font-[family-name:var(--font-bricolage)] text-xl font-semibold text-primary">
                    {num(o.priority_score, 0)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium leading-snug">{o.title}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {humanise(o.gap_type)} · effort {o.effort ?? "–"}
                    </p>
                  </div>
                  {o.review && <StatusPill status={o.review} />}
                </li>
              ))}
            </ol>
          ) : (
            <Empty title="No gaps found yet">Measure a run, then find gaps.</Empty>
          )}
        </Panel>

        <Panel title="Pipeline" note="What has been done so far.">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3">
            {[
              ["Runs", c.runs],
              ["Answers", c.answers],
              ["Gaps found", c.opportunities],
              ["Actions approved", c.recs_approved],
              ["Drafts", `${c.drafts_approved}/${c.drafts}`],
              ["Re-tests done", c.experiments_done],
            ].map(([k, v]) => (
              <div key={k as string}>
                <dt className="text-xs text-muted-foreground">{k}</dt>
                <dd className="num mt-1 font-[family-name:var(--font-bricolage)] text-2xl font-semibold">{v}</dd>
              </div>
            ))}
          </dl>
        </Panel>
      </div>

      <Panel title="Recent runs" note="Calls, failures, cost and speed per run.">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr className="border-b">
                <th className="py-2 font-normal">Started</th>
                <th className="font-normal">Engine</th>
                <th className="font-normal">Type</th>
                <th className="font-normal">Status</th>
                <th className="text-right font-normal">Calls</th>
                <th className="text-right font-normal">Failed</th>
                <th className="text-right font-normal">Cost</th>
                <th className="text-right font-normal">Avg time</th>
              </tr>
            </thead>
            <tbody className="num">
              {data.ops.map((o) => (
                <tr key={o.run_id} className="border-b last:border-0">
                  <td className="py-2.5">{when(o.started_at)}</td>
                  <td>{providerLabel(o.provider)}</td>
                  <td className="capitalize">{o.run_type}</td>
                  <td>
                    <StatusPill status={o.status} />
                  </td>
                  <td className="text-right">{o.calls}</td>
                  <td className={`text-right ${o.errors ? "text-loss" : ""}`}>{o.errors}</td>
                  <td className="text-right text-muted-foreground">{usd(o.cost_usd)}</td>
                  <td className="text-right">{ms(o.avg_latency_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <p className="max-w-3xl text-xs leading-relaxed text-muted-foreground">
        These figures describe the prompt panel, engines, market and dates measured, nothing wider.
        AI answers vary between runs; use repeated runs and the re-test page before drawing conclusions.
      </p>
    </div>
  );
}

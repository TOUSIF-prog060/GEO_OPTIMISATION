"use client";

import { ExternalLink, Search } from "lucide-react";
import { useMemo, useState } from "react";

import {
  BrandChip,
  Empty,
  ErrorNote,
  JobBar,
  Loading,
  PageHeader,
  Panel,
  RunSelect,
} from "@/components/bits";
import { BrandBars, RankBars } from "@/components/charts";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi, useJob } from "@/hooks/use-api";
import type { ResponseRow, Run, Status, VisibilityPayload, VisibilityRow } from "@/lib/api";
import { BRAND_ORDER, DOMAIN_TYPE_COLOR, brandColor, sortBrands } from "@/lib/brands";
import { humanise, num, pct, providerLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

function useRunParam(runs: Run[] | undefined) {
  const [pick, setRun] = useState<string>();
  // Runs only load in the browser, so this never reads window on the server.
  const fromUrl =
    runs && typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("run") : null;
  const run =
    pick ??
    runs?.find((r) => r.run_id === fromUrl)?.run_id ??
    runs?.find((r) => r.diagnosed)?.run_id ??
    runs?.[0]?.run_id;
  const choose = (id: string) => {
    setRun(id);
    window.history.replaceState(null, "", `?run=${id}`);
  };
  return [run, choose] as const;
}

function Metric({
  label,
  rows,
  pick,
  format,
  lowerIsBetter,
  hint,
}: {
  label: string;
  rows: VisibilityRow[];
  pick: (r: VisibilityRow) => number | null;
  format: (v: number | null) => string;
  lowerIsBetter?: boolean;
  hint: string;
}) {
  const target = rows.find((r) => r.is_target);
  const vals = rows.filter((r) => pick(r) != null);
  const best = [...vals].sort((a, b) => (lowerIsBetter ? pick(a)! - pick(b)! : pick(b)! - pick(a)!))[0];
  const leads = best && target && best.brand === target.brand;
  return (
    <div className="min-w-0 border-l-2 pl-4" style={{ borderColor: brandColor(target?.brand ?? "") }}>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="num mt-1 font-[family-name:var(--font-bricolage)] text-3xl font-semibold">
        {format(target ? pick(target) : null)}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        {!best ? hint : leads ? "Best of all brands" : `${best.brand}: ${format(pick(best))}`}
      </p>
    </div>
  );
}

function highlight(text: string, brands: string[]) {
  // Mark brand names in their swatch colour. Matching is for display only;
  // the measured mentions come from the diagnostics parser.
  if (!brands.length) return text;
  const re = new RegExp(`(${brands.map((b) => b.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return text.split(re).map((part, i) => {
    const b = brands.find((x) => x.toLowerCase() === part.toLowerCase());
    return b ? (
      <mark
        key={i}
        className="rounded-[3px] px-0.5 font-medium text-inherit"
        style={{ background: `color-mix(in oklch, ${brandColor(b)} 22%, transparent)` }}
      >
        {part}
      </mark>
    ) : (
      part
    );
  });
}

function Answers({ runId, target }: { runId: string; target: string }) {
  const { data, loading, error } = useApi<ResponseRow[]>(`/runs/${runId}/responses?limit=500`);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<"all" | "with" | "without" | "failed">("all");
  const [open, setOpen] = useState<string | null>(null);

  if (error) return <ErrorNote message={error} />;
  if (loading || !data) return <Loading />;

  const has = (r: ResponseRow) => r.mentions.some((m) => m.brand === target);
  const rows = data.filter((r) => {
    if (filter === "failed") return Boolean(r.error);
    if (r.error) return filter === "all";
    if (filter === "with" && !has(r)) return false;
    if (filter === "without" && has(r)) return false;
    const s = q.toLowerCase();
    return !s || r.prompt.toLowerCase().includes(s) || (r.answer_text ?? "").toLowerCase().includes(s);
  });
  const names = ["Sephora India", "Sephora", "Nykaa", "Tira"];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input
            placeholder="Search questions and answers"
            className="pl-8"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        {(
          [
            ["all", `All (${data.length})`],
            ["with", `Names ${target}`],
            ["without", `Misses ${target}`],
            ["failed", `Failed (${data.filter((r) => r.error).length})`],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setFilter(k)}
            className={cn(
              "rounded-full border px-3 py-1 text-xs",
              filter === k ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {!rows.length && <Empty title="No answers match" />}
      <ul className="divide-y rounded-lg border bg-card">
        {rows.map((r) => {
          const isOpen = open === r.response_id;
          return (
            <li key={r.response_id}>
              <button
                className="flex w-full items-start gap-4 px-4 py-3 text-left hover:bg-muted/50"
                onClick={() => setOpen(isOpen ? null : r.response_id)}
                aria-expanded={isOpen}
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{r.prompt}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {humanise(r.category)} · {providerLabel(r.provider)}
                    {r.repeat_no > 1 && ` · repeat ${r.repeat_no}`}
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
                  {r.error ? (
                    <span className="text-xs text-loss">failed</span>
                  ) : r.mentions.length ? (
                    sortBrands(r.mentions).map((m) => (
                      <span
                        key={m.brand}
                        className="num inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium text-white"
                        style={{ background: brandColor(m.brand) }}
                        title={`${m.brand}${m.rank ? `, ranked #${m.rank}` : ""}`}
                      >
                        {m.brand.split(" ")[0]}
                        {m.rank ? ` #${m.rank}` : ""}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-muted-foreground">no brand named</span>
                  )}
                </div>
              </button>
              {isOpen && (
                <div className="border-t bg-muted/30 px-4 py-4">
                  {r.error ? (
                    <p className="text-sm text-loss">{r.error}</p>
                  ) : (
                    <>
                      <div className="max-w-[75ch] whitespace-pre-wrap text-sm leading-relaxed">
                        {highlight(r.answer_text ?? "", names)}
                      </div>
                      {r.citations.length > 0 && (
                        <div className="mt-4">
                          <p className="mb-2 text-xs text-muted-foreground">
                            {r.citations.length} sources cited
                          </p>
                          <div className="flex flex-wrap gap-1.5">
                            {r.citations.map((c, i) => (
                              <a
                                key={i}
                                href={c.url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 rounded-md border bg-background px-2 py-1 text-xs hover:border-primary"
                              >
                                {c.domain}
                                <ExternalLink className="size-3 text-muted-foreground" />
                              </a>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function VisibilityPage() {
  const runs = useApi<Run[]>("/runs");
  const { data: status } = useApi<Status>("/status");
  const [runId, setRunId] = useRunParam(runs.data);
  const vis = useApi<VisibilityPayload>(runId ? `/runs/${runId}/visibility` : null);
  const [sentiment, setSentiment] = useState(false);
  const diagnose = useJob(() => {
    vis.reload();
    runs.reload();
  });

  const run = runs.data?.find((r) => r.run_id === runId);
  const target = status?.project.target ?? "Sephora India";

  const all = useMemo(() => sortBrands(vis.data?.visibility.filter((v) => v.category === "ALL") ?? []), [vis.data]);
  const brands = all.map((r) => r.brand);
  const byCat = useMemo(() => {
    const rows = vis.data?.visibility.filter((v) => v.category !== "ALL") ?? [];
    const cats = [...new Set(rows.map((r) => r.category))].sort();
    return cats.map((c) => {
      const row: Record<string, string | number | null> = { category: humanise(c) };
      for (const r of rows.filter((x) => x.category === c)) row[r.brand] = r.mention_rate;
      return row;
    });
  }, [vis.data]);
  const sources = useMemo(
    () =>
      (vis.data?.sources ?? [])
        .filter((s) => s.category === "ALL")
        .slice(0, 15)
        .map((s) => ({
          name: s.domain,
          value: s.n_citations,
          color: DOMAIN_TYPE_COLOR[s.domain_type ?? "unclassified"] ?? DOMAIN_TYPE_COLOR.unclassified,
          hint: humanise(s.domain_type ?? "unclassified"),
        })),
    [vis.data],
  );
  const sourceTypes = useMemo(() => {
    const rows = (vis.data?.sources ?? []).filter((s) => s.category === "ALL");
    const total = rows.reduce((s, r) => s + r.n_citations, 0) || 1;
    const m = new Map<string, number>();
    for (const r of rows) m.set(r.domain_type ?? "unclassified", (m.get(r.domain_type ?? "unclassified") ?? 0) + r.n_citations);
    return [...m.entries()].sort((a, b) => b[1] - a[1]).map(([t, n]) => ({ type: t, n, share: n / total }));
  }, [vis.data]);

  if (runs.error) return <ErrorNote message={runs.error} />;
  if (!runs.data) return <Loading />;
  if (!runs.data.length)
    return (
      <>
        <PageHeader title="Measure visibility" />
        <Empty title="No runs to measure">Ask the engines first, on the previous step.</Empty>
      </>
    );

  return (
    <div className="space-y-8">
      <PageHeader
        title="Measure visibility"
        lede="How often each brand is named, where it ranks in lists, which sites the engines cite, and how stable the answers are."
        actions={<RunSelect runs={runs.data} value={runId} onChange={setRunId} />}
      />

      {run && !run.diagnosed && (
        <Panel title="This run hasn't been measured yet">
          <p className="text-sm text-muted-foreground">
            Measuring reads the stored answers: it finds brand mentions and list ranks with rules, and cited sources. It
            makes no AI calls unless you add sentiment labels.
          </p>
        </Panel>
      )}

      <div className="flex flex-wrap items-center gap-4">
        <Button
          variant={run?.diagnosed ? "outline" : "default"}
          disabled={!runId || diagnose.busy}
          onClick={() =>
            diagnose.start("/jobs/diagnose", { run_id: runId, label_sentiment: sentiment }, "Measuring")
          }
        >
          {run?.diagnosed ? "Measure again" : "Measure this run"}
        </Button>
        <label
          className={cn("flex items-center gap-2 text-sm", !status?.analysis.has_key && "text-muted-foreground")}
        >
          <Checkbox
            checked={sentiment}
            disabled={!status?.analysis.has_key}
            onCheckedChange={(v) => setSentiment(Boolean(v))}
          />
          Add sentiment labels (uses OpenAI{status?.analysis.has_key ? "" : ", no key set"})
        </label>
        <div className="w-full sm:w-auto sm:min-w-[320px]">
          <JobBar job={diagnose.job} />
        </div>
      </div>

      {vis.error && <ErrorNote message={vis.error} />}
      {vis.loading && !vis.data && <Loading />}

      {vis.data && all.length > 0 && (
        <Tabs defaultValue="visibility" className="space-y-6">
          <TabsList>
            <TabsTrigger value="visibility">Visibility</TabsTrigger>
            <TabsTrigger value="sources">Sources</TabsTrigger>
            <TabsTrigger value="answers">Answers</TabsTrigger>
            <TabsTrigger value="stability">Stability and accuracy</TabsTrigger>
          </TabsList>

          <TabsContent value="visibility" className="space-y-8">
            <div className="grid grid-cols-2 gap-6 lg:grid-cols-4">
              <Metric label="Mention rate" rows={all} pick={(r) => r.mention_rate} format={(v) => pct(v)} hint="" />
              <Metric label="Share of voice" rows={all} pick={(r) => r.share_of_voice} format={(v) => pct(v)} hint="" />
              <Metric
                label="Average list position"
                rows={all}
                pick={(r) => r.avg_rank}
                format={(v) => (v == null ? "–" : `#${num(v)}`)}
                lowerIsBetter
                hint="Not named in a list"
              />
              <Metric
                label="Positive mentions"
                rows={all}
                pick={(r) => r.positive_rate}
                format={(v) => pct(v)}
                hint="Run sentiment labels to fill this"
              />
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <Panel title="Mention rate by brand" note={`${all[0]?.n_responses ?? 0} answers in this run.`}>
                <BrandBars
                  data={[Object.fromEntries([["x", "All answers"], ...all.map((r) => [r.brand, r.mention_rate])])]}
                  x="x"
                  series={brands}
                  height={240}
                />
              </Panel>
              <Panel title="Average position when listed" note="Lower is better: #1 is the first item in a list.">
                <BrandBars
                  data={[Object.fromEntries([["x", "Average rank"], ...all.map((r) => [r.brand, r.avg_rank])])]}
                  x="x"
                  series={brands}
                  percent={false}
                  height={240}
                />
              </Panel>
            </div>

            <Panel title="By category" note="Each category has only a few questions, so read single values with care.">
              <BrandBars data={byCat} x="category" series={brands.length ? brands : BRAND_ORDER} height={300} />
            </Panel>
          </TabsContent>

          <TabsContent value="sources" className="space-y-6">
            {sources.length ? (
              <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
                <Panel title="Most cited sites" note="Citations across every answer in this run.">
                  <RankBars data={sources} />
                </Panel>
                <Panel title="Kind of source" note="Share of all citations.">
                  <ul className="space-y-3">
                    {sourceTypes.map((s) => (
                      <li key={s.type}>
                        <div className="mb-1 flex justify-between text-sm">
                          <span>{humanise(s.type)}</span>
                          <span className="num text-muted-foreground">
                            {pct(s.share)} · {s.n}
                          </span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${s.share * 100}%`,
                              background: DOMAIN_TYPE_COLOR[s.type] ?? DOMAIN_TYPE_COLOR.unclassified,
                            }}
                          />
                        </div>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-4 text-xs text-muted-foreground">
                    Site types come from data/reference/domains_v1.csv. Add rows there to classify more sites.
                  </p>
                </Panel>
              </div>
            ) : (
              <Empty title="No citations in this run" />
            )}
          </TabsContent>

          <TabsContent value="answers">{runId && <Answers runId={runId} target={target} />}</TabsContent>

          <TabsContent value="stability" className="grid gap-6 lg:grid-cols-2">
            <Panel
              title="Answer stability"
              note="When a question is repeated, how often does the engine agree on whether to name the brand?"
            >
              {vis.data.repeatability.length ? (
                <ul className="space-y-3">
                  {sortBrands(vis.data.repeatability).map((r) => (
                    <li key={r.brand} className="flex items-center justify-between gap-4">
                      <BrandChip brand={r.brand} />
                      <span className="num text-sm">
                        {pct(r.agreement_rate)} agreement · {r.n_prompts} questions
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty title="Needs repeats">Start a run with 2 or more repeats to measure stability.</Empty>
              )}
            </Panel>
            <Panel title="Fact accuracy" note="Stated facts checked against verified reference facts.">
              {vis.data.accuracy.length ? (
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted-foreground">
                    <tr className="border-b">
                      <th className="py-2 font-normal">Subject</th>
                      <th className="font-normal">Fact</th>
                      <th className="text-right font-normal">Correct</th>
                      <th className="text-right font-normal">Wrong</th>
                    </tr>
                  </thead>
                  <tbody className="num">
                    {vis.data.accuracy.map((a) => (
                      <tr key={a.subject + a.attribute} className="border-b last:border-0">
                        <td className="py-2">{a.subject}</td>
                        <td>{humanise(a.attribute)}</td>
                        <td className="text-right">{a.n_match}</td>
                        <td className={cn("text-right", a.n_mismatch && "text-loss")}>{a.n_mismatch}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <Empty title="No verified facts yet">
                  Add products and facts with a source to data/reference/products_v1.csv and reference_facts_v1.csv, then
                  measure with accuracy checks.
                </Empty>
              )}
            </Panel>
          </TabsContent>
        </Tabs>
      )}

      {vis.data && !all.length && run?.diagnosed === false && null}
    </div>
  );
}

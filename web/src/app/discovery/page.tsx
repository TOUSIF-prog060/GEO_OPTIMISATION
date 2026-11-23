"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AskOwnQuestion } from "@/components/ask";
import { Empty, ErrorNote, JobBar, Loading, PageHeader, Panel, StatusPill } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi, useJob } from "@/hooks/use-api";
import { api, type DiscoveryPlan, type Panel as PanelT, type Run, type Status } from "@/lib/api";
import { humanise, providerLabel, usd, when } from "@/lib/format";
import { cn } from "@/lib/utils";

export default function DiscoveryPage() {
  const { data: panels, error } = useApi<PanelT[]>("/panels");
  const { data: status } = useApi<Status>("/status");
  const runs = useApi<Run[]>("/runs");

  const [version, setVersion] = useState("v0");
  const [chosenPick, setChosen] = useState<string[] | null>(null);
  const [limit, setLimit] = useState(5);
  const [repeats, setRepeats] = useState(1);
  const [category, setCategory] = useState<string | null>(null);
  const [plan, setPlan] = useState<DiscoveryPlan | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);

  const discovery = useJob(() => runs.reload());
  const diagnose = useJob(() => runs.reload());

  // Default: every engine that has a key.
  const chosen = useMemo(
    () => chosenPick ?? status?.providers.filter((p) => p.has_key).map((p) => p.name) ?? [],
    [chosenPick, status],
  );

  const panel = panels?.find((p) => p.version === version);
  const categories = useMemo(() => [...new Set(panel?.prompts.map((p) => p.category))].sort(), [panel]);
  const shown = panel?.prompts.filter((p) => !category || p.category === category) ?? [];

  const body = useMemo(
    () => ({ panel_version: version, providers: chosen, limit: limit || null, repeats }),
    [version, chosen, limit, repeats],
  );

  useEffect(() => {
    if (!chosen.length) return;
    api
      .post<DiscoveryPlan>("/discovery/plan", body)
      .then((p) => {
        setPlan(p);
        setPlanError(null);
      })
      .catch((e: Error) => setPlanError(e.message));
  }, [body, chosen.length]);

  if (error) return <ErrorNote message={error} />;
  if (!panels || !status) return <Loading />;

  const shownPlan = chosen.length ? plan : null;
  const blocked = !chosen.length || !shownPlan || shownPlan.missing_keys.length > 0 || discovery.busy;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Ask the engines"
        lede="Ask your own question and compare the engines' answers side by side, or run the fixed question panel that the headline numbers are built on. Every answer is stored exactly as it came back."
      />

      <Tabs defaultValue="own" className="gap-6">
        <TabsList>
          <TabsTrigger value="own">Your own question</TabsTrigger>
          <TabsTrigger value="panel">Question panel ({panel?.prompts.length ?? 0})</TabsTrigger>
        </TabsList>

        <TabsContent value="own">
          <AskOwnQuestion status={status} categories={categories} onFinished={runs.reload} />
        </TabsContent>

        <TabsContent value="panel">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
            <Panel
              title={`Prompt panel ${version}`}
              note={`${panel?.prompts.length ?? 0} questions across ${categories.length} categories. Edit data/reference/prompt_panel_${version}.csv to change them.`}
              action={
                panels.length > 1 && (
                  <select
                    className="rounded-md border bg-background px-2 py-1 text-sm"
                    value={version}
                    onChange={(e) => setVersion(e.target.value)}
                    aria-label="Panel version"
                  >
                    {panels.map((p) => (
                      <option key={p.version}>{p.version}</option>
                    ))}
                  </select>
                )
              }
            >
              <div className="mb-4 flex flex-wrap gap-1.5">
                {[null, ...categories].map((c) => (
                  <button
                    key={c ?? "all"}
                    onClick={() => setCategory(c)}
                    className={cn(
                      "rounded-full border px-3 py-1 text-xs capitalize transition-colors",
                      category === c ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted",
                    )}
                  >
                    {c ? c.replaceAll("_", " ") : "All"}
                  </button>
                ))}
              </div>
              <ol className="max-h-[440px] divide-y overflow-y-auto pr-1">
                {shown.map((p) => (
                  <li key={p.prompt_id} className="flex gap-3 py-2.5 text-sm">
                    <span className="num w-6 shrink-0 text-right text-xs text-muted-foreground">
                      {panel!.prompts.indexOf(p) + 1}
                    </span>
                    <div className="min-w-0">
                      <p
                        className={cn(limit && panel!.prompts.indexOf(p) >= limit && "text-muted-foreground")}
                      >
                        {p.text}
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {humanise(p.category)} · {humanise(p.intent)}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            </Panel>

            <Panel title="New run" className="h-fit lg:sticky lg:top-6">
              <fieldset className="space-y-2.5">
                <legend className="mb-2 text-sm font-medium">Engines</legend>
                {status.providers.map((p) => (
                  <label
                    key={p.name}
                    className={cn("flex items-center gap-3 text-sm", !p.has_key && "text-muted-foreground")}
                  >
                    <Checkbox
                      checked={chosen.includes(p.name)}
                      disabled={!p.has_key}
                      onCheckedChange={(v) =>
                        setChosen(v ? [...chosen, p.name] : chosen.filter((x) => x !== p.name))
                      }
                    />
                    <span className="flex-1">{providerLabel(p.name)}</span>
                    <span className="text-xs text-muted-foreground">
                      {p.has_key ? p.model : "add key in .env"}
                    </span>
                  </label>
                ))}
              </fieldset>

              <div className="mt-5 grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="limit">Questions</Label>
                  <Input
                    id="limit"
                    type="number"
                    min={1}
                    max={panel?.prompts.length}
                    value={limit}
                    onChange={(e) => setLimit(Number(e.target.value))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="repeats">Repeats</Label>
                  <Input
                    id="repeats"
                    type="number"
                    min={1}
                    max={5}
                    value={repeats}
                    onChange={(e) => setRepeats(Math.max(1, Math.min(5, Number(e.target.value))))}
                  />
                </div>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Repeats ask each question more than once to measure how stable answers are.
              </p>

              <div className="mt-5 rounded-md bg-muted px-3 py-2.5 text-sm">
                {planError ? (
                  <span className="text-loss">{planError}</span>
                ) : shownPlan ? (
                  <>
                    <span className="num font-semibold">{shownPlan.n_calls}</span> billed calls:{" "}
                    {shownPlan.n_prompts} questions × {shownPlan.providers.length} engine
                    {shownPlan.providers.length === 1 ? "" : "s"} × {shownPlan.repeats} repeat
                    {shownPlan.repeats === 1 ? "" : "s"}
                  </>
                ) : (
                  "Choose at least one engine."
                )}
              </div>

              <Button
                className="mt-4 w-full"
                size="lg"
                disabled={blocked}
                onClick={() => discovery.start("/jobs/discovery", body, "Discovery")}
              >
                {discovery.busy ? "Asking…" : "Start run"}
              </Button>
              <div className="mt-3">
                <JobBar job={discovery.job} />
              </div>
            </Panel>
          </div>
        </TabsContent>
      </Tabs>

      <Panel
        title="Runs"
        note="Measure a run to turn its answers into visibility, sources and gaps. Measuring is free; it reads stored answers."
      >
        {runs.loading && !runs.data ? (
          <Loading rows={2} />
        ) : !runs.data?.length ? (
          <Empty title="No runs yet">Start a run above.</Empty>
        ) : (
          <div className="space-y-3">
            <JobBar job={diagnose.job} />
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr className="border-b">
                    <th className="py-2 font-normal">Started</th>
                    <th className="font-normal">Engine</th>
                    <th className="font-normal">Status</th>
                    <th className="text-right font-normal">Answers</th>
                    <th className="text-right font-normal">Failed</th>
                    <th className="text-right font-normal">Cost</th>
                    <th className="w-48" />
                  </tr>
                </thead>
                <tbody className="num">
                  {runs.data.map((r) => (
                    <tr key={r.run_id} className="border-b last:border-0">
                      <td className="py-2.5">{when(r.started_at)}</td>
                      <td>
                        {providerLabel(r.provider)}{" "}
                        <span className="text-xs text-muted-foreground">{r.model}</span>
                        {r.run_type !== "baseline" && (
                          <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-[0.7rem] text-muted-foreground">
                            {r.run_type === "adhoc" ? "own questions" : r.run_type}
                          </span>
                        )}
                      </td>
                      <td>
                        <StatusPill status={r.status} />
                      </td>
                      <td className="text-right">{r.n_responses - r.n_errors}</td>
                      <td className={cn("text-right", r.n_errors && "text-loss")}>{r.n_errors}</td>
                      <td className="text-right text-muted-foreground">{usd(r.cost_usd)}</td>
                      <td className="text-right">
                        {r.diagnosed ? (
                          <Button asChild size="sm" variant="ghost">
                            <Link href={`/visibility?run=${r.run_id}`}>View results</Link>
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={diagnose.busy}
                            onClick={() =>
                              diagnose.start("/jobs/diagnose", { run_id: r.run_id }, "Measuring")
                            }
                          >
                            Measure
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {runs.data.some((r) => r.n_errors > 0) && (
              <p className="text-xs text-muted-foreground">
                Failed calls are stored with their error, never dropped. A burst of failures on Gemini is
                usually its free-tier rate limit (429); use fewer questions per run or wait a minute.
              </p>
            )}
          </div>
        )}
      </Panel>
    </div>
  );
}

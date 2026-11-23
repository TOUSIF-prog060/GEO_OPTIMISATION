"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { AskOwnQuestion } from "@/components/ask";
import { PanelPicker } from "@/components/panel-picker";
import { Empty, ErrorNote, JobBar, Loading, PageHeader, Panel, StatusPill } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi, useJob } from "@/hooks/use-api";
import type { Panel as PanelT, Run, Status } from "@/lib/api";
import { providerLabel, usd, when } from "@/lib/format";
import { cn } from "@/lib/utils";

export default function DiscoveryPage() {
  const { data: panels, error } = useApi<PanelT[]>("/panels");
  const { data: status } = useApi<Status>("/status");
  const runs = useApi<Run[]>("/runs");

  const diagnose = useJob(() => runs.reload());
  const categories = useMemo(
    () => [...new Set(panels?.flatMap((p) => p.prompts.map((q) => q.category)))].sort(),
    [panels],
  );
  const nPanel = panels?.[0]?.prompts.length ?? 0;
  // Tabs render only after data loads in the browser, so reading the URL here is safe.
  const [tab, setTab] = useState(() =>
    typeof window !== "undefined" && new URLSearchParams(window.location.search).get("tab") === "panel"
      ? "panel"
      : "own",
  );
  const changeTab = (t: string) => {
    setTab(t);
    window.history.replaceState(null, "", t === "panel" ? "?tab=panel" : window.location.pathname);
  };

  if (error) return <ErrorNote message={error} />;
  if (!panels || !status) return <Loading />;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Ask the engines"
        lede="Ask your own question and compare the engines' answers side by side, or run the fixed question panel that the headline numbers are built on. Every answer is stored exactly as it came back."
      />

      <Tabs value={tab} onValueChange={changeTab} className="gap-6">
        <TabsList>
          <TabsTrigger value="own">Your own question</TabsTrigger>
          <TabsTrigger value="panel">Question panel ({nPanel})</TabsTrigger>
        </TabsList>

        <TabsContent value="own">
          <AskOwnQuestion status={status} categories={categories} onFinished={runs.reload} />
        </TabsContent>

        <TabsContent value="panel">
          <p className="mb-5 max-w-3xl text-sm text-muted-foreground">
            The fixed questions behind the headline numbers. Tick the ones to ask, by question or by whole
            category. Edit data/reference/prompt_panel_v0.csv to change the list.
          </p>
          <PanelPicker panels={panels} status={status} onFinished={runs.reload} />
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

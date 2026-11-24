"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Empty, ErrorNote, JobBar, Loading, PageHeader, Panel, RunSelect, StatusPill } from "@/components/bits";
import { ExperimentBars } from "@/components/charts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi, useJob } from "@/hooks/use-api";
import { api, type Experiment, type ExperimentResult, type Run, type Variant } from "@/lib/api";
import { brandColor, sortBrands } from "@/lib/brands";
import { pct, pts, when } from "@/lib/format";
import { cn } from "@/lib/utils";

function Results({ id }: { id: string }) {
  const { data, loading, error } = useApi<ExperimentResult[]>(`/experiments/${id}/results`);
  if (error) return <ErrorNote message={error} />;
  if (loading || !data) return <Loading rows={2} />;
  if (!data.length) return <Empty title="No results yet">Run the re-test to compare with the baseline.</Empty>;
  const rows = sortBrands(data);
  const chart = rows.map((r) => ({
    brand: r.brand,
    baseline: r.baseline_value,
    retest: r.retest_value,
    err: [
      r.delta != null && r.ci_low != null ? Math.max(0, r.delta - r.ci_low) : 0,
      r.delta != null && r.ci_high != null ? Math.max(0, r.ci_high - r.delta) : 0,
    ] as [number, number],
  }));
  return (
    <div className="space-y-6">
      <ExperimentBars data={chart} />
      <ul className="space-y-3">
        {rows.map((r) => (
          <li key={r.brand} className="grid gap-1 border-l-2 pl-4 sm:grid-cols-[160px_1fr]" style={{ borderColor: brandColor(r.brand) }}>
            <div>
              <p className="text-sm font-medium">{r.brand}</p>
              <p className="num text-xs text-muted-foreground">
                {pct(r.baseline_value)} → {pct(r.retest_value)}
              </p>
            </div>
            <div className="text-sm">
              <p className="num">
                <span className={cn("font-semibold", (r.delta ?? 0) > 0 ? "text-gain" : (r.delta ?? 0) < 0 ? "text-loss" : "")}>
                  {pts(r.delta)}
                </span>{" "}
                <span className="text-muted-foreground">
                  95% CI {pts(r.ci_low)} to {pts(r.ci_high)} · p = {r.p_value == null ? "–" : r.p_value.toFixed(3)} · n{" "}
                  {r.n_baseline} → {r.n_retest}
                </span>
              </p>
              {r.interpretation && <p className="mt-1 text-muted-foreground">{r.interpretation}</p>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function ExperimentsPage() {
  const exps = useApi<Experiment[]>("/experiments");
  const runs = useApi<Run[]>("/runs");
  const variants = useApi<Variant[]>("/variants");
  const [selectedPick, setSelected] = useState<string>();
  const [design, setDesign] = useState<"content_variant" | "repeat_baseline">("repeat_baseline");
  const [baseline, setBaseline] = useState<string>();
  const [variant, setVariant] = useState<string>();
  const [repeats, setRepeats] = useState(3);
  const retest = useJob(() => exps.reload());

  const selected = selectedPick ?? exps.data?.[0]?.experiment_id;

  const approved = variants.data?.filter((v) => v.status === "approved") ?? [];
  const exp = exps.data?.find((e) => e.experiment_id === selected);

  const plan = async () => {
    const v = approved.find((x) => x.variant_id === variant);
    try {
      const out = await api.post<{ experiment_id: string }>("/experiments", {
        baseline_run_id: baseline,
        design,
        variant_id: design === "content_variant" ? variant : null,
        opportunity_id: design === "content_variant" ? v?.opportunity_id : null,
      });
      toast.success("Re-test planned");
      exps.reload();
      setSelected(out.experiment_id);
    } catch (e) {
      toast.error("Could not plan the re-test", { description: (e as Error).message });
    }
  };

  return (
    <div className="space-y-8">
      <PageHeader
        title="Re-test"
        lede="After a change goes live, ask the same questions again and compare with the baseline. A repeat baseline (no change) shows how much answers move on their own, so you know what counts as a real shift."
      />

      <div className="grid gap-6 lg:grid-cols-[380px_minmax(0,1fr)]">
        <div className="space-y-6">
          <Panel title="Plan a re-test">
            <Tabs value={design} onValueChange={(v) => setDesign(v as typeof design)}>
              <TabsList className="w-full">
                <TabsTrigger value="repeat_baseline">Measure noise</TabsTrigger>
                <TabsTrigger value="content_variant">Test a change</TabsTrigger>
              </TabsList>
            </Tabs>
            <div className="mt-4 space-y-3">
              <div className="space-y-1.5">
                <Label>Baseline run</Label>
                {runs.data && (
                  <RunSelect runs={runs.data.filter((r) => r.run_type === "baseline")} value={baseline} onChange={setBaseline} onlyDiagnosed />
                )}
              </div>
              {design === "content_variant" && (
                <div className="space-y-1.5">
                  <Label>Approved draft that went live</Label>
                  {approved.length ? (
                    <Select value={variant} onValueChange={setVariant}>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Choose a draft" />
                      </SelectTrigger>
                      <SelectContent>
                        {approved.map((v) => (
                          <SelectItem key={v.variant_id} value={v.variant_id}>
                            {v.title}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <p className="text-sm text-muted-foreground">Approve a draft on the Draft content page first.</p>
                  )}
                </div>
              )}
              <Button hint="Set up a before-and-after test using the round you picked as the 'before'. Nothing is sent yet."
                className="w-full"
                disabled={!baseline || (design === "content_variant" && !variant)}
                onClick={plan}
              >
                Plan re-test
              </Button>
            </div>
          </Panel>

          <Panel title="Re-tests">
            {exps.error && <ErrorNote message={exps.error} />}
            {exps.data && !exps.data.length && <p className="text-sm text-muted-foreground">None planned yet.</p>}
            <ul className="divide-y">
              {exps.data?.map((e) => (
                <li key={e.experiment_id}>
                  <button
                    onClick={() => setSelected(e.experiment_id)}
                    className={cn(
                      "flex w-full items-center gap-3 px-2 py-2.5 text-left text-sm hover:bg-muted/60",
                      selected === e.experiment_id && "bg-accent",
                    )}
                  >
                    <span className="min-w-0 flex-1 truncate">
                      {e.design === "repeat_baseline" ? "Noise check" : e.variant ?? "Change test"}
                    </span>
                    <span className="text-xs text-muted-foreground">{e.n_prompts} q</span>
                    <StatusPill status={e.status} />
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
        </div>

        <div className="min-w-0">
          {exp ? (
            <Panel
              title={exp.design === "repeat_baseline" ? "Noise check" : exp.variant ?? "Change test"}
              note={`${exp.n_prompts} questions · planned ${when(exp.created_at)}${exp.completed_at ? ` · done ${when(exp.completed_at)}` : ""}`}
            >
              {exp.hypothesis && <p className="mb-5 max-w-[70ch] text-sm text-muted-foreground">{exp.hypothesis}</p>}
              {exp.status !== "done" && (
                <div className="mb-6 flex flex-wrap items-end gap-3 rounded-md bg-muted p-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="reps">Repeats</Label>
                    <Input
                      id="reps"
                      type="number"
                      min={1}
                      max={5}
                      className="w-24"
                      value={repeats}
                      onChange={(e) => setRepeats(Number(e.target.value))}
                    />
                  </div>
                  <Button hint="Ask the same questions again now, so the answers can be compared with the 'before' round. Uses paid API calls."
                    disabled={retest.busy}
                    onClick={() =>
                      retest.start(`/jobs/experiments/${exp.experiment_id}/retest`, { repeats }, "Re-test")
                    }
                  >
                    Run re-test ({exp.n_prompts * repeats} billed calls)
                  </Button>
                  <div className="w-full">
                    <JobBar job={retest.job} />
                  </div>
                </div>
              )}
              <Results id={exp.experiment_id} key={`${exp.experiment_id}-${exp.status}`} />
              <p className="mt-6 text-xs text-muted-foreground">
                Observational comparison on the same questions and engine. It shows whether answers changed, not
                that the change caused it.
              </p>
            </Panel>
          ) : (
            <Empty title="No re-test selected">Plan one on the left.</Empty>
          )}
        </div>
      </div>
    </div>
  );
}

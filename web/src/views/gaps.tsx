"use client";

import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Empty, ErrorNote, JobBar, Loading, PageHeader, Panel, RunSelect, StatusPill } from "@/components/bits";
import { ReviewerField, useReviewer } from "@/components/reviewer";
import { Term } from "@/components/help";
import { Button } from "@/components/ui/button";
import { useApi, useJob } from "@/hooks/use-api";
import { api, type Evidence, type Opportunity, type Run } from "@/lib/api";
import { humanise, num, pct, providerLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

const RATE_METRICS = new Set(["mention_rate", "citation_share", "positive_rate", "share_of_voice", "accuracy_rate", "agreement_rate"]);

function Compare({ o }: { o: Opportunity }) {
  if (o.target_value == null || o.benchmark_value == null) return null;
  const isRate = RATE_METRICS.has(o.metric_name ?? "");
  const max = isRate ? 1 : Math.max(o.target_value, o.benchmark_value) * 1.15 || 1;
  const fmt = (v: number) => (isRate ? pct(v) : `#${num(v)}`);
  const bar = (label: string, v: number, color: string) => (
    <div className="flex items-center gap-3 text-xs">
      <span className="w-24 shrink-0 text-muted-foreground">{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full" style={{ width: `${(v / max) * 100}%`, background: color }} />
      </div>
      <span className="num w-12 text-right">{fmt(v)}</span>
    </div>
  );
  return (
    <div className="space-y-1.5">
      <p className="text-xs text-muted-foreground">{humanise(o.metric_name)}</p>
      {bar("Sephora India", o.target_value, "var(--brand-sephora)")}
      {bar("Benchmark", o.benchmark_value, "var(--chart-5)")}
    </div>
  );
}

function EvidenceList({ id }: { id: string }) {
  const { data, loading, error } = useApi<Evidence[]>(`/opportunities/${id}/evidence`);
  if (error) return <ErrorNote message={error} />;
  if (loading || !data) return <Loading rows={2} />;
  return (
    <ul className="space-y-3">
      {data.map((e) => (
        <li key={e.response_id} className="rounded-md border bg-background p-3">
          <p className="text-sm font-medium">{e.prompt}</p>
          <p className="mt-1 text-xs text-muted-foreground">{providerLabel(e.provider)}</p>
          <p className="mt-2 max-w-[75ch] whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
            {e.answer}
            {e.answer.length >= 600 && "…"}
          </p>
        </li>
      ))}
    </ul>
  );
}

export default function OpportunitiesPage() {
  const runs = useApi<Run[]>("/runs");
  const [runId, setRunId] = useState<string>();
  const opps = useApi<Opportunity[]>(`/opportunities${runId ? `?run_id=${runId}` : ""}`);
  const [reviewer, setReviewer] = useReviewer();
  const [open, setOpen] = useState<string | null>(null);
  const [type, setType] = useState<string | null>(null);
  const find = useJob(() => opps.reload());

  const types = useMemo(() => {
    const m = new Map<string, number>();
    for (const o of opps.data ?? []) m.set(o.gap_type, (m.get(o.gap_type) ?? 0) + 1);
    return [...m.entries()];
  }, [opps.data]);

  const review = async (o: Opportunity, status: "approved" | "rejected") => {
    if (!o.recommendation_id) return;
    try {
      await api.post(`/recommendations/${o.recommendation_id}/review`, { status, reviewer });
      toast.success(status === "approved" ? "Action approved" : "Action rejected");
      opps.reload();
    } catch (e) {
      toast.error("Review not saved", { description: (e as Error).message });
    }
  };

  const diagnosed = runs.data?.filter((r) => r.diagnosed) ?? [];
  const shown = (opps.data ?? []).filter((o) => !type || o.gap_type === type);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Find gaps"
        lede="Where Sephora India is missing, ranked lower, cited less or described wrongly, each backed by the answers that show it. Gaps come from fixed rules, not an AI, and cost nothing to find."
        actions={<ReviewerField value={reviewer} onChange={setReviewer} />}
      />

      <Panel quiet>
        <div className="flex flex-wrap items-center gap-3">
          {runs.data && (
            <RunSelect runs={runs.data} value={runId} onChange={setRunId} onlyDiagnosed />
          )}
          <Button hint="Compares Sephora with competitors in this round and lists where it falls behind. Pick a measured round first."
            disabled={!runId || find.busy}
            onClick={() => find.start("/jobs/opportunities", { run_id: runId }, "Finding gaps")}
          >
            Find gaps in this run
          </Button>
          {runId && (
            <Button hint="Stop filtering and show gaps from every round." variant="ghost" onClick={() => setRunId(undefined)}>
              Show all runs
            </Button>
          )}
          {!diagnosed.length && runs.data && (
            <span className="text-sm text-muted-foreground">Measure a run first.</span>
          )}
        </div>
        <div className="mt-3 max-w-md">
          <JobBar job={find.job} />
        </div>
      </Panel>

      {opps.error && <ErrorNote message={opps.error} />}
      {opps.loading && !opps.data && <Loading />}

      {opps.data && !opps.data.length && (
        <Empty title="No gaps found">
          Either Sephora India keeps up with competitors in this run, or the run is too small for the rules to be
          confident. Try a larger run.
        </Empty>
      )}

      {types.length > 1 && (
        <div className="flex flex-wrap gap-1.5">
          {[[null, opps.data?.length ?? 0] as const, ...types].map(([t, n]) => (
            <button
              key={t ?? "all"}
              onClick={() => setType(t)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs",
                type === t ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted",
              )}
            >
              {t ? humanise(t) : "All"} <span className="num opacity-70">{n}</span>
            </button>
          ))}
        </div>
      )}

      <ol className="space-y-4">
        {shown.map((o, i) => {
          const isOpen = open === o.opportunity_id;
          return (
            <li key={o.opportunity_id} className="rounded-lg border bg-card">
              <div className="grid gap-5 p-5 md:grid-cols-[72px_minmax(0,1fr)_260px]">
                <div>
                  <p className="num font-[family-name:var(--font-bricolage)] text-4xl font-semibold leading-none text-primary">
                    {num(o.priority_score, 0)}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">priority #{i + 1}</p>
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-muted-foreground">{humanise(o.gap_type)}</span>
                    {o.category && <span className="text-xs capitalize text-muted-foreground">in {o.category}</span>}
                  </div>
                  <h3 className="mt-1 text-lg font-semibold leading-snug">{o.title}</h3>
                  {o.rationale && <p className="mt-2 max-w-[70ch] text-sm text-muted-foreground">{o.rationale}</p>}
                  <dl className="num mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs">
                    <div>
                      <dt className="inline text-muted-foreground"><Term term="confidence">Confidence</Term> </dt>
                      <dd className="inline font-medium">{pct(o.confidence)}</dd>
                    </div>
                    <div>
                      <dt className="inline text-muted-foreground">Effort </dt>
                      <dd className="inline font-medium">{o.effort ?? "–"}</dd>
                    </div>
                    <div>
                      <dt className="inline text-muted-foreground">Severity </dt>
                      <dd className="inline font-medium">{pct(o.severity)}</dd>
                    </div>
                  </dl>
                </div>
                <Compare o={o} />
              </div>

              {o.action && (
                <div className="flex flex-col gap-3 border-t px-5 py-4 sm:flex-row sm:items-center">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-muted-foreground">Suggested action</p>
                    <p className="mt-0.5 text-sm">{o.action}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {o.rec_status && o.rec_status !== "proposed" && (
                      <span className="text-xs text-muted-foreground">
                        <StatusPill status={o.rec_status} /> {o.reviewed_by && `by ${o.reviewed_by}`}
                      </span>
                    )}
                    <Button hint="Mark this fix as not worth doing. Your initials are recorded."
                      size="sm"
                      variant="outline"
                      disabled={!reviewer}
                      title={reviewer ? undefined : "Enter your initials first"}
                      onClick={() => review(o, "rejected")}
                    >
                      Reject
                    </Button>
                    <Button hint="Agree this fix is worth doing. It can then be drafted in Write content. Your initials are recorded."
                      size="sm"
                      disabled={!reviewer}
                      title={reviewer ? undefined : "Enter your initials first"}
                      onClick={() => review(o, "approved")}
                    >
                      Approve
                    </Button>
                  </div>
                </div>
              )}

              <button
                className="flex w-full items-center gap-2 border-t px-5 py-3 text-left text-sm text-muted-foreground hover:text-foreground"
                onClick={() => setOpen(isOpen ? null : o.opportunity_id)}
                aria-expanded={isOpen}
              >
                <ChevronDown className={cn("size-4 transition-transform", isOpen && "rotate-180")} />
                {isOpen ? "Hide" : "Show"} the {o.n_evidence} answers behind this
              </button>
              {isOpen && (
                <div className="border-t bg-muted/30 p-5">
                  {o.validation_approach && (
                    <p className="mb-4 text-sm">
                      <span className="text-muted-foreground">How to check it: </span>
                      {o.validation_approach}
                    </p>
                  )}
                  <EvidenceList id={o.opportunity_id} />
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

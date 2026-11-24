"use client";

import { useState } from "react";

import { Empty, ErrorNote, JobBar, Loading, PageHeader, Panel, StatusPill } from "@/components/bits";
import { ReviewerField, useReviewer } from "@/components/reviewer";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi, useJob } from "@/hooks/use-api";
import type { AgentDetail, AgentRun, Run, Status } from "@/lib/api";
import { humanise, providerLabel, when } from "@/lib/format";
import { cn } from "@/lib/utils";

const STAGES = ["discover", "diagnose", "opportunities", "draft", "human_review", "plan_experiments", "report"];

function Timeline({ detail }: { detail: AgentDetail }) {
  const log = detail.values.log ?? [];
  const reached = new Set(log.map((l) => l.node));
  return (
    <ol className="relative space-y-4 border-l pl-6">
      {STAGES.map((s) => {
        const events = log.filter((l) => l.node === s);
        const waiting = s === "human_review" && detail.status === "awaiting_review";
        const done = reached.has(s) && !waiting;
        return (
          <li key={s} className="relative">
            <span
              className={cn(
                "absolute -left-[31px] top-1 size-3 rounded-full border-2 bg-background",
                done && "border-primary bg-primary",
                waiting && "border-[color:var(--chart-4)] bg-[color:var(--chart-4)]",
              )}
            />
            <p className={cn("text-sm font-medium", !done && !waiting && "text-muted-foreground")}>
              {humanise(s)}
              {waiting && " · waiting for you"}
            </p>
            {events.map((e, i) => (
              <p key={i} className="mt-0.5 text-xs text-muted-foreground">
                {e.message}
              </p>
            ))}
          </li>
        );
      })}
    </ol>
  );
}

function Review({ detail, reviewer, onDone }: { detail: AgentDetail; reviewer: string; onDone: () => void }) {
  const drafts = detail.pending[0]?.drafts ?? [];
  const [choice, setChoice] = useState<Record<string, "approve" | "reject" | "skip">>({});
  const resume = useJob(onDone);
  return (
    <Panel title="Your review" note="Read the drafts on the Draft content page, then decide here. The agent continues only after you submit.">
      <ul className="space-y-3">
        {drafts.map((d) => (
          <li key={d.variant_id} className="flex flex-wrap items-center gap-3">
            <span className="min-w-0 flex-1 text-sm">
              {d.title} {!d.grounded && <span className="text-xs text-loss">(not fully grounded)</span>}
            </span>
            <Tabs
              value={choice[d.variant_id] ?? "skip"}
              onValueChange={(v) => setChoice((c) => ({ ...c, [d.variant_id]: v as "approve" | "reject" | "skip" }))}
            >
              <TabsList>
                <TabsTrigger value="skip">Skip</TabsTrigger>
                <TabsTrigger value="reject">Reject</TabsTrigger>
                <TabsTrigger value="approve">Approve</TabsTrigger>
              </TabsList>
            </Tabs>
          </li>
        ))}
        {!drafts.length && <p className="text-sm text-muted-foreground">No drafts were produced.</p>}
      </ul>
      <Button hint="Send your approve/reject choices back to the agent so it can finish. Enter your initials first."
        className="mt-4"
        disabled={!reviewer || resume.busy}
        onClick={() =>
          resume.start(
            `/jobs/agent/${detail.thread_id}/resume`,
            {
              approved: Object.keys(choice).filter((k) => choice[k] === "approve"),
              rejected: Object.keys(choice).filter((k) => choice[k] === "reject"),
              reviewer,
            },
            "Resuming agent",
          )
        }
      >
        Submit review and continue
      </Button>
      {!reviewer && <p className="mt-2 text-xs text-muted-foreground">Enter your initials at the top first.</p>}
      <div className="mt-3">
        <JobBar job={resume.job} />
      </div>
    </Panel>
  );
}

export default function AgentPage() {
  const history = useApi<AgentRun[]>("/agent/runs");
  const runs = useApi<Run[]>("/runs");
  const { data: status } = useApi<Status>("/status");
  const [reviewer, setReviewer] = useReviewer();
  const [mode, setMode] = useState<"reuse" | "new">("reuse");
  const [picked, setPicked] = useState<string[]>([]);
  const [providerPick, setProviders] = useState<string[] | null>(null);
  const [limit, setLimit] = useState(5);
  const [maxDrafts, setMaxDrafts] = useState(3);
  const [threadPick, setThread] = useState<string>();
  const thread = threadPick ?? history.data?.[0]?.thread_id;
  const providers = providerPick ?? status?.providers.filter((p) => p.has_key).map((p) => p.name) ?? [];
  const detail = useApi<AgentDetail>(thread ? `/agent/runs/${thread}` : null);

  const agent = useJob((j) => {
    history.reload();
    const tid = (j.result as { thread_id?: string } | null)?.thread_id;
    if (tid) setThread(tid);
  });


  const diagnosed = runs.data?.filter((r) => r.diagnosed) ?? [];
  const body =
    mode === "reuse"
      ? { run_ids: picked, max_drafts: maxDrafts }
      : { providers, limit, repeats: 1, max_drafts: maxDrafts };

  return (
    <div className="space-y-8">
      <PageHeader
        title="Run the agent"
        lede="The agent runs the whole loop for you: ask, measure, find gaps and draft. Then it stops and waits for your review before planning re-tests. It only calls the same steps you can run by hand."
        actions={<ReviewerField value={reviewer} onChange={setReviewer} />}
      />

      <div className="grid gap-6 lg:grid-cols-[380px_minmax(0,1fr)]">
        <Panel title="Start" className="h-fit">
          <Tabs value={mode} onValueChange={(v) => setMode(v as "reuse" | "new")}>
            <TabsList className="w-full">
              <TabsTrigger value="reuse">Use existing runs</TabsTrigger>
              <TabsTrigger value="new">Ask again</TabsTrigger>
            </TabsList>
          </Tabs>

          {mode === "reuse" ? (
            <fieldset className="mt-4 space-y-2">
              <legend className="mb-2 text-sm text-muted-foreground">No new AI calls for answers.</legend>
              {diagnosed.map((r) => (
                <label key={r.run_id} className="flex items-center gap-3 text-sm">
                  <Checkbox
                    checked={picked.includes(r.run_id)}
                    onCheckedChange={(v) =>
                      setPicked((p) => (v ? [...p, r.run_id] : p.filter((x) => x !== r.run_id)))
                    }
                  />
                  {providerLabel(r.provider)} · {when(r.started_at)}
                </label>
              ))}
              {!diagnosed.length && <p className="text-sm text-muted-foreground">No measured runs yet.</p>}
            </fieldset>
          ) : (
            <div className="mt-4 space-y-3">
              {status?.providers.map((p) => (
                <label key={p.name} className={cn("flex items-center gap-3 text-sm", !p.has_key && "text-muted-foreground")}>
                  <Checkbox
                    checked={providers.includes(p.name)}
                    disabled={!p.has_key}
                    onCheckedChange={(v) =>
                      setProviders(v ? [...providers, p.name] : providers.filter((x) => x !== p.name))
                    }
                  />
                  {providerLabel(p.name)}
                  {!p.has_key && <span className="text-xs">no key</span>}
                </label>
              ))}
              <div className="space-y-1.5">
                <Label htmlFor="alimit">Questions (billed)</Label>
                <Input id="alimit" type="number" min={1} value={limit} onChange={(e) => setLimit(Number(e.target.value))} />
              </div>
            </div>
          )}

          <div className="mt-4 space-y-1.5">
            <Label htmlFor="drafts">Drafts to write, at most</Label>
            <Input
              id="drafts"
              type="number"
              min={1}
              max={10}
              value={maxDrafts}
              onChange={(e) => setMaxDrafts(Number(e.target.value))}
            />
            {!status?.analysis.has_key && (
              <p className="text-xs text-muted-foreground">
                Without an OpenAI key the drafting step is skipped and logged; the rest still runs.
              </p>
            )}
          </div>

          <Button hint="Runs the whole cycle automatically: ask, measure, find gaps and draft fixes. It pauses for your approval before anything is final."
            className="mt-5 w-full"
            size="lg"
            disabled={agent.busy || (mode === "reuse" ? !picked.length : !providers.length)}
            onClick={() => agent.start("/jobs/agent", body, "Agent")}
          >
            Start agent
          </Button>
          <div className="mt-3">
            <JobBar job={agent.job} />
          </div>
        </Panel>

        <div className="min-w-0 space-y-6">
          {history.error && <ErrorNote message={history.error} />}
          {history.data && !history.data.length && <Empty title="No agent runs yet" />}
          {history.data && history.data.length > 0 && (
            <Panel title="Agent runs">
              <ul className="divide-y">
                {history.data.map((h) => (
                  <li key={h.thread_id}>
                    <button
                      className={cn(
                        "flex w-full items-center gap-3 px-2 py-2.5 text-left text-sm hover:bg-muted/60",
                        thread === h.thread_id && "bg-accent",
                      )}
                      onClick={() => setThread(h.thread_id)}
                    >
                      <span className="num flex-1 truncate">{h.thread_id}</span>
                      <span className="text-xs text-muted-foreground">{when(h.created_at)}</span>
                      <StatusPill status={h.status} />
                    </button>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          {thread && (
            <div className="grid gap-6 xl:grid-cols-2">
              <Panel title="Progress" note={thread}>
                {detail.error && <ErrorNote message={detail.error} />}
                {detail.data ? <Timeline detail={detail.data} /> : <Loading rows={3} />}
                {detail.data?.values.errors?.length ? (
                  <div className="mt-4 space-y-2">
                    {detail.data.values.errors.map((e, i) => (
                      <ErrorNote key={i} message={e} />
                    ))}
                  </div>
                ) : null}
              </Panel>
              {detail.data?.status === "awaiting_review" ? (
                <Review
                  detail={detail.data}
                  reviewer={reviewer}
                  onDone={() => {
                    detail.reload();
                    history.reload();
                  }}
                />
              ) : (
                detail.data?.values.report && (
                  <Panel title="Report">
                    <dl className="grid grid-cols-2 gap-x-6 gap-y-4">
                      {Object.entries(detail.data.values.report).map(([k, v]) => (
                        <div key={k}>
                          <dt className="text-xs text-muted-foreground">{humanise(k)}</dt>
                          <dd className="num mt-0.5 font-[family-name:var(--font-bricolage)] text-2xl font-semibold">
                            {typeof v === "object" ? JSON.stringify(v) : String(v)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </Panel>
                )
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

"use client";

import { BookOpen, CheckCircle2, CircleAlert } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Empty, ErrorNote, JobBar, Loading, PageHeader, Panel, StatusPill } from "@/components/bits";
import { ReviewerField, useReviewer } from "@/components/reviewer";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useApi, useJob } from "@/hooks/use-api";
import { api, type Knowledge, type Opportunity, type Status, type Variant } from "@/lib/api";
import { humanise, num, when } from "@/lib/format";

type Chunk = { chunk_id: number; title: string; source_url: string; text: string };

function Sources({ ids }: { ids: number[] }) {
  const { data } = useApi<Chunk[]>(ids.length ? `/chunks?ids=${ids.join(",")}` : null);
  if (!ids.length) return <p className="text-sm text-loss">The draft cites no source.</p>;
  if (!data) return <Loading rows={1} />;
  return (
    <ul className="space-y-2">
      {data.map((c) => (
        <li key={c.chunk_id} className="rounded-md border bg-background p-3 text-sm">
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="num rounded bg-muted px-1.5">[{c.chunk_id}]</span>
            <a href={c.source_url} target="_blank" rel="noreferrer" className="underline-offset-2 hover:underline">
              {c.title}
            </a>
          </p>
          <p className="mt-1.5 line-clamp-4 text-muted-foreground">{c.text}</p>
        </li>
      ))}
    </ul>
  );
}

function Draft({ v, reviewer, onChange }: { v: Variant; reviewer: string; onChange: () => void }) {
  const [open, setOpen] = useState(false);
  const g = (v.grounding ?? {}) as {
    cited_chunk_ids?: number[];
    invalid_citations?: number[];
    unsupported_claims?: string[];
    needs_more_info?: boolean;
  };
  const review = async (status: "approved" | "rejected") => {
    try {
      await api.post(`/variants/${v.variant_id}/review`, { status, reviewer });
      toast.success(status === "approved" ? "Draft approved" : "Draft rejected");
      onChange();
    } catch (e) {
      toast.error("Review not saved", { description: (e as Error).message });
    }
  };
  return (
    <article className="rounded-lg border bg-card">
      <header className="flex flex-wrap items-start gap-3 p-5 pb-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">
            {humanise(v.content_type)} · v{v.version} · for “{v.opportunity}”
          </p>
          <h3 className="mt-1 text-lg font-semibold leading-snug">{v.title}</h3>
        </div>
        <StatusPill status={v.status} />
      </header>
      <div className="px-5">
        <div
          className={`flex items-start gap-2 rounded-md px-3 py-2 text-sm ${v.grounded ? "bg-gain/10" : "bg-loss/10"}`}
        >
          {v.grounded ? (
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-gain" />
          ) : (
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-loss" />
          )}
          <div>
            <p className="font-medium">{v.grounded ? "Every claim cites an approved source" : "Needs checking before use"}</p>
            {!v.grounded && (
              <ul className="mt-1 list-disc pl-4 text-muted-foreground">
                {g.unsupported_claims?.map((c) => <li key={c}>Unsupported: {c}</li>)}
                {g.invalid_citations?.length ? <li>Cites sources that were not retrieved: {g.invalid_citations.join(", ")}</li> : null}
                {g.needs_more_info && <li>The model said it needs more information.</li>}
              </ul>
            )}
          </div>
        </div>
      </div>
      <div className="px-5 py-4">
        <div className={`max-w-[75ch] whitespace-pre-wrap text-[0.95rem] leading-relaxed ${open ? "" : "line-clamp-6"}`}>
          {v.body}
        </div>
        <button className="mt-2 text-sm text-primary hover:underline" onClick={() => setOpen(!open)}>
          {open ? "Show less" : "Read the full draft and its sources"}
        </button>
        {open && (
          <div className="mt-4">
            <p className="mb-2 flex items-center gap-1.5 text-sm font-medium">
              <BookOpen className="size-4" /> Sources cited
            </p>
            <Sources ids={g.cited_chunk_ids ?? []} />
          </div>
        )}
      </div>
      <footer className="flex flex-wrap items-center gap-2 border-t px-5 py-3">
        <span className="flex-1 text-xs text-muted-foreground">
          {when(v.created_at)}
          {v.reviewed_by && ` · reviewed by ${v.reviewed_by}`}
        </span>
        <Button hint="Send this draft back. It will not be used. Your initials are recorded." size="sm" variant="outline" disabled={!reviewer} onClick={() => review("rejected")}>
          Reject
        </Button>
        <Button hint="Accept this draft for publishing. Your initials are recorded." size="sm" disabled={!reviewer} onClick={() => review("approved")}>
          Approve
        </Button>
      </footer>
    </article>
  );
}

export default function CopilotPage() {
  const kb = useApi<Knowledge>("/knowledge");
  const opps = useApi<Opportunity[]>("/opportunities");
  const variants = useApi<Variant[]>("/variants");
  const { data: status } = useApi<Status>("/status");
  const [reviewer, setReviewer] = useReviewer();
  const [opp, setOpp] = useState<string>();
  const ingest = useJob(() => kb.reload());
  const draft = useJob(() => variants.reload());

  const noKey = status && !status.analysis.has_key;
  const noKb = (kb.data?.stats.chunks ?? 0) === 0;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Draft content"
        lede="Write FAQs, buying guides and briefs that answer a gap, using only Sephora India's approved documents. Every sentence must cite a source; anything it can't support is flagged. Nothing is published automatically."
        actions={<ReviewerField value={reviewer} onChange={setReviewer} />}
      />

      {noKey && (
        <ErrorNote message="Drafting and the knowledge base use OpenAI. Add OPENAI_API_KEY to .env and restart the API to enable this step." />
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel
          title="Approved knowledge"
          note="Markdown files in data/knowledge/ with a title, source URL and verified date."
          action={
            <Button hint="Read the approved documents in data/knowledge so drafts can quote real facts."
              size="sm"
              variant="outline"
              disabled={Boolean(noKey) || ingest.busy || !kb.data?.local_docs.length}
              onClick={() => ingest.start("/jobs/ingest", {}, "Loading documents")}
            >
              Load documents
            </Button>
          }
        >
          {kb.error && <ErrorNote message={kb.error} />}
          {kb.data && (
            <>
              <p className="num mb-3 text-sm">
                <span className="font-semibold">{kb.data.stats.documents}</span> documents,{" "}
                <span className="font-semibold">{kb.data.stats.chunks}</span> searchable passages loaded.
              </p>
              {kb.data.error && <ErrorNote message={kb.data.error} />}
              {kb.data.local_docs.length ? (
                <ul className="divide-y text-sm">
                  {kb.data.local_docs.map((d) => (
                    <li key={d.doc_id} className="flex justify-between gap-3 py-2">
                      <span className="truncate">{d.title}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">verified {d.verified_at}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty title="No documents yet">
                  Add approved Sephora India pages (policies, product facts, offers) as Markdown files in
                  data/knowledge/. See its README for the format.
                </Empty>
              )}
            </>
          )}
          <div className="mt-3">
            <JobBar job={ingest.job} />
          </div>
        </Panel>

        <Panel title="Write a draft" note="Pick a gap. The draft is written from the passages most relevant to it.">
          {opps.data && opps.data.length ? (
            <div className="space-y-3">
              <Select value={opp} onValueChange={setOpp}>
                <SelectTrigger className="w-full" aria-label="Gap">
                  <SelectValue placeholder="Choose a gap" />
                </SelectTrigger>
                <SelectContent>
                  {opps.data.map((o) => (
                    <SelectItem key={o.opportunity_id} value={o.opportunity_id}>
                      [{num(o.priority_score, 0)}] {o.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button hint="The assistant writes website content for the chosen gap, using only facts from the loaded documents."
                disabled={!opp || Boolean(noKey) || noKb || draft.busy}
                onClick={() => draft.start("/jobs/draft", { opportunity_id: opp }, "Drafting")}
              >
                Write draft
              </Button>
              {noKb && !noKey && (
                <p className="text-xs text-muted-foreground">Load approved documents first.</p>
              )}
              <JobBar job={draft.job} />
            </div>
          ) : (
            <Empty title="No gaps to write for">Find gaps on step 3 first.</Empty>
          )}
        </Panel>
      </div>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Drafts</h2>
        {variants.loading && !variants.data && <Loading />}
        {variants.data && !variants.data.length && <Empty title="No drafts yet" />}
        {variants.data?.map((v) => (
          <Draft key={v.variant_id} v={v} reviewer={reviewer} onChange={variants.reload} />
        ))}
      </section>
    </div>
  );
}

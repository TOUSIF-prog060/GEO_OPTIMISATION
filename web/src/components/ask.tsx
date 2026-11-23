"use client";

import { ChevronDown, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Empty, JobBar } from "@/components/bits";
import { Highlighted } from "@/components/highlight";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useApi, useJob } from "@/hooks/use-api";
import { api, type DiscoveryPlan, type ResponseRow, type Status } from "@/lib/api";
import { brandColor, sortBrands } from "@/lib/brands";
import { ms, providerLabel, when } from "@/lib/format";
import { cn } from "@/lib/utils";

type CustomQuestion = {
  prompt_id: string;
  text: string;
  category: string;
  n_runs: number;
  last_asked: string | null;
};

const MAX_QUESTIONS = 10;

function AnswerCard({ r }: { r: ResponseRow }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex min-w-0 flex-col rounded-lg border bg-card">
      <div className="flex items-center justify-between gap-2 border-b px-4 py-2.5">
        <span className="text-sm font-semibold">{providerLabel(r.provider)}</span>
        <span className="num text-xs text-muted-foreground">{ms(r.latency_ms)}</span>
      </div>
      {r.error ? (
        <p className="p-4 text-sm text-loss">{r.error}</p>
      ) : (
        <>
          <div className="flex flex-wrap gap-1.5 px-4 pt-3">
            {r.mentions.length ? (
              sortBrands(r.mentions).map((m) => (
                <span
                  key={m.brand}
                  className="num inline-flex rounded-full px-2 py-0.5 text-xs font-medium text-white"
                  style={{ background: brandColor(m.brand) }}
                >
                  {m.brand}
                  {m.rank ? ` · #${m.rank}` : ""}
                </span>
              ))
            ) : (
              <span className="text-xs text-muted-foreground">Names none of the three brands</span>
            )}
          </div>
          <div
            className={cn(
              "max-w-[75ch] whitespace-pre-wrap px-4 py-3 text-sm leading-relaxed",
              !open && "line-clamp-[12]",
            )}
          >
            <Highlighted text={r.answer_text ?? ""} />
          </div>
          <div className="mt-auto border-t px-4 py-2.5">
            <button
              className="flex items-center gap-1 text-sm text-primary hover:underline"
              onClick={() => setOpen(!open)}
              aria-expanded={open}
            >
              <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
              {open ? "Show less" : `Full answer and ${r.citations.length} sources`}
            </button>
            {open && r.citations.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
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
            )}
          </div>
        </>
      )}
    </div>
  );
}

function Results({ runIds }: { runIds: string[] }) {
  const { data, loading, error } = useApi<ResponseRow[]>(`/ask/answers?run_ids=${runIds.join(",")}`);
  if (error) return <p className="text-sm text-loss">{error}</p>;
  if (loading || !data) return <p className="text-sm text-muted-foreground">Loading answers…</p>;
  const byPrompt = new Map<string, ResponseRow[]>();
  for (const r of data) byPrompt.set(r.prompt_id, [...(byPrompt.get(r.prompt_id) ?? []), r]);
  return (
    <div className="space-y-8">
      {[...byPrompt.values()].map((rows) => (
        <section key={rows[0].prompt_id} className="space-y-3">
          <h3 className="max-w-3xl font-[family-name:var(--font-bricolage)] text-xl font-semibold leading-snug">
            {rows[0].prompt}
          </h3>
          <div
            className={cn(
              "grid gap-4",
              rows.length > 1 && "md:grid-cols-2",
              rows.length > 2 && "xl:grid-cols-3",
            )}
          >
            {rows.map((r) => (
              <AnswerCard key={r.response_id} r={r} />
            ))}
          </div>
        </section>
      ))}
      <p className="text-xs text-muted-foreground">
        Stored with every answer and measured automatically. These one-off runs are kept out of the Overview
        numbers, which use only the fixed question panel.{" "}
        <Link className="text-primary hover:underline" href={`/visibility?run=${runIds[0]}`}>
          Open in Measure visibility
        </Link>
      </p>
    </div>
  );
}

export function AskOwnQuestion({
  status,
  categories,
  onFinished,
}: {
  status: Status;
  categories: string[];
  onFinished: () => void;
}) {
  const past = useApi<CustomQuestion[]>("/custom-questions");
  const [text, setText] = useState("");
  const [category, setCategory] = useState("custom");
  const [again, setAgain] = useState<string[]>([]);
  const [pick, setPick] = useState<string[] | null>(null);
  const [plan, setPlan] = useState<DiscoveryPlan | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [runIds, setRunIds] = useState<string[]>([]);

  const engines = pick ?? status.providers.filter((p) => p.has_key).map((p) => p.name);
  const questions = useMemo(
    () =>
      text
        .split("\n")
        .map((q) => q.trim())
        .filter((q) => q.length > 0),
    [text],
  );
  const tooMany = questions.length > MAX_QUESTIONS;
  const hasInput = (questions.length > 0 && !tooMany) || again.length > 0;
  const body = useMemo(
    () => ({ questions: tooMany ? [] : questions, prompt_ids: again, category, providers: engines }),
    [questions, again, category, engines, tooMany],
  );

  const ask = useJob((j) => {
    const ids = (j.result as { run_ids?: string[] } | null)?.run_ids ?? [];
    if (j.status === "done") {
      setRunIds(ids);
      setText("");
      setAgain([]);
      past.reload();
      onFinished();
    }
  });

  useEffect(() => {
    if (!hasInput || !engines.length) return;
    const t = setTimeout(() => {
      api
        .post<DiscoveryPlan>("/ask/plan", body)
        .then((p) => {
          setPlan(p);
          setPlanError(null);
        })
        .catch((e: Error) => setPlanError(e.message));
    }, 300);
    return () => clearTimeout(t);
  }, [body, hasInput, engines.length]);

  const shownPlan = hasInput && engines.length ? plan : null;
  const stage = (ask.job?.progress as { stage?: string } | undefined)?.stage;

  return (
    <div className="space-y-8">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-3">
          <Label htmlFor="questions" className="text-base font-semibold">
            Your question
          </Label>
          <Textarea
            id="questions"
            rows={5}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={
              "Ask it the way a shopper would, for example:\nIs it safe to buy perfume from Sephora India online?\nWhich is cheaper for Huda Beauty, Nykaa or Tira?"
            }
            className="min-h-[140px] resize-y text-[0.95rem] leading-relaxed"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && hasInput && !ask.busy)
                ask.start("/jobs/ask", body, "Asking");
            }}
          />
          <p className={cn("text-xs", tooMany ? "text-loss" : "text-muted-foreground")}>
            One question per line, up to {MAX_QUESTIONS}.{" "}
            {questions.length > 0 && `${questions.length} typed. `}
            Ctrl + Enter to ask.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Label htmlFor="cat" className="text-sm text-muted-foreground">
              Category
            </Label>
            <Input
              id="cat"
              list="categories"
              className="w-44"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />
            <datalist id="categories">
              {["custom", ...categories].map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
            <span className="text-xs text-muted-foreground">
              Used to group results; keep “custom” if unsure.
            </span>
          </div>
        </div>

        <div className="h-fit space-y-4 rounded-lg border bg-card p-5">
          <fieldset className="space-y-2.5">
            <legend className="mb-2 text-sm font-medium">Ask these engines</legend>
            {status.providers.map((p) => (
              <label
                key={p.name}
                className={cn("flex items-center gap-3 text-sm", !p.has_key && "text-muted-foreground")}
              >
                <Checkbox
                  checked={engines.includes(p.name)}
                  disabled={!p.has_key}
                  onCheckedChange={(v) =>
                    setPick(v ? [...engines, p.name] : engines.filter((x) => x !== p.name))
                  }
                />
                <span className="flex-1">{providerLabel(p.name)}</span>
                <span className="text-xs text-muted-foreground">
                  {p.has_key ? p.model : "add key in .env"}
                </span>
              </label>
            ))}
          </fieldset>
          <div className="rounded-md bg-muted px-3 py-2.5 text-sm">
            {planError ? (
              <span className="text-loss">{planError}</span>
            ) : shownPlan ? (
              <>
                <span className="num font-semibold">{shownPlan.n_calls}</span> billed call
                {shownPlan.n_calls === 1 ? "" : "s"}: {shownPlan.n_prompts} question
                {shownPlan.n_prompts === 1 ? "" : "s"} × {shownPlan.providers.length} engine
                {shownPlan.providers.length === 1 ? "" : "s"}
              </>
            ) : (
              "Type a question and pick an engine."
            )}
          </div>
          <Button
            size="lg"
            className="w-full"
            disabled={
              !hasInput || !engines.length || !shownPlan || shownPlan.missing_keys.length > 0 || ask.busy
            }
            onClick={() => ask.start("/jobs/ask", body, "Asking")}
          >
            {ask.busy ? (stage === "measuring" ? "Measuring answers…" : "Asking…") : "Ask"}
          </Button>
          <JobBar job={ask.job} />
        </div>
      </div>

      {runIds.length > 0 && <Results runIds={runIds} key={runIds.join(",")} />}

      <div>
        <h3 className="mb-1 text-lg font-semibold">Asked before</h3>
        <p className="mb-3 text-sm text-muted-foreground">
          Tick questions to ask them again. The same question keeps the same id, so answers can be compared
          over time.
        </p>
        {past.data && past.data.length ? (
          <ul className="divide-y rounded-lg border bg-card">
            {past.data.map((q) => (
              <li key={q.prompt_id}>
                <label className="flex cursor-pointer items-start gap-3 px-4 py-2.5 text-sm hover:bg-muted/50">
                  <Checkbox
                    className="mt-0.5"
                    checked={again.includes(q.prompt_id)}
                    onCheckedChange={(v) =>
                      setAgain(v ? [...again, q.prompt_id] : again.filter((x) => x !== q.prompt_id))
                    }
                  />
                  <span className="min-w-0 flex-1">{q.text}</span>
                  <span className="num shrink-0 text-xs text-muted-foreground">
                    {q.n_runs} run{q.n_runs === 1 ? "" : "s"} · {when(q.last_asked)}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        ) : (
          <Empty title="No questions of your own yet" />
        )}
      </div>
    </div>
  );
}

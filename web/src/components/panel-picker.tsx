"use client";

import { Check, Minus, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { JobBar } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useJob } from "@/hooks/use-api";
import { api, type DiscoveryPlan, type Panel, type Status } from "@/lib/api";
import { humanise, providerLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

type Tri = boolean | "mixed";

/** Tick box with a partly-ticked state, for "select the whole category". */
function TriCheck({ state, onChange, label }: { state: Tri; onChange: () => void; label: string }) {
  const on = state !== false;
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={state === "mixed" ? "mixed" : state}
      aria-label={label}
      onClick={onChange}
      className={cn(
        "grid size-4 shrink-0 place-items-center rounded-[4px] border transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        on ? "border-primary bg-primary text-primary-foreground" : "border-input bg-background",
      )}
    >
      {state === true && <Check className="size-3" strokeWidth={3} />}
      {state === "mixed" && <Minus className="size-3" strokeWidth={3} />}
    </button>
  );
}

const REPEAT_OPTIONS = [1, 2, 3, 5];

export function PanelPicker({
  panels,
  status,
  onFinished,
}: {
  panels: Panel[];
  status: Status;
  onFinished: () => void;
}) {
  const [version, setVersion] = useState(panels[0]?.version ?? "v0");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [enginePick, setEngines] = useState<string[] | null>(null);
  const [repeats, setRepeats] = useState(1);
  const [plan, setPlan] = useState<DiscoveryPlan | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const run = useJob(() => onFinished());

  const panel = panels.find((p) => p.version === version);
  const prompts = useMemo(() => panel?.prompts ?? [], [panel]);
  const engines = enginePick ?? status.providers.filter((p) => p.has_key).map((p) => p.name);

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const m = new Map<string, typeof prompts>();
    for (const p of prompts) {
      if (q && !p.text.toLowerCase().includes(q) && !p.category.includes(q)) continue;
      m.set(p.category, [...(m.get(p.category) ?? []), p]);
    }
    return [...m.entries()];
  }, [prompts, query]);

  const toggle = (ids: string[], on: boolean) =>
    setSelected((s) => {
      const next = new Set(s);
      ids.forEach((id) => (on ? next.add(id) : next.delete(id)));
      return next;
    });

  const ids = useMemo(
    () => prompts.filter((p) => selected.has(p.prompt_id)).map((p) => p.prompt_id),
    [prompts, selected],
  );
  const body = useMemo(
    () => ({ panel_version: version, providers: engines, prompt_ids: ids, repeats }),
    [version, engines, ids, repeats],
  );
  const ready = ids.length > 0 && engines.length > 0;

  useEffect(() => {
    if (!ready) return;
    const t = setTimeout(() => {
      api
        .post<DiscoveryPlan>("/discovery/plan", body)
        .then((p) => {
          setPlan(p);
          setPlanError(null);
        })
        .catch((e: Error) => setPlanError(e.message));
    }, 250);
    return () => clearTimeout(t);
  }, [body, ready]);

  const shownPlan = ready ? plan : null;
  const visibleIds = groups.flatMap(([, ps]) => ps.map((p) => p.prompt_id));
  const allVisibleOn = visibleIds.length > 0 && visibleIds.every((id) => selected.has(id));

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`Search ${prompts.length} questions`}
              className="pl-8"
              aria-label="Search questions"
            />
          </div>
          <Button hint="Tick or untick every question shown in the list." variant="outline" size="sm" onClick={() => toggle(visibleIds, !allVisibleOn)}>
            {allVisibleOn ? "Clear" : "Select"} {query ? "matches" : "all"}
          </Button>
          {selected.size > 0 && (
            <Button hint="Untick every question." variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
              <X /> Clear selection
            </Button>
          )}
          {panels.length > 1 && (
            <select
              className="h-8 rounded-md border bg-background px-2 text-sm"
              value={version}
              onChange={(e) => {
                setVersion(e.target.value);
                setSelected(new Set());
              }}
              aria-label="Panel version"
            >
              {panels.map((p) => (
                <option key={p.version} value={p.version}>
                  Panel {p.version}
                </option>
              ))}
            </select>
          )}
        </div>

        {!groups.length && (
          <p className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
            No question matches “{query}”.
          </p>
        )}

        <div className="columns-1 gap-4 xl:columns-2">
          {groups.map(([cat, ps]) => {
            const n = ps.filter((p) => selected.has(p.prompt_id)).length;
            const state: Tri = n === 0 ? false : n === ps.length ? true : "mixed";
            return (
              <section
                key={cat}
                className={cn(
                  "mb-4 break-inside-avoid overflow-hidden rounded-lg border bg-card transition-colors",
                  n > 0 && "border-primary/40",
                )}
              >
                <header className="flex items-center gap-3 border-b bg-muted/40 px-4 py-2.5">
                  <TriCheck
                    state={state}
                    label={`Select all ${humanise(cat)} questions`}
                    onChange={() =>
                      toggle(
                        ps.map((p) => p.prompt_id),
                        state !== true,
                      )
                    }
                  />
                  <h3 className="flex-1 font-[family-name:var(--font-bricolage)] text-[0.95rem] font-semibold capitalize">
                    {cat.replaceAll("_", " ")}
                  </h3>
                  <span
                    className={cn("num text-xs", n ? "font-medium text-primary" : "text-muted-foreground")}
                  >
                    {n}/{ps.length}
                  </span>
                </header>
                <ul>
                  {ps.map((p) => {
                    const on = selected.has(p.prompt_id);
                    return (
                      <li key={p.prompt_id} className="border-b last:border-0">
                        <label
                          className={cn(
                            "flex cursor-pointer items-start gap-3 px-4 py-3 transition-colors",
                            on ? "bg-accent/60" : "hover:bg-muted/50",
                          )}
                        >
                          <Checkbox
                            className="mt-0.5"
                            checked={on}
                            onCheckedChange={(v) => toggle([p.prompt_id], Boolean(v))}
                          />
                          <span className="min-w-0 flex-1">
                            <span className={cn("block text-sm leading-snug", on && "font-medium")}>
                              {p.text}
                            </span>
                            <span className="mt-1 inline-block text-xs text-muted-foreground">
                              {humanise(p.intent)} · {p.prompt_id}
                            </span>
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}
        </div>
      </div>

      <aside className="h-fit space-y-5 rounded-lg border bg-card p-5 lg:sticky lg:top-6">
        <div>
          <p className="text-sm text-muted-foreground">Selected</p>
          <p className="num mt-1 font-[family-name:var(--font-bricolage)] text-5xl font-semibold leading-none">
            {ids.length}
            <span className="text-2xl text-muted-foreground"> / {prompts.length}</span>
          </p>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-300"
              style={{ width: `${prompts.length ? (ids.length / prompts.length) * 100 : 0}%` }}
            />
          </div>
        </div>

        <fieldset className="space-y-2.5">
          <legend className="mb-2 text-sm font-medium">Engines</legend>
          {status.providers.map((p) => (
            <label
              key={p.name}
              className={cn("flex items-center gap-3 text-sm", !p.has_key && "text-muted-foreground")}
            >
              <Checkbox
                checked={engines.includes(p.name)}
                disabled={!p.has_key}
                onCheckedChange={(v) =>
                  setEngines(v ? [...engines, p.name] : engines.filter((x) => x !== p.name))
                }
              />
              <span className="flex-1">{providerLabel(p.name)}</span>
              <span className="text-xs text-muted-foreground">{p.has_key ? p.model : "add key in .env"}</span>
            </label>
          ))}
        </fieldset>

        <div>
          <p className="mb-2 text-sm font-medium">Ask each question</p>
          <div role="radiogroup" aria-label="Repeats" className="grid grid-cols-4 rounded-md border p-0.5">
            {REPEAT_OPTIONS.map((r) => (
              <button
                key={r}
                role="radio"
                aria-checked={repeats === r}
                onClick={() => setRepeats(r)}
                className={cn(
                  "num rounded-[5px] py-1.5 text-sm transition-colors",
                  repeats === r
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {r}×
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Asking more than once shows how stable the answers are.
          </p>
        </div>

        <div className="rounded-md bg-muted px-3 py-2.5 text-sm">
          {!ids.length ? (
            "Tick the questions you want to ask."
          ) : !engines.length ? (
            "Choose at least one engine."
          ) : planError ? (
            <span className="text-loss">{planError}</span>
          ) : shownPlan ? (
            <>
              <span className="num font-semibold">{shownPlan.n_calls}</span> billed call
              {shownPlan.n_calls === 1 ? "" : "s"}: {shownPlan.n_prompts} × {shownPlan.providers.length}{" "}
              engine
              {shownPlan.providers.length === 1 ? "" : "s"} × {shownPlan.repeats}
            </>
          ) : (
            "Counting calls…"
          )}
        </div>

        <Button hint="Sends the ticked questions to each chosen engine. Results appear in step 2, See results."
          size="lg"
          className="w-full"
          disabled={!shownPlan || shownPlan.missing_keys.length > 0 || run.busy}
          onClick={() => run.start("/jobs/discovery", body, "Panel run")}
        >
          {run.busy
            ? "Asking…"
            : `Ask ${ids.length || ""} question${ids.length === 1 ? "" : "s"}`.replace("  ", " ")}
        </Button>
        {engines.includes("gemini") && ids.length > 10 && (
          <p className="text-xs text-muted-foreground">
            Gemini&apos;s free tier allows about 10 requests a minute; larger runs may see some failed calls.
          </p>
        )}
        <JobBar job={run.job} />
      </aside>
    </div>
  );
}

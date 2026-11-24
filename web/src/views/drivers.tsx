"use client";

import { CheckCircle2, CircleAlert, CircleHelp } from "lucide-react";

import { Empty, ErrorNote, Loading, PageHeader, Panel } from "@/components/bits";
import { useApi } from "@/hooks/use-api";
import type { CellRate, FactorRate, ModelInsights, ModelRun, ModelSummary, OddsRatio } from "@/lib/api";
import { brandColor } from "@/lib/brands";
import { num, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

// ---------- labels ----------

const LEVEL: Record<string, string> = {
  chatgpt: "ChatGPT",
  claude: "Claude",
  gemini: "Gemini",
  google_ai_mode: "Google AI Mode",
  perplexity: "Perplexity",
  where_to_buy: "Where to buy",
  en: "English",
  hinglish: "Hinglish",
  batched_chat: "Batched chat",
  single_chat: "Fresh chat",
  api: "API",
  acne_skincare: "Acne skincare",
};
const FACTOR: Record<string, string> = {
  engine: "Engine",
  question_type: "Question type",
  category: "Category",
  language: "Language",
  collection_method: "How it was collected",
};

const levelLabel = (v: string) => LEVEL[v] ?? v.charAt(0).toUpperCase() + v.slice(1).replaceAll("_", " ");
const factorLabel = (f: string) => FACTOR[f] ?? f.replaceAll("_", " ");
const modelLabel = (m: string) => m.replace(/\s*\(.*\)\s*$/, "");

function termLabel(term: string, refs: Record<string, string>) {
  const [factor, level] = term.split("=");
  const ref = refs[factor];
  return { name: levelLabel(level), vs: ref ? `vs ${levelLabel(ref)}` : "", factor: factorLabel(factor) };
}

const times = (v: number) => (v >= 10 ? `${Math.round(v)}×` : `${v.toFixed(v < 1 ? 2 : 1)}×`);

// ---------- headline ----------

function Tile({ label, value, hint }: { label: string; value: React.ReactNode; hint: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="num mt-1 font-[family-name:var(--font-bricolage)] text-2xl font-semibold sm:text-3xl">
        {value}
      </p>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{hint}</p>
    </div>
  );
}

function Headline({ run, robust }: { run: ModelRun; robust: ModelInsights["robustness"] }) {
  const ors = run.odds_ratios;
  const up = [...ors].filter((o) => o.ci_low > 1).sort((a, b) => b.odds_ratio - a.odds_ratio)[0];
  const down = [...ors].filter((o) => o.ci_high < 1).sort((a, b) => a.odds_ratio - b.odds_ratio)[0];
  const d = run.dataset;
  return (
    <div className="grid grid-cols-2 gap-x-6 gap-y-6 lg:grid-cols-4">
      <Tile
        label={`${d.target} named`}
        value={pct(run.prevalence, 1)}
        hint={`${d.n_positive} of ${d.n_used} answers, ${d.n_groups} questions`}
      />
      {up ? (
        <Tile
          label="Biggest lift"
          value={times(up.odds_ratio)}
          hint={`${termLabel(up.term, run.reference_levels).name} ${termLabel(up.term, run.reference_levels).vs}`}
        />
      ) : (
        <Tile label="Biggest lift" value="–" hint="No factor clearly raises the odds" />
      )}
      {down ? (
        <Tile
          label="Biggest drag"
          value={times(down.odds_ratio)}
          hint={`${termLabel(down.term, run.reference_levels).name} ${termLabel(down.term, run.reference_levels).vs}`}
        />
      ) : (
        <Tile label="Biggest drag" value="–" hint="No factor clearly lowers the odds" />
      )}
      <Tile
        label="Best model"
        value={<span className="text-xl sm:text-2xl">{modelLabel(run.chosen)}</span>}
        hint={
          robust.status === "agrees"
            ? "Confirmed on the strict set"
            : robust.status === "disagrees"
              ? "Not confirmed on the strict set"
              : "Strict set not checked yet"
        }
      />
    </div>
  );
}

// ---------- where the brand is named: interval bars per factor ----------

function RateBars({ rows, overall, color }: { rows: FactorRate[]; overall: number; color: string }) {
  const max = Math.min(1, Math.max(0.3, ...rows.map((r) => r.ci_high ?? r.rate)));
  const x = (v: number) => `${(v / max) * 100}%`;
  const sorted = [...rows].sort((a, b) => b.rate - a.rate);
  return (
    <ul className="space-y-2.5">
      {sorted.map((r) => (
        <li
          key={r.level}
          className="grid grid-cols-[7.5rem_1fr_4.5rem] items-center gap-3 text-sm"
          title={`${levelLabel(r.level)}: ${pct(r.rate, 1)} of ${r.n} answers (95% interval ${pct(r.ci_low)}–${pct(r.ci_high)})`}
        >
          <span className="truncate text-muted-foreground">{levelLabel(r.level)}</span>
          <div className="relative h-5 rounded-[4px] bg-muted">
            <div
              className="absolute inset-y-0 left-0 rounded-[4px]"
              style={{ width: x(r.rate), background: color, opacity: 0.85 }}
            />
            {r.ci_low != null && r.ci_high != null && (
              <div
                className="absolute top-1/2 h-px -translate-y-1/2 bg-foreground/70"
                style={{ left: x(r.ci_low), width: `calc(${x(r.ci_high)} - ${x(r.ci_low)})` }}
              />
            )}
            <div
              className="absolute inset-y-[-3px] w-px border-l border-dashed border-foreground/40"
              style={{ left: x(overall) }}
            />
          </div>
          <span className="num text-right">
            {pct(r.rate)} <span className="text-xs text-muted-foreground">n={r.n}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

// ---------- odds ratios: forest plot on a log scale ----------

const LOG_MIN = Math.log10(0.01);
const LOG_MAX = Math.log10(1000);
const lx = (v: number) => {
  const c = Math.min(Math.max(Math.log10(Math.max(v, 1e-6)), LOG_MIN), LOG_MAX);
  return ((c - LOG_MIN) / (LOG_MAX - LOG_MIN)) * 100;
};

function Forest({ ors, refs }: { ors: OddsRatio[]; refs: Record<string, string> }) {
  const sorted = [...ors].sort((a, b) => b.odds_ratio - a.odds_ratio);
  const ticks = [0.01, 0.1, 1, 10, 100, 1000];
  return (
    <div>
      <div className="grid grid-cols-[minmax(0,11rem)_1fr_4.5rem] gap-3 pb-1 text-xs text-muted-foreground">
        <span />
        <div className="relative h-4">
          {ticks.map((t) => (
            <span
              key={t}
              className={cn("absolute -translate-x-1/2", [0.1, 10, 1000].includes(t) && "hidden sm:inline")}
              style={{ left: `${lx(t)}%` }}
            >
              {t}×
            </span>
          ))}
        </div>
        <span className="text-right">odds</span>
      </div>
      <ul className="space-y-1.5">
        {sorted.map((o) => {
          const sig = o.ci_low > 1 ? "up" : o.ci_high < 1 ? "down" : "none";
          const color = sig === "up" ? "var(--gain)" : sig === "down" ? "var(--loss)" : "var(--muted-foreground)";
          const lab = termLabel(o.term, refs);
          return (
            <li
              key={o.term}
              className="grid grid-cols-[minmax(0,11rem)_1fr_4.5rem] items-center gap-3 text-sm"
              title={`${lab.factor}: ${lab.name} ${lab.vs} — odds ×${num(o.odds_ratio, 2)} (95% ${num(o.ci_low, 2)}–${num(o.ci_high, 2)}), p=${num(o.p_value, 3)}`}
            >
              <span className="min-w-0 truncate">
                {lab.name} <span className="text-xs text-muted-foreground">{lab.vs}</span>
              </span>
              <div className="relative h-6">
                <div className="absolute inset-y-0 w-px bg-border" style={{ left: `${lx(1)}%` }} />
                <div
                  className="absolute top-1/2 h-[2px] -translate-y-1/2 rounded"
                  style={{ left: `${lx(o.ci_low)}%`, width: `${lx(o.ci_high) - lx(o.ci_low)}%`, background: color, opacity: 0.55 }}
                />
                <div
                  className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-card"
                  style={{ left: `${lx(o.odds_ratio)}%`, background: color }}
                />
              </div>
              <span className={cn("num text-right", sig === "none" && "text-muted-foreground")}>
                {times(o.odds_ratio)}
              </span>
            </li>
          );
        })}
      </ul>
      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-full" style={{ background: "var(--gain)" }} /> Raises the odds (interval above 1)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-full" style={{ background: "var(--loss)" }} /> Lowers the odds (interval below 1)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-full bg-muted-foreground" /> No clear effect
        </span>
      </div>
    </div>
  );
}

// ---------- engine × question type ----------

function CellGrid({ cells, color }: { cells: CellRate[]; color: string }) {
  const engines = [...new Set(cells.map((c) => c.engine))].sort();
  const types = [...new Set(cells.map((c) => c.question_type))].sort();
  const get = (e: string, q: string) => cells.find((c) => c.engine === e && c.question_type === q);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px] table-fixed border-separate border-spacing-1 text-sm">
        <thead>
          <tr>
            <th className="w-32 text-left text-xs font-normal text-muted-foreground">Engine</th>
            {types.map((q) => (
              <th key={q} className="text-left text-xs font-medium">
                {levelLabel(q)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {engines.map((e) => (
            <tr key={e}>
              <td className="pr-2 text-muted-foreground">{levelLabel(e)}</td>
              {types.map((q) => {
                const c = get(e, q);
                return (
                  <td key={q} className="p-0">
                    <div
                      className="relative h-10 overflow-hidden rounded-[4px] bg-muted"
                      title={c ? `${levelLabel(e)} · ${levelLabel(q)}: ${c.positives} of ${c.n} (95% ${pct(c.ci_low)}–${pct(c.ci_high)})` : "no answers"}
                    >
                      {c && (
                        <div className="absolute inset-0" style={{ background: color, opacity: 0.08 + c.rate * 0.82 }} />
                      )}
                      <span
                        className={cn(
                          "num relative flex h-full items-center px-2",
                          c && c.rate > 0.55 && "text-white",
                        )}
                      >
                        {c ? pct(c.rate) : "–"}
                        {c && <span className="ml-1 text-[0.7rem] opacity-70">/{c.n}</span>}
                      </span>
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------- model comparison ----------

function ModelBars({ main, strict, prevalence }: { main: ModelRun; strict: ModelRun | null; prevalence: number }) {
  const strictBy = Object.fromEntries((strict?.summary ?? []).map((s) => [s.model, s]));
  const max = Math.max(0.4, ...main.summary.map((s) => (s.pr_auc_mean ?? 0) + (s.pr_auc_sd ?? 0)));
  const x = (v: number) => `${(v / max) * 100}%`;
  const row = (s: ModelSummary, isChosen: boolean) => (
    <li key={s.model} className="grid grid-cols-[minmax(0,10rem)_1fr_5.5rem] items-center gap-3 text-sm">
      <span className={cn("min-w-0 truncate", isChosen && "font-semibold")}>{modelLabel(s.model)}</span>
      <div className="relative h-5 rounded-[4px] bg-muted">
        <div
          className="absolute inset-y-0 left-0 rounded-[4px]"
          style={{ width: x(s.pr_auc_mean ?? 0), background: isChosen ? "var(--primary)" : "var(--chart-5)", opacity: isChosen ? 0.9 : 0.55 }}
        />
        {s.pr_auc_sd != null && (
          <div
            className="absolute top-1/2 h-px -translate-y-1/2 bg-foreground/70"
            style={{
              left: x(Math.max(0, (s.pr_auc_mean ?? 0) - s.pr_auc_sd)),
              width: `calc(${x((s.pr_auc_mean ?? 0) + s.pr_auc_sd)} - ${x(Math.max(0, (s.pr_auc_mean ?? 0) - s.pr_auc_sd))})`,
            }}
          />
        )}
        <div
          className="absolute inset-y-[-3px] w-px border-l border-dashed border-foreground/50"
          style={{ left: x(prevalence) }}
          title={`Random ranking scores about ${num(prevalence, 2)}`}
        />
      </div>
      <span className="num text-right">{num(s.pr_auc_mean, 3)}</span>
    </li>
  );
  return (
    <div className="space-y-5">
      <ul className="space-y-2.5">{main.summary.map((s) => row(s, s.model === main.chosen))}</ul>
      <p className="text-xs text-muted-foreground">
        Bar: PR-AUC on questions the model never saw, averaged over {main.summary[0]?.n_runs || 1} reshuffled
        runs; line: ±1 sd; dashed: random ranking ({num(prevalence, 2)}).
      </p>
      <div className="overflow-x-auto">
        <table className="num w-full min-w-[520px] text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr className="border-b">
              <th className="py-2 font-normal">Model</th>
              <th className="text-right font-normal">Beats baseline</th>
              <th className="text-right font-normal">Brier</th>
              <th className="text-right font-normal">F1</th>
              <th className="text-right font-normal">Strict set PR-AUC</th>
            </tr>
          </thead>
          <tbody>
            {main.summary.map((s) => (
              <tr key={s.model} className="border-b last:border-0">
                <td className="py-2">{modelLabel(s.model)}</td>
                <td className="text-right">
                  {s.wins_vs_baseline == null ? "–" : `${s.wins_vs_baseline} of ${s.n_runs} runs`}
                </td>
                <td className="text-right">{num(s.brier_mean, 3)}</td>
                <td className="text-right">{num(s.f1_mean, 2)}</td>
                <td className="text-right">{num(strictBy[s.model]?.pr_auc_mean, 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Verdict({ main, robust }: { main: ModelRun; robust: ModelInsights["robustness"] }) {
  const Icon = robust.status === "agrees" ? CheckCircle2 : robust.status === "disagrees" ? CircleAlert : CircleHelp;
  const tone = robust.status === "agrees" ? "text-gain" : robust.status === "disagrees" ? "text-loss" : "text-muted-foreground";
  return (
    <div className="space-y-3 text-sm leading-relaxed">
      <p>
        <span className="font-semibold">{modelLabel(main.chosen)}</span> is selected. {main.choice_reason}
      </p>
      <p className={cn("flex items-start gap-2", tone)}>
        <Icon className="mt-0.5 size-4 shrink-0" />
        <span>{robust.note}</span>
      </p>
      {main.m1_c != null && (
        <p className="text-xs text-muted-foreground">
          M1 regularisation strength C = {main.m1_c}, chosen by grouped cross-validation.
        </p>
      )}
    </div>
  );
}

// ---------- page ----------

export default function ModelsPage() {
  const { data, error, loading } = useApi<ModelInsights>("/models");
  const main = data?.main ?? null;
  const target = main?.dataset.target ?? "the target brand";
  const color = brandColor(target);
  const factorOrder = ["question_type", "engine", "category", "language", "collection_method"];

  return (
    <div className="space-y-8">
      <PageHeader
        title="What drives visibility"
        lede={
          main
            ? `Which questions and engines make AI answers name ${target}? Learned from ${main.dataset.n_used} real answers to ${main.dataset.n_groups} questions, in English and Hinglish.`
            : "Which questions and engines make AI answers name the brand, learned from real answers."
        }
      />

      {error && <ErrorNote message={error} />}
      {loading && <Loading rows={4} />}
      {data && !main && (
        <Empty title="No model trained yet">
          Run <code className="rounded bg-muted px-1.5 py-0.5 text-xs">python -m src.modelling.train --data responses_clean_v1.0.csv</code>{" "}
          and refresh.
        </Empty>
      )}

      {main && (
        <>
          <Headline run={main} robust={data!.robustness} />

          <Panel
            title={`Where ${target} gets named`}
            note="Share of answers naming the brand, with 95% intervals. Dashed line: the overall rate."
          >
            <div className="grid gap-x-10 gap-y-8 lg:grid-cols-2">
              {factorOrder
                .filter((f) => main.factor_rates.some((r) => r.factor === f))
                .map((f) => (
                  <div key={f}>
                    <h3 className="mb-3 text-sm font-medium">{factorLabel(f)}</h3>
                    <RateBars
                      rows={main.factor_rates.filter((r) => r.factor === f)}
                      overall={main.prevalence}
                      color={color}
                    />
                  </div>
                ))}
            </div>
          </Panel>

          <div className="grid gap-6 xl:grid-cols-[1.15fr_1fr]">
            <Panel
              title="What raises or lowers the odds"
              note="Each factor holding the others fixed, compared with its most common level. Association in this sample, not cause; intervals account for repeated answers to one question."
            >
              <Forest ors={main.odds_ratios} refs={main.reference_levels} />
            </Panel>
            <Panel
              title="Engine × question type"
              note="The baseline model: share of answers naming the brand in each cell (answers per cell after the slash)."
            >
              <CellGrid cells={main.baseline_cells} color={color} />
            </Panel>
          </div>

          <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
            <Panel
              title="Which model to trust"
              note="Scored on questions held out from training, grouped so English and Hinglish versions stay together."
            >
              <ModelBars main={main} strict={data!.strict} prevalence={main.prevalence} />
            </Panel>
            <Panel title="Verdict">
              <Verdict main={main} robust={data!.robustness} />
            </Panel>
          </div>

          <Panel title="Read with care" quiet>
            <ul className="max-w-[80ch] list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-muted-foreground">
              {main.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
              <li>Observational answers: effects describe this sample, not what would change if Sephora acted.</li>
              <li>
                Brand mentions are found by fixed rules; they agree with the team&apos;s word search on{" "}
                {pct(main.dataset.reader_vs_sheet_agreement, 1)} of answers and are not yet checked by hand.
              </li>
            </ul>
            <p className="mt-4 break-all text-xs text-muted-foreground">
              Run {main.run} · data {main.dataset.sha256.slice(0, 12)} · {main.dataset.analysis_set} ·{" "}
              {main.dataset.n_rows} rows in file, {main.dataset.n_used} used
              {main.mlflow_run_id ? ` · MLflow ${main.mlflow_run_id.slice(0, 8)}` : ""}
            </p>
          </Panel>
        </>
      )}
    </div>
  );
}

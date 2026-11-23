"use client";

import { useState } from "react";

import { Empty, ErrorNote, Loading, PageHeader, Panel } from "@/components/bits";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi } from "@/hooks/use-api";
import type { PRF, ValidationReport, ValidationSample } from "@/lib/api";
import { num, pct } from "@/lib/format";

function Score({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="num mt-1 font-[family-name:var(--font-bricolage)] text-3xl font-semibold">{value}</p>
      <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}

function PrfRow({ name, prf }: { name: string; prf: PRF | null }) {
  return (
    <tr className="border-b last:border-0">
      <td className="py-2.5">{name}</td>
      <td className="text-right">{pct(prf?.precision, 1)}</td>
      <td className="text-right">{pct(prf?.recall, 1)}</td>
      <td className="text-right">{pct(prf?.f1, 1)}</td>
      <td className="text-right text-muted-foreground">{prf?.n ?? "–"}</td>
    </tr>
  );
}

export default function ValidationPage() {
  const samples = useApi<ValidationSample[]>("/validation");
  const [versionPick, setVersion] = useState<string>();
  const version = versionPick ?? samples.data?.[0]?.sample_version;
  const report = useApi<ValidationReport | null>(version ? `/validation/${version}` : null);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Check accuracy"
        lede="Two people label a sample of answers by hand. Comparing their labels with the system's shows how far the measurements can be trusted."
      />

      {samples.error && <ErrorNote message={samples.error} />}
      {samples.loading && <Loading />}

      {samples.data && !samples.data.length && (
        <Panel title="How to set up a check">
          <ol className="max-w-[70ch] list-decimal space-y-2 pl-5 text-sm leading-relaxed text-muted-foreground">
            <li>
              Draw a sample from the latest run:{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 text-xs text-foreground">
                python scripts/validation.py sample --latest --n 100 --version s1 --labellers TS AB
              </code>
            </li>
            <li>Each person fills in their own sheet in data/processed/validation/, without seeing the other&apos;s.</li>
            <li>
              Import both sheets:{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 text-xs text-foreground">
                python scripts/validation.py import --version s1 --labeller TS --file …
              </code>
            </li>
            <li>The scores appear here.</li>
          </ol>
        </Panel>
      )}

      {samples.data && samples.data.length > 0 && (
        <Tabs value={version} onValueChange={setVersion}>
          <TabsList>
            {samples.data.map((s) => (
              <TabsTrigger key={s.sample_version} value={s.sample_version}>
                Sample {s.sample_version} · {s.n_responses} answers
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      )}

      {report.loading && version && <Loading />}
      {version && report.data === null && (
        <Empty title={`No labels imported for sample ${version}`}>Import the labelled sheets to see the scores.</Empty>
      )}

      {report.data && (
        <>
          <div className="grid grid-cols-2 gap-6 lg:grid-cols-4">
            <Score label="Mention precision" value={pct(report.data.mentioned.precision, 1)} hint="Named by the system and truly there" />
            <Score label="Mention recall" value={pct(report.data.mentioned.recall, 1)} hint="Truly there and found by the system" />
            <Score label="Mention F1" value={pct(report.data.mentioned.f1, 1)} hint={`${report.data.mentioned.n} labelled items`} />
            <Score
              label="Labeller agreement"
              value={num(report.data.kappa_mentioned, 2)}
              hint="Cohen's κ between the two people; above 0.8 is strong"
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Panel title="Scores by measurement">
              <table className="num w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr className="border-b">
                    <th className="py-2 font-normal">Measure</th>
                    <th className="text-right font-normal">Precision</th>
                    <th className="text-right font-normal">Recall</th>
                    <th className="text-right font-normal">F1</th>
                    <th className="text-right font-normal">n</th>
                  </tr>
                </thead>
                <tbody>
                  <PrfRow name="Brand mentioned" prf={report.data.mentioned} />
                  <PrfRow name="Recommended" prf={report.data.is_recommended} />
                </tbody>
              </table>
              <dl className="num mt-5 grid grid-cols-2 gap-4 text-sm">
                <div>
                  <dt className="text-xs text-muted-foreground">List rank exact</dt>
                  <dd>
                    {pct(report.data.rank_accuracy, 1)} <span className="text-muted-foreground">of {report.data.rank_n}</span>
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Sentiment accuracy</dt>
                  <dd>
                    {pct(report.data.sentiment_accuracy, 1)}{" "}
                    <span className="text-muted-foreground">of {report.data.sentiment_n}</span>
                  </dd>
                </div>
              </dl>
            </Panel>
            <Panel title="Where the system disagreed" note="First mismatches with the human consensus, for error analysis.">
              {report.data.errors.length ? (
                <ul className="divide-y text-sm">
                  {report.data.errors.map((e, i) => (
                    <li key={i} className="py-2">
                      <p>
                        {e.brand}: people said <b>{e.human === "True" ? "mentioned" : "not mentioned"}</b>, system said{" "}
                        <b>{e.system === "True" ? "mentioned" : "not mentioned"}</b>
                      </p>
                      {e.notes && <p className="text-xs text-muted-foreground">{e.notes}</p>}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">No disagreements.</p>
              )}
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}

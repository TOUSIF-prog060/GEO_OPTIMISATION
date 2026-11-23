"use client";

import { AlertTriangle, Loader2 } from "lucide-react";

import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import type { Job, Run } from "@/lib/api";
import { brandColor } from "@/lib/brands";
import { providerLabel, when } from "@/lib/format";
import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  lede,
  actions,
}: {
  title: string;
  lede?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-2xl">
        <h1 className="text-3xl font-semibold sm:text-[2.4rem] sm:leading-[1.05]">{title}</h1>
        {lede && <p className="mt-3 text-[0.95rem] leading-relaxed text-muted-foreground">{lede}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** A titled region. `quiet` drops the surface so not every block reads as a card. */
export function Panel({
  title,
  note,
  action,
  children,
  className,
  quiet,
}: {
  title?: string;
  note?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  quiet?: boolean;
}) {
  return (
    <section
      className={cn(
        "min-w-0",
        !quiet && "rounded-lg border bg-card p-5 shadow-[0_1px_0_rgba(22,24,29,0.03)]",
        className,
      )}
    >
      {(title || action) && (
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && <h2 className="text-lg font-semibold">{title}</h2>}
            {note && <p className="mt-1 text-sm text-muted-foreground">{note}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed px-6 py-10 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-lg border border-loss/30 bg-loss/5 px-4 py-3 text-sm"
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-loss" />
      <p>{message}</p>
    </div>
  );
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-busy>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-16 w-full" />
      ))}
    </div>
  );
}

export function BrandChip({ brand, muted }: { brand: string; muted?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm", muted && "text-muted-foreground")}>
      <span aria-hidden className="size-2.5 rounded-[3px]" style={{ background: brandColor(brand) }} />
      {brand}
    </span>
  );
}

export function StatusPill({ status }: { status: string }) {
  const tone: Record<string, string> = {
    completed: "bg-gain/10 text-gain",
    done: "bg-gain/10 text-gain",
    approved: "bg-gain/10 text-gain",
    running: "bg-primary/10 text-primary",
    in_progress: "bg-primary/10 text-primary",
    awaiting_review: "bg-chart-4/15 text-[color:var(--chart-4)]",
    partial: "bg-chart-4/15 text-[color:var(--chart-4)]",
    planned: "bg-muted text-muted-foreground",
    failed: "bg-loss/10 text-loss",
    rejected: "bg-loss/10 text-loss",
  };
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
        tone[status] ?? "bg-muted text-muted-foreground",
      )}
    >
      {status.replaceAll("_", " ")}
    </span>
  );
}

export function JobBar({ job }: { job: Job | null }) {
  if (!job) return null;
  const { done, total, provider, stage } = job.progress ?? {};
  const value = total ? Math.round(((done ?? 0) / total) * 100) : undefined;
  return (
    <div
      aria-live="polite"
      className={cn(
        "rounded-lg border px-4 py-3 text-sm",
        job.status === "failed" && "border-loss/30 bg-loss/5",
        job.status === "done" && "border-gain/30 bg-gain/5",
      )}
    >
      <div className="flex items-center gap-2">
        {(job.status === "running" || job.status === "queued") && (
          <Loader2 className="size-4 animate-spin text-primary" />
        )}
        <span className="font-medium capitalize">{job.kind.replaceAll("_", " ")}</span>
        <StatusPill status={job.status} />
        {total ? (
          <span className="num ml-auto text-muted-foreground">
            {stage === "measuring" ? "Measuring" : provider ? providerLabel(provider) : ""} {done}/{total}
          </span>
        ) : null}
      </div>
      {value != null && job.status === "running" && <Progress value={value} className="mt-3 h-1.5" />}
      {job.error && <p className="mt-2 text-loss">{job.error}</p>}
    </div>
  );
}

export function RunSelect({
  runs,
  value,
  onChange,
  onlyDiagnosed,
}: {
  runs: Run[];
  value: string | undefined;
  onChange: (id: string) => void;
  onlyDiagnosed?: boolean;
}) {
  const list = onlyDiagnosed ? runs.filter((r) => r.diagnosed) : runs;
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-[300px] max-w-full" aria-label="Run">
        <SelectValue placeholder="Choose a run" />
      </SelectTrigger>
      <SelectContent>
        {list.map((r) => (
          <SelectItem key={r.run_id} value={r.run_id}>
            {providerLabel(r.provider)} · {when(r.started_at)} · {r.n_responses - r.n_errors} answers
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function Delta({ value, suffix = " pts" }: { value: number | null | undefined; suffix?: string }) {
  if (value == null) return <span className="text-xs text-muted-foreground">first run</span>;
  const up = value > 0;
  return (
    <span className={cn("num text-xs font-medium", up ? "text-gain" : value < 0 ? "text-loss" : "text-muted-foreground")}>
      {up ? "▲" : value < 0 ? "▼" : "•"} {Math.abs(value * 100).toFixed(1)}
      {suffix}
    </span>
  );
}

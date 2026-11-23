"use client";

import { Download, FileText, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useApi, useJob } from "@/hooks/use-api";
import type { Job } from "@/lib/api";

type Props = {
  kind: "run" | "evaluation";
  runId?: string;
  label?: string;
  disabled?: boolean;
  disabledReason?: string;
  variant?: "default" | "outline";
};

/** Builds a PDF report on the server, then downloads it. */
export function ReportButton({ kind, runId, label, disabled, disabledReason, variant = "outline" }: Props) {
  const [last, setLast] = useState<string | null>(null);
  const job = useJob((j: Job) => {
    if (j.status !== "done") return;
    const { file, format } = (j.result ?? {}) as { file?: string; format?: string };
    if (!file) return;
    setLast(file);
    // Same-origin file download: a temporary link with the download attribute.
    const link = document.createElement("a");
    link.href = `/api/reports/${encodeURIComponent(file)}`;
    link.download = file;
    document.body.appendChild(link);
    link.click();
    link.remove();
    if (format !== "pdf")
      toast.warning("Saved as a web page", {
        description: "Chrome or Edge was not found on the server, so the report could not be printed to PDF.",
      });
  });

  const text = label ?? (kind === "run" ? "Download PDF report" : "Download evaluation PDF");
  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        variant={variant}
        disabled={disabled || job.busy}
        title={disabled ? disabledReason : undefined}
        onClick={() =>
          job.start(
            "/jobs/report",
            { kind, run_id: runId ?? null },
            kind === "run" ? "Report" : "Evaluation report",
          )
        }
      >
        {job.busy ? <Loader2 className="animate-spin" /> : <Download />}
        {job.busy ? "Preparing PDF…" : text}
      </Button>
      {job.busy && kind === "evaluation" && (
        <span className="text-xs text-muted-foreground">Runs every test first, about 10 seconds.</span>
      )}
      {last && !job.busy && (
        <a
          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
          href={`/api/reports/${encodeURIComponent(last)}`}
        >
          <FileText className="size-3" /> {last}
        </a>
      )}
      {job.job?.status === "failed" && (
        <span className="max-w-xs text-right text-xs text-loss">{job.job.error}</span>
      )}
    </div>
  );
}

type ReportFile = { file: string; kind: string; size_kb: number; created: number };

/** Reports already generated, newest first. */
export function ReportList({ kind }: { kind?: "run" | "evaluation" }) {
  const { data, error } = useApi<ReportFile[]>("/reports");
  if (error) return <p className="text-sm text-loss">{error}</p>;
  const rows = (data ?? []).filter((r) => !kind || r.kind === kind);
  if (!rows.length)
    return (
      <p className="text-sm text-muted-foreground">No reports yet. Use the download button to create one.</p>
    );
  return (
    <ul className="divide-y text-sm">
      {rows.slice(0, 8).map((r) => (
        <li key={r.file} className="flex items-center gap-3 py-2">
          <FileText className="size-4 shrink-0 text-muted-foreground" />
          <a
            className="min-w-0 flex-1 truncate hover:text-primary hover:underline"
            href={`/api/reports/${encodeURIComponent(r.file)}`}
          >
            {r.kind === "run" ? "Visibility report" : "Evaluation report"} ·{" "}
            {new Date(r.created * 1000).toLocaleString("en-IN", {
              day: "numeric",
              month: "short",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </a>
          <span className="num shrink-0 text-xs text-muted-foreground">{r.size_kb} KB</span>
        </li>
      ))}
    </ul>
  );
}

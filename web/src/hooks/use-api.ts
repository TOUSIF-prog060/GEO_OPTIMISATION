"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api, type Job } from "@/lib/api";

type State<T> = { key: string | null; data?: T; error: string | null };

/** GET a path; re-fetch with reload(). Pass null to skip. Keeps showing data while reloading. */
export function useApi<T>(path: string | null) {
  const [tick, setTick] = useState(0);
  const [state, setState] = useState<State<T>>({ key: null, error: null });
  const key = path ? `${path}#${tick}` : null;

  useEffect(() => {
    if (!key || !path) return;
    let alive = true;
    api
      .get<T>(path)
      .then((data) => alive && setState({ key, data, error: null }))
      .catch((e: Error) => alive && setState((s) => ({ key, data: s.data, error: e.message })));
    return () => {
      alive = false;
    };
  }, [key, path]);

  const samePath = path != null && state.key?.startsWith(`${path}#`);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return {
    data: samePath ? state.data : undefined,
    error: samePath ? state.error : null,
    loading: key != null && state.key !== key,
    reload,
  };
}

/** Start a background job and poll it until it finishes. */
export function useJob(onDone?: (job: Job) => void) {
  const [job, setJob] = useState<Job | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const doneRef = useRef(onDone);

  useEffect(() => {
    doneRef.current = onDone;
  });

  const stop = () => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  };

  useEffect(() => stop, []);

  const start = useCallback(async (path: string, body?: unknown, label?: string) => {
    stop();
    const name = label ?? "Job";
    try {
      const j = await api.post<Job>(path, body);
      setJob(j);
      toast.info(`${name} started`);
      timer.current = setInterval(async () => {
        try {
          const next = await api.get<Job>(`/jobs/${j.job_id}`);
          setJob(next);
          if (next.status === "done" || next.status === "failed") {
            stop();
            if (next.status === "done") toast.success(`${name} finished`);
            else toast.error(`${name} failed`, { description: next.error ?? undefined });
            doneRef.current?.(next);
          }
        } catch (e) {
          stop();
          toast.error("Lost track of the job", { description: (e as Error).message });
        }
      }, 1500);
    } catch (e) {
      toast.error(`${name} could not start`, { description: (e as Error).message });
    }
  }, []);

  const busy = job?.status === "queued" || job?.status === "running";
  return { job, start, busy };
}

/** True after hydration; false during server render. */
export function useMounted() {
  const [mounted] = useState(() => typeof window !== "undefined");
  return mounted;
}

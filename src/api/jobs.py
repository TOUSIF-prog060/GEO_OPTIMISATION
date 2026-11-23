"""Background jobs for long, billed or slow work (discovery, diagnostics, agent, re-tests).

The API returns a job id at once; the dashboard polls GET /api/jobs/{id}. Jobs live in memory
only: results themselves are always written to the database by the engines, so a restart loses
the progress view, never data.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "done", "failed"]


class Job(BaseModel):
    job_id: str
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)
    status: JobStatus = "queued"
    progress: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


ProgressFn = Callable[[dict[str, Any]], None]
JobFn = Callable[[ProgressFn], Any]


class JobManager:
    def __init__(self, max_workers: int = 2, keep: int = 100) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._keep = keep

    def submit(self, kind: str, params: dict[str, Any], fn: JobFn) -> Job:
        job = Job(job_id=uuid.uuid4().hex[:12], kind=kind, params=params)
        with self._lock:
            self._jobs[job.job_id] = job
            self._trim()
        self._pool.submit(self._run, job.job_id, fn)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy(deep=True) if job else None

    def list(self) -> list[Job]:
        with self._lock:
            jobs = [j.model_copy(deep=True) for j in self._jobs.values()]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def _update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for k, v in fields.items():
                setattr(job, k, v)

    def _run(self, job_id: str, fn: JobFn) -> None:
        self._update(job_id, status="running")

        def progress(p: dict[str, Any]) -> None:
            self._update(job_id, progress=p)

        try:
            result = fn(progress)
            self._update(job_id, status="done", result=result, finished_at=datetime.now(UTC))
        except Exception as exc:  # report to the UI and log with traceback
            logger.exception("Job %s failed", job_id)
            self._update(job_id, status="failed", error=f"{type(exc).__name__}: {exc}",
                         finished_at=datetime.now(UTC))  # fmt: skip

    def _trim(self) -> None:
        if len(self._jobs) <= self._keep:
            return
        done = sorted((j for j in self._jobs.values() if j.status in {"done", "failed"}),
                      key=lambda j: j.created_at)  # fmt: skip
        for j in done[: len(self._jobs) - self._keep]:
            del self._jobs[j.job_id]

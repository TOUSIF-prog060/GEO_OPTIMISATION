"""API tests: the job manager, and endpoints with the database and engines replaced."""

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api import main
from src.api.jobs import JobManager
from src.config import Settings, load_project_config

# ---------------------------------------------------------------- job manager


def wait(jm: JobManager, job_id: str, timeout: float = 5.0):
    end = time.time() + timeout
    while time.time() < end:
        job = jm.get(job_id)
        if job and job.status in {"done", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_job_runs_and_reports_progress() -> None:
    jm = JobManager()

    def fn(progress):
        progress({"done": 1, "total": 2})
        return {"ok": True}

    job = wait(jm, jm.submit("demo", {"a": 1}, fn).job_id)
    assert job.status == "done" and job.result == {"ok": True}
    assert job.progress == {"done": 1, "total": 2} and job.finished_at


def test_job_failure_is_recorded_not_raised() -> None:
    jm = JobManager()

    def fn(progress):
        raise ValueError("boom")

    job = wait(jm, jm.submit("demo", {}, fn).job_id)
    assert job.status == "failed" and job.error == "ValueError: boom"


def test_job_list_trims_finished() -> None:
    jm = JobManager(keep=2)
    ids = [jm.submit("d", {}, lambda p: None).job_id for _ in range(3)]
    for i in ids:
        if jm.get(i):
            wait(jm, i)
    jm.submit("d", {}, lambda p: None)
    assert len(jm.list()) <= 3


# ---------------------------------------------------------------- endpoints


class FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def client(monkeypatch) -> TestClient:
    settings = Settings(project=load_project_config(), gemini_api_key="g")
    main.app.dependency_overrides[main.settings_dep] = lambda: settings
    main.app.dependency_overrides[main.db] = lambda: FakeConn()
    main.jobs = JobManager()
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_status_reports_keys_without_values(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(main, "check_connection", lambda: (True, "PostgreSQL 17"))
    s = Settings(project=load_project_config(), gemini_api_key="secret-g", supabase_db_url="x")
    main.app.dependency_overrides[main.settings_dep] = lambda: s
    body = client.get("/api/status").json()
    keys = {p["name"]: p["has_key"] for p in body["providers"]}
    assert keys == {"perplexity": False, "openai": False, "gemini": True}
    assert "secret-g" not in str(body)
    assert body["db"]["ok"] is True


def test_overview_uses_reporting(client: TestClient, monkeypatch) -> None:
    hist = [{"provider": "gemini", "brand": "Sephora India", "is_target": True,
             "started_at": "2026-11-23", "n_responses": 5, "mention_rate": 0.4}]  # fmt: skip
    monkeypatch.setattr(main.reporting, "visibility_history", lambda c: hist)
    monkeypatch.setattr(main.reporting, "pipeline_counts", lambda c: {"runs": 1})
    monkeypatch.setattr(main.reporting, "category_matrix", lambda c: [])
    monkeypatch.setattr(main.reporting, "top_opportunities", lambda c, n: [])
    monkeypatch.setattr(main.reporting, "ops_stats", lambda c: [])
    body = client.get("/api/overview").json()
    assert body["kpis"][0]["value"] == 0.4 and body["leaders"] == {"gemini": "Sephora India"}


def test_discovery_job_refuses_missing_keys(client: TestClient) -> None:
    r = client.post("/api/jobs/discovery", json={"providers": ["openai"], "limit": 1})
    assert r.status_code == 400 and "openai" in r.json()["detail"]


def test_discovery_job_runs_with_progress(client: TestClient, monkeypatch) -> None:
    def fake_discover(panel, providers, repeats, limit, prompt_ids, on_progress):
        on_progress("gemini", 1, 1)
        return ["run-1"]

    monkeypatch.setattr(main.services, "discover", fake_discover)
    job = client.post("/api/jobs/discovery", json={"providers": ["gemini"], "limit": 1}).json()
    done = wait(main.jobs, job["job_id"])
    assert done.result == {"run_ids": ["run-1"]}
    assert done.progress == {"provider": "gemini", "done": 1, "total": 1}
    assert client.get(f"/api/jobs/{job['job_id']}").json()["status"] == "done"


def test_unknown_job_is_404(client: TestClient) -> None:
    assert client.get("/api/jobs/nope").status_code == 404


def test_llm_steps_need_openai_key(client: TestClient) -> None:
    r = client.post("/api/jobs/diagnose", json={"run_id": "r", "label_sentiment": True})
    assert r.status_code == 400
    assert client.post("/api/jobs/draft", json={"opportunity_id": "o"}).status_code == 400


def test_review_validates_status(client: TestClient, monkeypatch) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(main, "review_recommendation", lambda *a: calls.append(a))
    ok = client.post(
        "/api/recommendations/r1/review", json={"status": "approved", "reviewer": "TS"}
    )
    assert ok.status_code == 200 and calls[0][1:] == ("r1", "approved", "TS", "")
    bad = client.post("/api/recommendations/r1/review", json={"status": "maybe", "reviewer": "TS"})
    assert bad.status_code == 422


def test_run_404(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(main.queries, "run_detail", lambda c, r: None)
    assert client.get("/api/runs/x").status_code == 404


def test_panels_lists_csv_versions(client: TestClient) -> None:
    panels = client.get("/api/panels").json()
    v0 = next(p for p in panels if p["version"] == "v0")
    assert len(v0["prompts"]) == 30

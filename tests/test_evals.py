"""Regression guards for the sandbox evaluation. Known parser limitations (list positions in
headings, tables, comparison sections) are measured by the suite, not asserted away here."""

from evals.agent_eval import eval_agent
from evals.gold import MENTION_CASES, URL_CASES
from evals.run import to_markdown
from evals.suites import eval_gaps, eval_measurement, eval_metrics


def test_gold_ids_unique() -> None:
    assert len({c.case_id for c in MENTION_CASES}) == len(MENTION_CASES)
    assert len({u.url for u in URL_CASES}) == len(URL_CASES)


def test_mention_detection_stays_perfect_on_gold() -> None:
    m = eval_measurement()["metrics"]
    assert m["mention"]["f1"] == 1.0
    assert m["citations"]["domain_accuracy"] == 1.0


def test_metric_calculations_correct() -> None:
    out = eval_metrics()
    assert out["metrics"]["accuracy"] == 1.0, out["failures"]


def test_gap_detection_finds_every_planted_gap() -> None:
    assert eval_gaps()["metrics"]["recall"] == 1.0


def test_agent_scenarios_all_pass() -> None:
    out = eval_agent()
    assert out["metrics"]["pass_rate"] == 1.0, out["failures"]


def test_report_renders() -> None:
    report = {"generated_at": "t", "gold_version": "g", "sandbox": "s",
              "measurement": eval_measurement(), "metrics": eval_metrics(),
              "gaps": eval_gaps(), "agent": {"metrics": {"scenarios": 1, "passed": 1,
              "pass_rate": 1.0, "mean_seconds": 0.1}, "failures": []}}  # fmt: skip
    md = to_markdown(report)
    assert "Brand mentions" in md and "What went wrong" in md


def test_pdf_report_html_builds_without_db() -> None:
    from evals.report_pdf import build_html
    from evals.run import run

    page = build_html(run(), None)
    for heading in ("Summary scorecard", "Brand mention detection", "List position",
                    "Metric calculations", "Gap detection", "Agent behaviour",
                    "Live model check", "Real data", "Sign-off", "Appendix A"):  # fmt: skip
        assert heading in page
    assert page.count("Manual review") >= 8

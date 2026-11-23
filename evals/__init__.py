"""Sandbox evaluation suite: measures how accurate the pipeline and agent are, without touching
the production database or paid APIs (except the opt-in live model check).

Run:  python -m evals.run            (offline suites)
      python -m evals.run --live     (+ a small real Gemini stability test, in memory only)
"""

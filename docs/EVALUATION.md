# Evaluation (sandbox)

How accurate the pipeline and the agent are, measured in a sandbox: everything runs in memory,
nothing is written to the database, and the offline suites make no network calls.

```bash
python -m evals.run            # offline suites (free); report in reports/evals/
python -m evals.run --live     # + live model stability test (real calls, still no DB writes)
python -m evals.report_pdf     # printable PDF: charts, comparisons, every case, review boxes
```

The PDF (`reports/evals/evaluation_report_<time>.pdf`) has a scorecard, a chart and an
expected-vs-actual table for every suite, the latest real run compared across brands with 95%
intervals, findings, a sign-off block, and an appendix listing every test decision with a tick
box. It is printed with the installed Chrome or Edge; no extra Python packages. Chart colours
are the brand hues re-stepped to pass colour-blind and contrast checks for print.

## What is measured

| Suite | Ground truth | Parameters |
|---|---|---|
| Measurement (`evals/gold.py`) | 30 synthetic answers (90 brand decisions) and 10 URLs, correct by construction. Several copy real Gemini formatting | Mention precision, recall, F1, accuracy; list-position exact match, found-rate, mean absolute error, spurious-rank rate; citation domain and owner accuracy |
| Metric calculation | 4 answers and 4 citations with hand-computed values; a 3-repeat question for repeatability | Mention rate, share of voice, average rank, citation share, repeatability agreement |
| Gap detection | 6 scenarios with planted gaps (or none) | Precision, recall, scenarios fully correct |
| Agent | 11 scripted scenarios on the real LangGraph workflow, fault injection, in-memory checkpoints | Pass rate per scenario: step order, human-review gate, approvals applied exactly, forged approvals ignored, retry on transient failure, clean failure, partial-failure recovery, no-cost reuse, max-drafts limit |
| Live model (opt-in) | None (no right answer exists) | Success rate, latency median and p95, sources per answer, target mention rate, mention agreement across repeats, list-position stability, cited-source overlap (Jaccard) |

The gold set measures the **rules**, not the AI engines. Accuracy on real answers still needs
human labels (Check accuracy page, `scripts/validation.py`).

## Results (gold_v1, 23 Nov 2026)

| Area | Parameter | Result |
|---|---|---|
| Brand mentions | Precision / recall / F1 | 100% / 100% / 100% (90 decisions) |
| List position | Exact match, all mentioned brands | 70.8% |
| | Found when the brand is truly ranked (n=26) | 84.6% |
| | Exact when truly ranked | 69.2%, mean error 0.18 positions |
| | Rank given when the answer does not rank (n=22) | 27.3% |
| Citations | Domain and owner brand | 100% / 100% (10 URLs) |
| Metric calculation | Checks correct | 15 / 15 |
| Gap detection | Precision / recall | 80% / 100% (5 of 6 scenarios fully correct) |
| Agent | Scenarios passed | 11 / 11 |
| Live model (Gemini 2.5 Flash) | Not measured | Free-tier daily quota exhausted (see below) |

## Findings

1. **Brand mentions are reliable.** Aliases, domains, case, possessives and look-alike words
   (tiramisu, tirade, Tirana) are all handled. Note the definition: "not on Nykaa" counts as a
   mention of Nykaa; sentiment is a separate (LLM) label.
2. **List position is the weak spot.**
   - An intro heading (`## Where to buy`) is counted as list item 1, so every brand below it is
     shifted down by one. This is the common Gemini format.
   - Bold numbers (`**1. Nykaa**`) and Markdown tables are not read as lists.
   - Comparison answers ("**Nykaa** · Range · Price …", "Choose Tira if …") get positions even
     though nothing is ranked; so does a brand named in passing inside another option.
   Impact: average-rank figures and **ranking gaps** can be wrong for comparison questions.
   The gap found in the first real run ("Sephora India ranks lower than Nykaa in 'retailer'
   lists") rests on 4 answers: 1 is a comparison question ("Nykaa vs Sephora India"), where a
   position is not meaningful; the other 3 are genuine "where to buy" lists. Check them by hand
   before acting on it.
3. **Ranking gaps can fire on very few ranked answers.** The rule checks the category's answer
   count, not how many answers actually rank the brand. In the sandbox it fired on 2 ranked
   answers out of 10 (confidence 17%). Its low confidence keeps it low in priority, but a
   minimum number of ranked answers would remove it.
4. **Metrics and the agent behave exactly as specified.** All hand-computed metrics match. The
   agent never acts before human review, ignores approvals for drafts it did not create, retries
   transient failures, fails cleanly on persistent ones and keeps going when one run fails.
5. **The Gemini free tier allows 20 requests per model per day.** The live test hit the limit
   (7 of 9 calls returned 429; resets after about 11 hours). This also explains the 13 failed calls
   in the first 30-question run. A full baseline (30 questions × 3 repeats = 90 calls) needs a
   paid key, several days, or a model with a larger free quota.

## Next steps

- Fix list-position parsing: skip headings that contain no brand before the first list item,
  read bold-numbered lines and Markdown tables, and give no position in comparison-style answers
  (version the parser as v2 and re-measure; keep v1 results for comparison).
- Require a minimum number of ranked answers for ranking gaps.
- Re-run `python -m evals.run --live` when the Gemini quota resets, or with a paid key.
- Label 100 real answers (two people) to measure accuracy on real data, not only the gold set.

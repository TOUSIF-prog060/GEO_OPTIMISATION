# Visibility model: overview

Which factors drive AI engines to name Sephora India? Short version for presentations. The full
detail is in the model card written with each training run (`reports/models/<run>/model_card.md`)
and in [DECISION_LOG.md](DECISION_LOG.md).

## Question

When people ask AI engines for beauty recommendations in India, what makes them name Sephora
India?

## Data

- 706 real answers in the team's clean dataset (data-v1.0, `use_in_model = yes`).
- 5 engines: ChatGPT, Claude, Gemini, Google AI Mode, Perplexity.
- 40 questions: 20 English, 20 Hinglish.
- Sephora India is named in 110 answers (15.6%); Nykaa in 300 (42.5%).

## Models

| Model | What it does | Why it's included |
|---|---|---|
| Baseline | Sephora's naming rate for each engine × question type, with 95% intervals | The simple benchmark every model must beat |
| M1: logistic regression (L2) | Odds that Sephora is named, factor by factor | Easy for a marketer to read |
| M2: random forest, gradient boosting | Non-linear effects and interactions | Checks whether a more complex model adds anything |

Factors: engine, question type, category, language, collection method.

## How it was tested

- 5-fold cross-validation grouped by question. The English and Hinglish versions of a question
  always stay in the same fold, so every model is scored on questions it has never seen.
- Repeated 10 times with reshuffled folds. Each run is scored on all of its held-out predictions
  pooled together, which is steadier than averaging five small folds.
- Every model is tested on the same folds, so each run is a head-to-head comparison.
- M1's regularisation strength and every model's F1 cut-off are tuned only on the training part
  of each fold, using inner grouped splits. The test questions are never used for tuning.
- PR-AUC: how well a model ranks the answers that name Sephora above those that don't. It suits
  a target that's present in only 16% of answers, where plain accuracy would mislead. A model
  that ranks at random scores about 0.16.
- Brier score: how well calibrated the predicted probabilities are.
- Every run is logged in MLflow with its data checksum, settings and git commit, so it can be
  repeated exactly.

## Result

| Model | PR-AUC (mean ± sd, 10 runs) | Runs beating baseline | Brier | Strict-set PR-AUC |
|---|---|---|---|---|
| Baseline | 0.213 ± 0.003 | – | 0.132 | 0.193 |
| M1 logistic regression | 0.250 ± 0.051 | 6 of 10 | 0.138 | 0.139 |
| M2 random forest | 0.177 ± 0.021 | 0 of 10 | 0.136 | 0.136 |
| M2 gradient boosting | 0.217 ± 0.023 | 5 of 10 | 0.141 | 0.165 |

- On the main set (706 answers), M1 logistic regression passes the charter's rule. It is the
  simplest model that beats the baseline (in 6 of 10 runs) and is within one standard error of
  the best.
- On the strict set (640 answers, without repeated or suspect answers), M1 loses every run and
  the baseline is kept.
- So M1's lead is real but fragile: treat it as tentative. Every model is only modestly better
  than random ranking.
- With only 19 question groups, each type of question rests on a few questions. More
  questions, not more complex models, would improve prediction.
- The random forest is the weakest: with this few questions it overfits.

## What drives Sephora's visibility

These odds ratios describe association in this sample, not cause. Intervals are clustered by
question.

| Factor | Odds ratio | 95% interval |
|---|---|---|
| "Where to buy" vs budget question | 187 | 44 – 789 |
| Shortlist vs budget question | 9.8 | 2.0 – 48 |
| Gemini vs ChatGPT | 0.36 | 0.15 – 0.84 |
| Perplexity vs ChatGPT | 0.14 | 0.04 – 0.57 |
| Sunscreen vs foundation | 0.04 | 0.01 – 0.28 |
| Acne skincare vs foundation | 0.02 | 0.00 – 0.24 |
| Hinglish vs English | 1.2 | 0.47 – 3.1 (no clear effect) |

- Sephora appears in 94% of "where to buy" answers, but that rests on a single question.
- It is almost never named for sunscreen or acne skincare, and is strongest in foundation and
  fragrance.
- Neither language nor collection method (fresh chat vs batched chat) shows a clear effect.

## So what for Sephora India

Sephora is visible when people ask where to buy or ask for a shortlist. It is close to invisible
in everyday skincare questions, and on Perplexity and Gemini. The content opportunities lie
there.

## Limits

- The data is observational, so the results show association, not cause.
- 110 positives over 15 model columns is 7.3 per column, below the charter's guideline of 10,
  so individual odds ratios are rough.
- Most answers came from batched chats.
- Brand mentions are detected by rules and haven't been checked by hand yet.
- Plan tier isn't a factor because it follows the engine exactly (ChatGPT and Claude rows are
  paid, the rest free).
- Model version isn't a factor because it is missing for most rows.

## On the dashboard

The **What drives visibility** page (`/models`) shows:
- the rate at which each level of each factor names Sephora, with 95% intervals;
- the odds ratios as a forest plot;
- the engine × question type grid;
- the model comparison, with the strict-set check.

It reads the latest training run from `reports/models/`, through `GET /api/models`.

## Reproduce

```bash
python -m src.modelling.train --data <path to responses_clean_v1.0.csv>            # main set
python -m src.modelling.train --data <path to responses_clean_v1.0.csv> --strict   # strict set
mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db                           # browse runs
```

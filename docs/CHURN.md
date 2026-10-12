# Milestone 05A: churn baseline

This is a synthetic modeling exercise, not a production churn predictor. The prediction unit is one active AtlasCloud customer at a cutoff date. The target is a cancellation strictly after the cutoff and within the next 90 days. Only events with `event_date < cutoff_date` enter features; the 180-day feature window is split into two 90-day usage totals. Other features are tenure, plan, region, and recent payment-failure and support-ticket counts.

## Reproduce in order

```sh
make seed
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra ml --locked
make churn-seed
make churn-snapshots
make churn-eval
```

The first step creates the existing 200 July 2026 customers. `churn-seed` verifies the base manifest and uses those exact IDs, plans, regions, join dates, and historical tickets for the final test cohort. It creates separate synthetic historical customers for training and validation. All cohorts receive deterministic synthetic usage/payment activity and cancellation outcomes. The original business tables and policy corpus remain unchanged. Source CSV checksums and a seed are saved in `data/generated/churn/manifest.json`; `snapshots.csv` is a derived inspection artifact. `churn-eval` rebuilds snapshots from the checked source files, not from that export.

| Split | Cutoff | Customers | Label period |
| --- | --- | ---: | --- |
| Train | 2025-10-01 | 400 | 2025-10-02 through 2025-12-30 |
| Validation | 2026-01-01 | 200 | 2026-01-02 through 2026-04-01 |
| Test | 2026-07-01 | 200 | 2026-07-02 through 2026-09-29 |

Customer IDs do not cross splits. The logistic model is fit on train only. The validation and test scores are reported without threshold tuning. `reports/churn_baseline_dev.json` records average precision, ROC AUC, Brier score, prevalence, and mean prediction for each split. The test cohort is temporally later and the target horizon has elapsed by the current project date. No test-set feedback was used to alter the model.

The simulation itself generates labels from an unobserved risk flag, failed payments, and plan; usage decline is a correlated signal. This makes the benchmark useful for checking temporal feature code and a basic ML pipeline, but its metrics do not estimate business performance. The base orders contain the same monthly purchase pattern for every current customer, so they are excluded from this first baseline. For 05B, add stronger models, train-only preprocessing, calibration, business thresholds, and explanations. A real deployment would need actual dated cancellation events and independently reviewed labels.

## Milestone 05B: comparison, calibration and explanations

Install the advanced optional dependencies and run the comparison after 05A seeding:

```sh
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra ml --extra ml-advanced --locked
make churn-advanced
```

The command fits logistic regression and a shallow gradient-boosting classifier on the training cohort. It chooses the highest validation average precision, using lower validation Brier as a tie-break. The selected fitted model is frozen before a sigmoid calibrator is fit on the validation cohort. The July test cohort is used for final reporting; it does not choose the model, calibrator, or outreach rule. Validation calibration metrics are in-sample for that calibrator and should not be read as unbiased validation.

The outreach rule assumes 3 synthetic value units per contact, 100 units retained if a customer stays, a 25% intervention success rate, and capacity for at most 10% of customers. It contacts the highest calibrated risks only when their probability is at least the break-even value `3/(100*0.25) = 0.12`. The reported net value uses observed synthetic churn labels and assumes that success rate; it is **hypothetical**, not an observed treatment effect. There was no randomized intervention or causal estimate.

SHAP explains the selected *uncalibrated* model's raw log-odds. The report contains global mean absolute attributions and a few high-risk synthetic examples. These attributions describe model behavior, not why a real customer would churn. A local SQLite-backed MLflow run logs the dataset hash, configuration, split metrics, report and a joblib model artifact under `.runtime/`; no hosted tracking service is used. Load that pickle only from the trusted local project. The case-level JSON is `reports/churn_advanced_dev.json`, with interpretation in `reports/churn_advanced_dev.md`.

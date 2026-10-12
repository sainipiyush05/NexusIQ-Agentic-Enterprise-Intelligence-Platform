# Churn 05B development diagnostic

The 400-account training, 200-account validation and 200-account July test cohorts are synthetic and customer-disjoint. All input features precede their cohort's prediction cutoff. The report is reproducible with `make churn-advanced` after the setup in `docs/CHURN.md`; case-level metrics, source checksums and the local MLflow run ID are in `churn_advanced_dev.json`.

| Model | Validation average precision | Validation Brier | July test average precision | July test Brier |
| --- | ---: | ---: | ---: | ---: |
| Logistic | 0.454 | 0.0895 | 0.373 | 0.1144 |
| Gradient boosting | 0.407 | 0.0939 | 0.286 | 0.1230 |

The validation rule chose logistic. A sigmoid calibrator fit to validation predictions preserved ranking but **worsened** July test Brier to 0.1156. The validation calibrated Brier of 0.0882 is in-sample for the calibrator. These results do not justify a claim that calibration helped.

At a 10% contact capacity and a 0.12 break-even probability under the declared synthetic cost assumptions, the rule contacted 20 July customers and identified 11 of 30 churners. Precision among contacts was 55% and churner recall was 36.7%. The calculated 215-unit net value assumes a 25% intervention success rate; no intervention was performed, so it is not measured business lift.

SHAP's largest global absolute contributions for the selected logistic model were usage change, usage in the previous and recent 90-day windows, and support tickets. The values explain raw model log-odds and cannot establish causal drivers. Small synthetic samples, a single validation cohort, and shared simulation rules limit all metrics. The July test was reported after model selection; it was not used to tune the candidates or decision assumptions.

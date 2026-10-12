"""Validation-selected churn comparison, calibration, decision policy and SHAP."""
import json
import math
import hashlib
from pathlib import Path

from .churn import CATEGORICAL, NUMERIC, SPLITS, build_snapshots
from .config import REPORTS, ROOT

CONTACT_COST = 3.0
RETAINED_VALUE = 100.0
INTERVENTION_SUCCESS = 0.25
CAPACITY_FRACTION = 0.10
VALUE_THRESHOLD = CONTACT_COST / (RETAINED_VALUE * INTERVENTION_SUCCESS)
REPORT = REPORTS / 'churn_advanced_dev.json'


def feature_rows(rows):
    columns = NUMERIC + CATEGORICAL
    return [{key: row[key] for key in columns} for row in rows]


def metrics(labels, probabilities):
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
    return dict(count=len(labels), positives=sum(labels), prevalence=sum(labels)/len(labels),
                average_precision=float(average_precision_score(labels, probabilities)),
                roc_auc=float(roc_auc_score(labels, probabilities)) if len(set(labels)) == 2 else None,
                brier=float(brier_score_loss(labels, probabilities)),
                mean_prediction=float(sum(probabilities)/len(probabilities)))


def outreach_decision(probabilities, labels, capacity_fraction=CAPACITY_FRACTION,
                      value_threshold=VALUE_THRESHOLD):
    """Rank by calibrated risk; contact only above break-even and within capacity."""
    if len(probabilities) != len(labels) or len(probabilities) == 0:
        raise ValueError('Probability and label lengths must agree and be nonempty')
    if not 0 < capacity_fraction <= 1 or not 0 <= value_threshold <= 1:
        raise ValueError('Invalid outreach assumptions')
    capacity = max(1, math.floor(len(labels)*capacity_fraction))
    ranked = sorted(range(len(labels)), key=lambda i: (-probabilities[i], i))
    selected = [i for i in ranked[:capacity] if probabilities[i] >= value_threshold]
    true_churn = sum(labels[i] for i in selected)
    return dict(capacity=capacity, contacted=len(selected), true_churn_contacted=true_churn,
                precision_at_contact=true_churn/len(selected) if selected else None,
                churn_recall=true_churn/sum(labels) if sum(labels) else None,
                hypothetical_net_value=round(true_churn*RETAINED_VALUE*INTERVENTION_SUCCESS-
                                              len(selected)*CONTACT_COST, 2),
                selected_indices=selected)


def choose_candidate(validation):
    """Select without consulting calibration or the later test cohort."""
    if not validation:
        raise ValueError('At least one validation candidate is required')
    return sorted(validation, key=lambda name: (-validation[name]['average_precision'],
                                                 validation[name]['brier'], name))[0]


def _explain_selected(name, model, train_x, test_x, test_rows, probabilities, limit=5):
    import numpy as np
    import shap
    transform = model.named_steps['features']
    names = list(transform.get_feature_names_out())
    if name == 'logistic':
        train_matrix = model.named_steps['scale'].transform(transform.transform(train_x))
        test_matrix = model.named_steps['scale'].transform(transform.transform(test_x))
        # A fixed training-only background bounds explanation cost and sampling.
        explainer = shap.LinearExplainer(model.named_steps['classifier'], train_matrix[:100])
    else:
        train_matrix = transform.transform(train_x)
        test_matrix = transform.transform(test_x)
        explainer = shap.TreeExplainer(model.named_steps['classifier'])
    values = np.asarray(explainer.shap_values(test_matrix))
    if values.shape != (len(test_rows), len(names)) or not np.isfinite(values).all():
        raise ValueError('Unexpected SHAP explanation shape or value')
    mean_abs = np.abs(values).mean(axis=0)
    global_features = [dict(feature=names[i], mean_abs_shap=float(mean_abs[i]))
                       for i in np.argsort(-mean_abs)[:10]]
    top = sorted(range(len(test_rows)), key=lambda i: (-probabilities[i], test_rows[i]['customer_id']))[:limit]
    examples = []
    for row_index in top:
        ranked = np.argsort(-np.abs(values[row_index]))[:5]
        examples.append(dict(customer_id=test_rows[row_index]['customer_id'],
                             predicted_risk=float(probabilities[row_index]),
                             feature_effects=[dict(feature=names[j], shap_value=float(values[row_index,j]))
                                              for j in ranked]))
    return dict(model=name, output_space='raw_log_odds', background_rows=min(100, len(train_x)),
                global_features=global_features,
                highest_risk_examples=examples,
                note='SHAP explains the uncalibrated model score in log-odds, not the calibrated probability or a causal effect.')


def compare_models(directory=None, track=True):
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.frozen import FrozenEstimator
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    snapshots, manifest = build_snapshots(directory) if directory is not None else build_snapshots()
    groups = {name: [row for row in snapshots if row['split'] == name] for name in SPLITS}
    if any(len(groups[name]) != SPLITS[name][1] for name in SPLITS):
        raise ValueError('Temporal cohort sizes changed')
    ids = [row['customer_id'] for row in snapshots]
    if len(ids) != len(set(ids)):
        raise ValueError('Customer IDs cross temporal cohorts')
    x = {name: feature_rows(rows) for name, rows in groups.items()}
    y = {name: [row['churned'] for row in rows] for name, rows in groups.items()}
    models = {
        'logistic': Pipeline([('features', DictVectorizer()),
                              ('scale', StandardScaler(with_mean=False)),
                              ('classifier', LogisticRegression(max_iter=1000, random_state=42))]),
        'gradient_boosting': Pipeline([('features', DictVectorizer(sparse=False)),
                                       ('classifier', GradientBoostingClassifier(
                                           n_estimators=100, max_depth=2, learning_rate=.05, random_state=42))]),
    }
    validation = {}
    for name, model in models.items():
        model.fit(x['train'], y['train'])
        validation[name] = metrics(y['validation'], model.predict_proba(x['validation'])[:,1])
    # Frozen, explicit selection: validation average precision, then Brier, then name.
    selected = choose_candidate(validation)
    calibrated = CalibratedClassifierCV(FrozenEstimator(models[selected]), method='sigmoid')
    calibrated.fit(x['validation'], y['validation'])
    val_probs = calibrated.predict_proba(x['validation'])[:,1]
    test_probs = calibrated.predict_proba(x['test'])[:,1]
    test_metrics = {name: metrics(y['test'], model.predict_proba(x['test'])[:,1])
                    for name, model in models.items()}
    policy = outreach_decision(test_probs, y['test'])
    val_policy = outreach_decision(val_probs, y['validation'])
    report = dict(dataset_sha256=manifest['base_dataset_sha256'], source_files=manifest['files'],
                  feature_columns=list(NUMERIC+CATEGORICAL),
                  split_cutoffs=manifest['split_cutoffs'],
                  selection_rule='Highest validation average precision; Brier then model name break ties',
                  validation_candidates=validation, selected_model=selected,
                  calibration=dict(method='sigmoid', fit_split='validation',
                                   validation_metrics=metrics(y['validation'], val_probs),
                                   test_metrics=metrics(y['test'], test_probs),
                                   caveat='Validation calibration metrics are in-sample for the calibrator.'),
                  test_candidates=test_metrics,
                  decision_assumptions=dict(contact_cost=CONTACT_COST, retained_value=RETAINED_VALUE,
                                            intervention_success=INTERVENTION_SUCCESS,
                                            capacity_fraction=CAPACITY_FRACTION,
                                            break_even_probability=VALUE_THRESHOLD),
                  validation_decision={k:v for k,v in val_policy.items() if k!='selected_indices'},
                  test_decision={k:v for k,v in policy.items() if k!='selected_indices'},
                  explanations=_explain_selected(selected, models[selected], x['train'], x['test'], groups['test'], test_probs),
                  limitations='All labels and much activity are synthetic; one small validation cohort selected/calibrated the model. Test metrics are a single temporal diagnostic, not an estimate of real business lift. SHAP is associative, not causal.')
    if track:
        import joblib
        artifact = ROOT/'.runtime/churn_05b_calibrated.joblib'
        artifact.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(calibrated, artifact)
        report['model_artifact'] = dict(path=str(artifact), sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
                                        note='Local joblib pickle; load only from this trusted project artifact.')
        report['mlflow'] = log_local_run(report)
    return report


def log_local_run(report):
    import os
    os.environ.setdefault('MLFLOW_DISABLE_AGENT_HINT', '1')
    import mlflow
    store = ROOT/'.runtime/mlflow.db'
    store.parent.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(f'sqlite:///{store}')
    mlflow.set_experiment('nexusiq-synthetic-churn')
    with mlflow.start_run(run_name='05B-validation-selected-comparison') as run:
        mlflow.log_params(dict(seed=42, selected_model=report['selected_model'],
                               calibration='sigmoid', capacity_fraction=CAPACITY_FRACTION,
                               break_even_probability=VALUE_THRESHOLD,
                               base_dataset_sha256=report['dataset_sha256']))
        mlflow.log_metrics({f'validation_{name}_pr_auc': values['average_precision']
                            for name, values in report['validation_candidates'].items()})
        mlflow.log_metrics({f'test_{name}_pr_auc': values['average_precision']
                            for name, values in report['test_candidates'].items()})
        mlflow.log_metrics(dict(test_calibrated_brier=report['calibration']['test_metrics']['brier'],
                                test_hypothetical_net_value=report['test_decision']['hypothetical_net_value']))
        mlflow.log_dict(report, 'churn_advanced_report.json')
        mlflow.log_artifact(report['model_artifact']['path'], artifact_path='model')
        return dict(run_id=run.info.run_id, tracking_uri=f'sqlite:///{store}')


def write_report(report, path=REPORT):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2))
    return path

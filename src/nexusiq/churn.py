"""Reproducible synthetic churn snapshots and a temporal logistic baseline."""
import csv
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .config import DATA, REPORTS

CHURN_DATA = DATA / 'churn'
SPLITS = {'train': (date(2025, 10, 1), 400),
          'validation': (date(2026, 1, 1), 200),
          'test': (date(2026, 7, 1), 200)}
HORIZON_DAYS = 90
EVENT_TYPES = {'usage_sessions', 'payment_failed', 'support_ticket'}
NUMERIC = ('tenure_days', 'usage_recent_90d', 'usage_previous_90d',
           'usage_change', 'payment_failures_90d', 'support_tickets_90d')
CATEGORICAL = ('region', 'plan')


def _read_csv(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def _write_csv(path, rows, fields):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_churn(destination=CHURN_DATA, source=DATA, seed=42):
    """Keep historic synthetic cohorts separate from the July demo customers."""
    source, destination = Path(source), Path(destination)
    base = json.loads((source/'manifest.json').read_text())
    for name in ('customers.csv', 'tickets.csv'):
        if _sha(source/name) != base['tables'][name]:
            raise ValueError('Base business data checksum mismatch')
    current = _read_csv(source/'customers.csv')
    tickets = _read_csv(source/'tickets.csv')
    if len(current) != SPLITS['test'][1] or len({r['customer_id'] for r in current}) != len(current):
        raise ValueError('Expected 200 distinct current customers')
    rng = random.Random(seed)
    accounts, events, cancellations = [], [], []
    for split, (cutoff, count) in SPLITS.items():
        for i in range(count):
            if split == 'test':
                customer = current[i]
                customer_id = customer['customer_id']
                region, plan, joined = customer['region'], customer['plan'], date.fromisoformat(customer['join_date'])
                if joined >= cutoff:
                    raise ValueError('Current customer joined after cutoff')
            else:
                customer_id = f'H{split[0].upper()}{i+1:04d}'
                region = rng.choice(('APAC', 'EMEA', 'AMER'))
                plan = rng.choice(('Starter', 'Growth', 'Enterprise'))
                joined = cutoff - timedelta(days=rng.randint(270, 900))
            accounts.append(dict(customer_id=customer_id, tenant_id='atlascloud', split=split,
                                 cutoff_date=cutoff.isoformat(), region=region, plan=plan,
                                 join_date=joined.isoformat()))
            at_risk = rng.random() < .32
            baseline = rng.randint(18, 55)
            failures = 0
            for month_back in range(6, 0, -1):
                occurred = cutoff - timedelta(days=month_back*30)
                drop = rng.uniform(.18, .62) if at_risk and month_back <= 3 else 0
                usage = max(0, round(baseline*(1-drop) + rng.gauss(0, 4)))
                events.append(dict(customer_id=customer_id, event_date=occurred.isoformat(),
                                   event_type='usage_sessions', value=usage))
                if rng.random() < (.19 if at_risk else .025):
                    failures += 1
                    events.append(dict(customer_id=customer_id, event_date=occurred.isoformat(),
                                       event_type='payment_failed', value=1))
                if split != 'test' and rng.random() < (.28 if at_risk else .10):
                    events.append(dict(customer_id=customer_id, event_date=occurred.isoformat(),
                                       event_type='support_ticket', value=1))
            if split == 'test':
                for ticket in tickets:
                    if ticket['customer_id'] == customer_id:
                        events.append(dict(customer_id=customer_id, event_date=ticket['opened_at'],
                                           event_type='support_ticket', value=1))
            risk = -2.6 + (1.3 if at_risk else 0) + .5*failures + (.25 if plan == 'Starter' else 0)
            if rng.random() < 1/(1+math.exp(-risk)):
                cancellation = cutoff + timedelta(days=rng.randint(1, HORIZON_DAYS))
                cancellations.append(dict(customer_id=customer_id, cancellation_date=cancellation.isoformat()))
    destination.mkdir(parents=True, exist_ok=True)
    files = {'accounts.csv': (accounts, ('customer_id','tenant_id','split','cutoff_date','region','plan','join_date')),
             'events.csv': (events, ('customer_id','event_date','event_type','value')),
             'cancellations.csv': (cancellations, ('customer_id','cancellation_date'))}
    for name, (rows, fields) in files.items():
        _write_csv(destination/name, rows, fields)
    manifest = dict(version='churn-v1', seed=seed, base_dataset_sha256=base['dataset_sha256'],
                    horizon_days=HORIZON_DAYS, split_cutoffs={name: cutoff.isoformat() for name,(cutoff,_) in SPLITS.items()},
                    counts=dict(accounts=len(accounts), events=len(events), cancellations=len(cancellations)),
                    files={name: _sha(destination/name) for name in files})
    (destination/'manifest.json').write_text(json.dumps(manifest, indent=2))
    return manifest


def build_snapshots(directory=CHURN_DATA):
    """Build one row per active account; every feature uses event_date < cutoff."""
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text())
    if manifest['version'] != 'churn-v1' or manifest['horizon_days'] != HORIZON_DAYS:
        raise ValueError('Unsupported churn dataset contract')
    for name, expected in manifest['files'].items():
        if _sha(directory/name) != expected:
            raise ValueError('Churn source checksum mismatch')
    accounts = _read_csv(directory/'accounts.csv')
    events = _read_csv(directory/'events.csv')
    cancellations = _read_csv(directory/'cancellations.csv')
    if len(accounts) != manifest['counts']['accounts'] or len(events) != manifest['counts']['events'] or len(cancellations) != manifest['counts']['cancellations']:
        raise ValueError('Churn source count mismatch')
    by_id = {row['customer_id']: row for row in accounts}
    if len(by_id) != len(accounts):
        raise ValueError('Duplicate account ID')
    cancel_by_id = {}
    for row in cancellations:
        cid = row['customer_id']
        if cid not in by_id or cid in cancel_by_id:
            raise ValueError('Invalid cancellation customer')
        cancel_by_id[cid] = date.fromisoformat(row['cancellation_date'])
    events_by_id = defaultdict(list)
    for row in events:
        if row['customer_id'] not in by_id or row['event_type'] not in EVENT_TYPES:
            raise ValueError('Invalid activity event')
        value = float(row['value'])
        if not math.isfinite(value) or value < 0:
            raise ValueError('Invalid activity value')
        events_by_id[row['customer_id']].append((date.fromisoformat(row['event_date']), row['event_type'], value))
    snapshots = []
    for account in accounts:
        cid = account['customer_id']
        split = account['split']
        if split not in SPLITS:
            raise ValueError('Unknown temporal split')
        cutoff = date.fromisoformat(account['cutoff_date'])
        if cutoff != SPLITS[split][0]:
            raise ValueError('Unexpected cutoff for split')
        joined = date.fromisoformat(account['join_date'])
        if joined >= cutoff:
            raise ValueError('Account starts after prediction cutoff')
        cancelled = cancel_by_id.get(cid)
        if cancelled and cancelled <= cutoff:
            continue  # Not at risk at this cutoff.
        recent = prior = failures = tickets = 0
        for occurred, kind, value in events_by_id[cid]:
            if occurred < joined:
                raise ValueError('Activity predates account')
            if not cutoff-timedelta(days=180) <= occurred < cutoff:
                continue
            if kind == 'usage_sessions':
                if occurred >= cutoff-timedelta(days=90): recent += value
                else: prior += value
            elif occurred >= cutoff-timedelta(days=90) and kind == 'payment_failed': failures += value
            elif occurred >= cutoff-timedelta(days=90) and kind == 'support_ticket': tickets += value
        snapshots.append(dict(customer_id=cid, split=split, cutoff_date=cutoff.isoformat(),
                              label_end_date=(cutoff+timedelta(days=HORIZON_DAYS)).isoformat(),
                              churned=int(cancelled is not None and cancelled <= cutoff+timedelta(days=HORIZON_DAYS)),
                              region=account['region'], plan=account['plan'], tenure_days=(cutoff-joined).days,
                              usage_recent_90d=recent, usage_previous_90d=prior,
                              usage_change=(recent-prior)/max(prior, 1),
                              payment_failures_90d=failures, support_tickets_90d=tickets))
    return snapshots, manifest


def export_snapshots(directory=CHURN_DATA):
    """Write the derived, labeled table for inspection; model code rebuilds it."""
    rows, manifest = build_snapshots(directory)
    path = Path(directory)/'snapshots.csv'
    _write_csv(path, rows, tuple(rows[0]))
    return dict(path=str(path), rows=len(rows), sha256=_sha(path), source_files=manifest['files'])


def evaluate_baseline(directory=CHURN_DATA):
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    snapshots, manifest = build_snapshots(directory)
    grouped = {split: [row for row in snapshots if row['split'] == split] for split in SPLITS}
    if any(len(grouped[split]) != SPLITS[split][1] for split in SPLITS):
        raise ValueError('Temporal split sizes changed')
    if len({row['customer_id'] for row in snapshots}) != len(snapshots):
        raise ValueError('A customer appears in more than one split')
    columns = NUMERIC + CATEGORICAL
    def xy(rows):
        return [{key: row[key] for key in columns} for row in rows], [row['churned'] for row in rows]
    train_x, train_y = xy(grouped['train'])
    if len(set(train_y)) != 2:
        raise ValueError('Training labels require both classes')
    model = Pipeline([('features', DictVectorizer()), ('scale', StandardScaler(with_mean=False)),
                      ('classifier', LogisticRegression(max_iter=1000, random_state=42))])
    model.fit(train_x, train_y)
    metrics = {}
    for split, rows in grouped.items():
        x, y = xy(rows)
        scores = model.predict_proba(x)[:,1]
        metrics[split] = dict(count=len(rows), positives=sum(y), prevalence=sum(y)/len(y),
                              average_precision=average_precision_score(y, scores),
                              roc_auc=roc_auc_score(y, scores) if len(set(y)) == 2 else None,
                              brier=brier_score_loss(y, scores),
                              mean_prediction=float(scores.mean()))
    return dict(dataset=manifest, feature_columns=list(columns), feature_rule='event_date < cutoff_date; label in (cutoff, cutoff+90 days]',
                split_metrics=metrics, model='DictVectorizer + StandardScaler + LogisticRegression, fit on train only',
                limitations='Synthetic labels generated from synthetic activity; temporal and customer-disjoint splits are a leakage check, not evidence of business performance. No threshold or calibration claim.')


def write_report(report, path=REPORTS/'churn_baseline_dev.json'):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2))
    return path

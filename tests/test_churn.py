import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from nexusiq.churn import build_snapshots, export_snapshots, seed_churn
from nexusiq.data import seed_data


class ChurnSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root/'base'
        self.churn = self.root/'churn'
        seed_data(self.base)
        self.manifest = seed_churn(self.churn, self.base)

    def tearDown(self):
        self.temp.cleanup()

    def test_deterministic_customer_disjoint_temporal_cohorts(self):
        first = {name: (self.churn/name).read_bytes() for name in self.manifest['files']}
        self.assertEqual(self.manifest, seed_churn(self.churn, self.base))
        self.assertEqual(first, {name: (self.churn/name).read_bytes() for name in self.manifest['files']})
        rows, _ = build_snapshots(self.churn)
        self.assertEqual(len(rows), 800)
        self.assertEqual(len({r['customer_id'] for r in rows}), 800)
        self.assertEqual({r['split'] for r in rows}, {'train','validation','test'})
        self.assertTrue(all(r['label_end_date'] > r['cutoff_date'] for r in rows))
        self.assertTrue(all(r['churned'] in (0,1) for r in rows))
        with (self.base/'customers.csv').open() as stream:
            current = {r['customer_id'] for r in csv.DictReader(stream)}
        self.assertEqual({r['customer_id'] for r in rows if r['split']=='test'}, current)

    def test_future_activity_does_not_change_features(self):
        before, _ = build_snapshots(self.churn)
        future = dict(customer_id=before[-1]['customer_id'], event_date='2026-07-01',
                      event_type='payment_failed', value='999')
        with (self.churn/'events.csv').open('a', newline='') as stream:
            csv.DictWriter(stream, fieldnames=list(future)).writerow(future)
        manifest_path = self.churn/'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['files']['events.csv'] = hashlib.sha256((self.churn/'events.csv').read_bytes()).hexdigest()
        manifest['counts']['events'] += 1
        manifest_path.write_text(json.dumps(manifest))
        after, _ = build_snapshots(self.churn)
        self.assertEqual(before, after)

    def test_tampered_activity_is_rejected(self):
        with (self.churn/'events.csv').open('a') as stream:
            stream.write('bad,bad,bad,bad\n')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            build_snapshots(self.churn)

    def test_labels_never_enter_feature_columns(self):
        from nexusiq.churn import NUMERIC, CATEGORICAL
        self.assertNotIn('churned', NUMERIC+CATEGORICAL)
        self.assertNotIn('cancellation_date', NUMERIC+CATEGORICAL)

    def test_snapshot_export_has_traceable_source_hashes(self):
        result = export_snapshots(self.churn)
        self.assertEqual(result['rows'], 800)
        self.assertEqual(result['source_files'], self.manifest['files'])
        self.assertEqual(result['sha256'], hashlib.sha256((self.churn/'snapshots.csv').read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()

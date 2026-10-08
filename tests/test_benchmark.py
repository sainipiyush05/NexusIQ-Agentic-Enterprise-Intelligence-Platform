import math
import tempfile
import unittest
from pathlib import Path
from nexusiq.data import seed_data
from nexusiq.benchmark import load_benchmark_index, load_cases, validate_benchmark, retrieval_metrics, run_benchmark

class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.data=Path(cls.tmp.name)
        seed_data(cls.data)
        cls.index=load_benchmark_index(cls.data)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_evidence_labels_match_sources(self):
        result=validate_benchmark(self.index)
        self.assertEqual(result['cases'],162)
        self.assertEqual(len({c.document_id for c in self.index.chunks}),40)

    def test_scope_groups_do_not_cross_splits(self):
        dev, holdout=load_cases('dev'),load_cases('holdout')
        self.assertEqual((len(dev),len(holdout)),(105,57))
        self.assertFalse({c['group_id'] for c in dev}&{c['group_id'] for c in holdout})

    def test_wrong_section_does_not_count_as_evidence(self):
        labels=[dict(document_id='policy',section='Rules')]
        hits=[dict(document_id='policy',section='Scope')]
        metrics=retrieval_metrics(hits,labels)
        self.assertEqual(metrics['evidence_recall_at_k'],0)
        self.assertEqual(metrics['ndcg_at_k'],0)

    def test_duplicate_chunks_do_not_inflate_recall(self):
        labels=[dict(document_id='a',section='Rules'),dict(document_id='b',section='Rules')]
        hits=[dict(document_id='a',section='Rules'),dict(document_id='a',section='Rules')]
        metrics=retrieval_metrics(hits,labels)
        self.assertEqual(metrics['evidence_recall_at_k'],0.5)
        self.assertEqual(metrics['evidence_precision_at_k'],0.2)
        self.assertAlmostEqual(metrics['ndcg_at_k'],1/(1+1/math.log2(3)))
        self.assertEqual(metrics['reciprocal_rank'],1)

    def test_metrics_use_cutoff_not_number_of_results(self):
        labels=[dict(document_id='a',section='Rules'),dict(document_id='b',section='Rules')]
        hits=[dict(document_id='a',section='Rules')]
        metrics=retrieval_metrics(hits,labels,5)
        self.assertEqual(metrics['evidence_precision_at_k'],0.2)
        self.assertLess(metrics['ndcg_at_k'],1)
        self.assertEqual(retrieval_metrics(hits,labels,1)['ndcg_at_k'],1)

    def test_dev_report_exposes_failures_without_oracle_filters(self):
        report=run_benchmark(directory=self.data)
        self.assertEqual(report['split'],'dev')
        self.assertEqual(report['overall']['cases'],105)
        self.assertLess(report['by_category']['paraphrase']['evidence_recall_at_k'],1)
        self.assertEqual(len(report['cases']),105)
        self.assertTrue(all(r['id'] in {c['id'] for c in load_cases('dev')} for r in report['cases']))

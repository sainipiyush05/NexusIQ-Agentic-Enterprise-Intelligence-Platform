import unittest

from nexusiq.citationverify import CitationVerifier, evaluate_dev, load_config, load_dev_cases


class FakeScorer:
    def __init__(self, scores):
        self.result = scores
        self.calls = []

    def scores(self, premise, hypothesis):
        self.calls.append((premise, hypothesis))
        return self.result


class CitationVerificationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.source = {'s1': 'The Basic plan allows 100 export rows.'}

    def test_entailment_uses_quote_as_premise(self):
        scorer = FakeScorer(dict(contradiction=.01, entailment=.95, neutral=.04))
        result = CitationVerifier(scorer, self.config).verify(
            'Basic exports have a 100-row limit.', 's1', self.source['s1'], self.source)
        self.assertEqual(result['verdict'], 'supported')
        self.assertEqual(scorer.calls, [(self.source['s1'], 'Basic exports have a 100-row limit.')])

    def test_provenance_fails_before_model_call(self):
        scorer = FakeScorer(dict(contradiction=.01, entailment=.95, neutral=.04))
        verifier = CitationVerifier(scorer, self.config)
        self.assertEqual(verifier.verify('Anything', 'other', 'Anything', self.source)['reason'],
                         'unknown_or_unauthorized_source')
        self.assertEqual(verifier.verify('Anything', 's1', 'Fabricated quote', self.source)['reason'],
                         'quote_not_in_source')
        self.assertEqual(scorer.calls, [])

    def test_contradiction_and_uncertainty(self):
        scorer = FakeScorer(dict(contradiction=.92, entailment=.04, neutral=.04))
        verifier = CitationVerifier(scorer, self.config)
        self.assertEqual(verifier.verify('Basic allows 1,000 rows.', 's1', self.source['s1'], self.source)['verdict'],
                         'unsupported')
        scorer.result = dict(contradiction=.15, entailment=.35, neutral=.50)
        self.assertEqual(verifier.verify('Basic exports cost $9.', 's1', self.source['s1'], self.source)['verdict'],
                         'uncertain')
        scorer.result = None
        self.assertEqual(verifier.verify('Long claim', 's1', self.source['s1'], self.source)['reason'],
                         'pair_exceeds_token_limit')

    def test_precision_recall_count_uncertain_as_missed_unsupported(self):
        cases = [dict(id='a', claim='A', source_id='s', quote='A', source_text='A', label='unsupported'),
                 dict(id='b', claim='B', source_id='s', quote='B', source_text='B', label='unsupported'),
                 dict(id='c', claim='C', source_id='s', quote='C', source_text='C', label='supported')]
        class StubVerifier:
            config = {'model_id': 'stub', 'revision': '0'*40}
            def verify(self, claim, *_):
                return dict(verdict={'A': 'unsupported', 'B': 'uncertain', 'C': 'unsupported'}[claim],
                            reason='test', scores=None)
        summary = evaluate_dev(StubVerifier(), cases)['summary']
        self.assertEqual((summary['true_positive'], summary['false_positive'], summary['false_negative']), (1, 1, 1))
        self.assertEqual((summary['unsupported_precision'], summary['unsupported_recall']), (.5, .5))

    def test_development_cases_validate(self):
        cases = load_dev_cases()
        self.assertEqual(len(cases), 20)
        self.assertEqual(sum(c['label']=='unsupported' for c in cases), 10)


if __name__ == '__main__':
    unittest.main()

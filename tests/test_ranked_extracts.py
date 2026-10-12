import unittest

from nexusiq.generation import validate_output
from nexusiq.rankedextracts import RankedExtractsProvider


class FakeReranker:
    metadata = {'model': 'fake'}
    def score(self, query, hits):
        return [float(hit['score']) for hit in hits]


def hit(source_id, text, score, plan='Starter'):
    return dict(source_id=source_id, document_id=source_id, title=f'APAC {plan} Policy',
                section='Rules', text=text, score=score, region='APAC', plan=plan,
                tenant_id='atlascloud', roles=['analyst'])


class RankedExtractsTests(unittest.TestCase):
    def setUp(self):
        self.provider = RankedExtractsProvider(FakeReranker())

    def test_selects_one_exact_sentence_from_scoped_evidence(self):
        hits = [hit('starter', 'Starter refund window is 7 days. Renewals are excluded.', 5),
                hit('growth', 'Growth refund window is 14 days.', 7, 'Growth')]
        result = self.provider.generate('What is the APAC Starter refund window?', hits, [])
        self.assertEqual(validate_output(result, hits)['claims'],
                         [{'source_id': 'starter', 'quote': 'Starter refund window is 7 days.'}])

    def test_composite_question_needs_two_sources(self):
        hits = [hit('refund', 'Refunds take 7 days.', 5),
                hit('support', 'Support response takes 24 hours.', 4)]
        result = self.provider.generate('Compare APAC Starter refund and support time limits.', hits, [])
        self.assertEqual(len(validate_output(result, hits)['claims']), 2)

    def test_unknown_named_entity_and_weak_score_abstain(self):
        hits = [hit('starter', 'Starter refund window is 7 days.', 5)]
        self.assertEqual(self.provider.generate('What is the Platinum plan refund window?', hits, [])['status'],
                         'insufficient_evidence')
        self.assertEqual(self.provider.generate('What is the platinum plan refund window?', hits, [])['status'],
                         'insufficient_evidence')
        hits[0]['score'] = -4
        self.assertEqual(self.provider.generate('What is the APAC Starter refund window?', hits, [])['status'],
                         'insufficient_evidence')

    def test_numeric_question_prefers_sentence_with_period(self):
        hits = [hit('starter', 'Staff may quote this approved period. The approved refund period is 18 days.', 5)]
        result = self.provider.generate('What refund period may APAC Starter staff quote?', hits, [])
        self.assertEqual(result['claims'][0]['quote'], 'The approved refund period is 18 days.')

    def test_interrogative_after_sentence_does_not_look_like_unknown_entity(self):
        hits = [hit('starter', 'Starter customers in APAC receive refunds within 7 days.', 5)]
        result = self.provider.generate('I paid for Starter in APAC. How long is the refund window?', hits, [])
        self.assertEqual(result['status'], 'answered')

    def test_identifier_can_use_two_sections_of_same_document(self):
        price = hit('price', 'AC-EN is the Enterprise plan at 299 USD per month.', 2, 'Enterprise')
        seats = hit('seats', 'Starter includes 5 seats. Enterprise includes 100 seats.', -8, 'Enterprise')
        price['document_id'] = seats['document_id'] = 'catalog'
        price['section'] = 'Product codes'
        seats['section'] = 'Limits'
        result = self.provider.generate('What price and seat limit apply to AC-EN?', [price, seats], [])
        self.assertEqual(len(result['claims']), 2)
        self.assertEqual(result['claims'][1]['quote'], 'Enterprise includes 100 seats.')

    def test_support_subject_filters_higher_scored_refund_policy(self):
        refund = hit('refund', 'Starter refunds take 7 days.', 7)
        support = hit('support', 'Starter support responds within 24 hours.', 2)
        refund['title'] = 'APAC Starter Refund Policy'
        support['title'] = 'APAC Starter Support Policy'
        result = self.provider.generate('Our APAC Starter service is down. How soon will support respond?',
                                        [refund, support], [])
        self.assertEqual(result['claims'][0]['source_id'], 'support')

    def test_draft_conflict_keeps_both_sources(self):
        approved = hit('approved', 'The approved refund period is 18 days.', 5)
        draft = hit('draft', 'An unapproved sales draft claims a 40 day refund period.', 4)
        approved['title'] = 'APAC Starter Refund Policy'
        draft['title'] = 'APAC Starter Sales Draft'
        result = self.provider.generate('Compare the APAC Starter refund period and sales draft.',
                                        [approved, draft], [])
        self.assertEqual({c['source_id'] for c in result['claims']}, {'approved', 'draft'})

    def test_access_reviews_retain_security_source(self):
        retention = hit('retention', 'Finance approves retention offers.', 4)
        security = hit('security', 'Access reviews occur every 90 days.', 4)
        retention['title'] = 'APAC Starter Retention Policy'
        security['title'] = 'APAC Starter Security Policy'
        selected = self.provider._subject_filter('Who approves retention offers and how often are access reviews held?',
                                                  [retention, security])
        self.assertEqual({h['source_id'] for h in selected}, {'retention', 'security'})


if __name__ == '__main__':
    unittest.main()

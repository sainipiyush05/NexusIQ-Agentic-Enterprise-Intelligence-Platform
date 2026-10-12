import unittest

from nexusiq.churnadvanced import VALUE_THRESHOLD, choose_candidate, outreach_decision


class ChurnAdvancedTests(unittest.TestCase):
    def test_selection_uses_validation_average_precision_then_brier(self):
        candidates = {'boosting': {'average_precision': .3, 'brier': .08},
                      'logistic': {'average_precision': .4, 'brier': .10}}
        self.assertEqual(choose_candidate(candidates), 'logistic')
        candidates['boosting']['average_precision'] = .4
        self.assertEqual(choose_candidate(candidates), 'boosting')

    def test_outreach_respects_capacity_break_even_and_stable_ties(self):
        scores = [.8, .8, .3, .1, .05]
        labels = [1, 0, 1, 0, 0]
        result = outreach_decision(scores, labels, capacity_fraction=.4, value_threshold=.2)
        self.assertEqual(result['selected_indices'], [0, 1])
        self.assertEqual(result['capacity'], 2)
        self.assertEqual(result['true_churn_contacted'], 1)
        self.assertEqual(result['hypothetical_net_value'], 19)
        self.assertEqual(VALUE_THRESHOLD, .12)

    def test_outreach_can_choose_no_one(self):
        result = outreach_decision([.02, .03], [1, 0])
        self.assertEqual(result['contacted'], 0)
        self.assertIsNone(result['precision_at_contact'])
        self.assertEqual(result['hypothetical_net_value'], 0)


if __name__ == '__main__':
    unittest.main()

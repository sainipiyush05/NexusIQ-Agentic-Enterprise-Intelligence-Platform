import unittest
from nexusiq.hybrid import reciprocal_rank_fusion

class FusionTests(unittest.TestCase):
    def test_ranks_ignore_incompatible_scores(self):
        rankings={'fts':[{'source_id':'a','score':999},{'source_id':'b','score':1}], 'dense':[{'source_id':'b','score':.01},{'source_id':'c','score':.001}]}
        hits=reciprocal_rank_fusion(rankings)
        self.assertEqual([h['source_id'] for h in hits],['b','a','c'])
        self.assertAlmostEqual(hits[0]['score'],1/62+1/61)
        self.assertEqual(hits[0]['branch_ranks'],{'fts':2,'dense':1})
    def test_duplicate_does_not_inflate_or_shift_ranks(self):
        hits=reciprocal_rank_fusion({'one':[{'source_id':'b'},{'source_id':'b'},{'source_id':'a'}]})
        self.assertAlmostEqual(hits[1]['score'],1/62)
        self.assertEqual(len(hits),2)
    def test_ties_and_empty_branch(self):
        self.assertEqual([h['source_id'] for h in reciprocal_rank_fusion({'x':[{'source_id':'z'}],'y':[{'source_id':'a'}]})],['a','z'])
        self.assertEqual(reciprocal_rank_fusion({'x':[]}),[])
    def test_invalid_constant(self):
        for value in [0,-1,True,1.5]:
            with self.assertRaises(ValueError): reciprocal_rank_fusion({},value)

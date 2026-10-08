import math
import os
import unittest
from nexusiq.retrieval import Chunk, SearchIndex
from nexusiq.rerank import RerankedIndex

class FakeReranker:
    def __init__(self): self.seen=[]
    def score(self,query,hits):
        self.seen=hits
        return [10 if h['source_id']=='b' else 1 for h in hits]

class RerankerTests(unittest.TestCase):
    def setUp(self):
        self.chunks=[Chunk(s,s,'Refund','Rules',text,s+'.md',tenant,('analyst',),region,'Growth') for s,text,tenant,region in [('a','refund refund','atlascloud','APAC'),('b','refund terms','atlascloud','APAC'),('private','refund confidential','other','APAC'),('emea','refund terms','atlascloud','EMEA')]]
        self.reranker=FakeReranker()
        self.index=RerankedIndex(SearchIndex(self.chunks),self.reranker)
    def test_reranking_uses_only_filtered_candidates_and_preserves_sources(self):
        hits=self.index.search('refund',1,filters={'region':'APAC'})
        self.assertEqual(hits[0]['source_id'],'b')
        self.assertEqual({h['source_id'] for h in self.reranker.seen},{'a','b'})
        self.assertIn('retrieval_score',hits[0])
        self.assertEqual(hits[0]['text'],'refund terms')
    def test_empty_and_invalid_scores(self):
        self.assertEqual(self.index.search('refund',role='guest'),[])
        for value in [[],[math.nan]*4]:
            self.reranker.score=lambda q,h,v=value:v
            with self.assertRaises(ValueError): self.index.search('refund')
    def test_bounds_and_deterministic_ties(self):
        for k in [True,0,21]:
            with self.assertRaises(ValueError):self.index.search('refund',k)
        self.reranker.score=lambda q,h:[1]*len(h)
        self.assertEqual([h['source_id'] for h in self.index.search('refund',filters={'region':'APAC'})],['a','b'])
    def test_variants_preserve_access_metadata_and_baseline(self):
        from nexusiq.experiments import variant_chunks
        from nexusiq.benchmark import load_benchmark_index
        self.assertEqual(variant_chunks(120,15),load_benchmark_index().chunks)
        baseline={(c.document_id,c.section):c for c in load_benchmark_index().chunks}
        for c in variant_chunks(24,6):
            original=baseline[(c.document_id,c.section)]
            self.assertEqual((c.tenant_id,c.roles,c.region,c.plan),(original.tenant_id,original.roles,original.region,original.plan))
            self.assertLessEqual(len(c.text.split()),24)

@unittest.skipUnless(os.environ.get('NEXUSIQ_RERANK_TESTS')=='1','Set NEXUSIQ_RERANK_TESTS=1 for real cross-encoder integration')
class RealRerankerTests(unittest.TestCase):
    def test_real_pair_scoring_and_overflow_rejection(self):
        from nexusiq.rerank import LocalReranker
        model=LocalReranker()
        hits=[{'title':'Refund policy','section':'Rules','text':'A refund is available within fourteen days of purchase.'},{'title':'Support','section':'Rules','text':'Critical support requests receive a response within one hour.'}]
        scores=model.score('How long do I have to request a refund?',hits)
        self.assertGreater(scores[0],scores[1])
        self.assertEqual(model.score('refund',[]),[])
        with self.assertRaises(ValueError):model.score('refund '*1000,hits)

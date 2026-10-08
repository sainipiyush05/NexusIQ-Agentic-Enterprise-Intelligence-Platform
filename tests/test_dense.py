import json
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from nexusiq.retrieval import Chunk
from nexusiq.dense import DenseIndex, fingerprint
from nexusiq.embeddings import normalize_vector

class ToyEmbedder:
    """Known vectors test mechanics only; never used in semantic experiments."""
    def __init__(self):
        self.metadata=dict(provider='test_fixture',dimension=2,revision='test-v1')
        self.calls=0
    def encode(self,texts):
        self.calls+=1
        return [[1,0] if 'refund' in text.lower() else [0,1] for text in texts]

def chunk(sid,text,tenant='atlascloud',role='analyst',region='APAC'):
    return Chunk(sid,sid,'Policy','Rules',text,sid+'.md',tenant,(role,),region,'Enterprise')

class DenseTests(unittest.TestCase):
    def setUp(self):
        self.embedder=ToyEmbedder()
        self.chunks=[chunk('refund','refund terms'),chunk('support','support response'),chunk('private','refund secret',tenant='private')]
        self.index=DenseIndex.build(self.chunks,self.embedder)

    def test_exact_cosine_ranking_and_access_filter(self):
        hits=self.index.search('refund',top_k=2)
        self.assertEqual(hits[0]['source_id'],'refund')
        self.assertEqual(hits[0]['score'],1)
        self.assertNotIn('private',[h['source_id'] for h in hits])
        self.assertEqual([],self.index.search('refund',role='guest'))
        self.assertEqual([],self.index.search('refund',filters={'region':'EMEA'}))

    def test_no_eligible_sources_do_not_embed_query(self):
        before=self.embedder.calls
        self.index.search('refund',tenant_id='missing')
        self.index.search('')
        self.assertEqual(before,self.embedder.calls)

    def test_persisted_roundtrip_without_reembedding_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'index.json'
            self.index.save(path)
            before=self.embedder.calls
            loaded=DenseIndex.load(path,self.chunks,self.embedder)
            self.assertEqual(before,self.embedder.calls)
            self.assertEqual(loaded.search('refund'),self.index.search('refund'))

    def test_artifact_tampering_and_stale_corpus_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'index.json'
            self.index.save(path)
            changed=[replace(self.chunks[0],text='new policy')]+self.chunks[1:]
            with self.assertRaisesRegex(ValueError,'stale'):
                DenseIndex.load(path,changed,self.embedder)
            content=json.loads(path.read_text())
            content['payload']['vectors'][0][0]=0.5
            path.write_text(json.dumps(content))
            with self.assertRaisesRegex(ValueError,'checksum'):
                DenseIndex.load(path,self.chunks,self.embedder)

    def test_model_change_requires_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'index.json'
            self.index.save(path)
            other=ToyEmbedder()
            other.metadata['revision']='test-v2'
            with self.assertRaisesRegex(ValueError,'model/config'):
                DenseIndex.load(path,self.chunks,other)

    def test_invalid_vectors_and_query_inputs_are_rejected(self):
        for vector in [[],[0,0],[float('nan'),1],[float('inf'),1]]:
            with self.assertRaises(ValueError):
                normalize_vector(vector)
        with self.assertRaisesRegex(ValueError,'dimensions'):
            DenseIndex(self.chunks,[[1,0,0]]*3,self.embedder)
        with self.assertRaisesRegex(ValueError,'count'):
            DenseIndex(self.chunks,[[1,0]],self.embedder)
        for top_k in [True,0,21,2.5]:
            with self.assertRaises(ValueError):
                self.index.search('refund',top_k)
        with self.assertRaises(ValueError):
            self.index.search('refund',filters={'tenant_id':'private'})

    def test_cosine_is_invariant_to_document_vector_scale(self):
        index=DenseIndex(self.chunks,[[50,0],[0,7],[1,0]],self.embedder)
        self.assertEqual(index.search('refund')[0]['score'],1)
        self.assertAlmostEqual(sum(x*x for x in normalize_vector([3,4])),1)

    def test_identity_changes_invalidate_corpus_fingerprint(self):
        self.assertNotEqual(fingerprint(self.chunks),fingerprint([replace(self.chunks[0],roles=('guest',))]+self.chunks[1:]))

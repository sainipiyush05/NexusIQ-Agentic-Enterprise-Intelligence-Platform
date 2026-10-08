"""Explicit real-model integration check; opt in after model installation."""
import os
import tempfile
import unittest
from pathlib import Path
from nexusiq.retrieval import Chunk
from nexusiq.dense import DenseIndex

@unittest.skipUnless(os.environ.get('NEXUSIQ_MODEL_TESTS') == '1', 'Set NEXUSIQ_MODEL_TESTS=1 for the downloaded local model integration test')
class LocalModelIntegrationTests(unittest.TestCase):
    def test_real_semantic_encoding_and_disk_roundtrip(self):
        from nexusiq.embeddings import LocalEmbedder
        embedder=LocalEmbedder()
        chunks=[Chunk('refund','refund','Billing Policy','Rules','Customers can receive a refund of their initial payment within thirty days.','refund.md','atlascloud',('analyst',),'APAC','Enterprise'),Chunk('security','security','Security Policy','Rules','Administrators must enable multi-factor authentication.','security.md','atlascloud',('analyst',),'APAC','Enterprise')]
        index=DenseIndex.build(chunks,embedder)
        hits=index.search('How long do I have to get my money back?')
        self.assertEqual(hits[0]['source_id'],'refund')
        self.assertEqual(len(index.vectors[0]),384)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'dense.json'
            index.save(path)
            loaded=DenseIndex.load(path,chunks,embedder)
            self.assertEqual(index.search('money back'),loaded.search('money back'))
        with self.assertRaisesRegex(ValueError,'token budget'):
            embedder.encode(['refund '*1000])

import os
import threading
import unittest
from nexusiq.localgeneration import LocalTransformersProvider,GenerationBudgetExceeded
from nexusiq.generation import GenerationUnavailable,InvalidGeneration,validate_output

class LocalGenerationGuardTests(unittest.TestCase):
    def test_busy_generator_rejects_before_inference(self):
        provider=LocalTransformersProvider.__new__(LocalTransformersProvider)
        provider.lock=threading.Lock();provider.lock.acquire()
        try:
            with self.assertRaises(GenerationUnavailable):provider.generate('query',[],[])
        finally:provider.lock.release()
    def test_readiness_rejects_training_mode(self):
        provider=LocalTransformersProvider.__new__(LocalTransformersProvider)
        class Model:training=True
        provider.model=Model();provider.tokenizer=None
        with self.assertRaises(GenerationUnavailable):provider.assert_ready()

@unittest.skipUnless(os.environ.get('NEXUSIQ_GENERATION_TESTS')=='1','Set NEXUSIQ_GENERATION_TESTS=1 for cached local causal model')
class RealGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.provider=LocalTransformersProvider()
    def test_cached_model_live_quote_generation(self):
        self.provider.assert_ready()
        hits=[dict(source_id='s1',title='Refund',section='Rules',text='Refunds are allowed within 7 calendar days.')]
        output=self.provider.generate('What is the refund deadline?',hits,hits)
        self.assertEqual(validate_output(output,hits)['status'],'answered')
        self.assertTrue(any('7' in c['quote'] for c in output['claims']))
    def test_token_overflow_rejected_without_truncation(self):
        with self.assertRaises(GenerationBudgetExceeded):self.provider.generate('refund '*6000,[],[])
        self.assertFalse(self.provider.lock.locked())

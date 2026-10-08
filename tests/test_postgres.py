import os
import unittest
from dataclasses import replace
from nexusiq.retrieval import Chunk
from nexusiq.dense import DenseIndex
from nexusiq.storageerrors import StorageUnavailable

class FixedEmbedder:
    metadata={'provider':'database-test','dimension':384,'revision':'fixture-v1'}
    def encode(self,texts):
        return [([1.0,0.0] if 'refund' in text.lower() else [0.0,1.0])+[0.0]*382 for text in texts]

@unittest.skipUnless(os.environ.get('NEXUSIQ_DB_TESTS')=='1','Set NEXUSIQ_DB_TESTS=1 for actual PostgreSQL integration tests')
class PostgresIntegrationTests(unittest.TestCase):
    def setUp(self):
        from nexusiq.postgres import import_index, PostgresIndex
        embedder=FixedEmbedder()
        self.chunks=[Chunk('allowed','doc1','Refund','Rules','refund terms','a.md','atlascloud',('analyst',),'APAC','Enterprise'),Chunk('other','doc2','Support','Rules','support terms','b.md','atlascloud',('analyst',),'EMEA','Growth'),Chunk('private','doc3','Refund','Rules','refund secrets','c.md','private',('admin',),'APAC','Enterprise')]
        self.reference=DenseIndex.build(self.chunks,embedder)
        import_index(self.reference,'test')
        self.index=PostgresIndex(self.reference,'test')

    def tearDown(self):
        from nexusiq.postgres import connect
        with connect() as conn:
            conn.execute("DELETE FROM nexusiq.datasets WHERE scope='test'")

    def test_exact_search_and_sql_filters(self):
        self.assertEqual(self.index.search('refund')[0]['source_id'],'allowed')
        self.assertEqual(self.index.search('refund',role='guest'),[])
        self.assertEqual(self.index.search('refund',tenant_id='missing'),[])
        hits=self.index.search('refund',filters={'region':'APAC','plan':'Enterprise'})
        self.assertEqual([r['source_id'] for r in hits],['allowed'])
        self.assertEqual(self.index.search('refund',filters={'region':"APAC' OR 1=1 --"}),[])
        self.assertEqual(self.index.search('refund',tenant_id="atlascloud' OR 1=1 --"),[])

    def test_reader_cannot_write_even_with_readonly_disabled(self):
        import psycopg
        from nexusiq.postgres import connect
        with connect(reader=True) as conn:
            conn.autocommit=True
            conn.execute('SET default_transaction_read_only=off')
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute("UPDATE nexusiq.chunks SET body='bad' WHERE scope='test'")

    def test_failed_import_rolls_back_entire_scope(self):
        import psycopg
        from nexusiq.postgres import import_index
        broken=DenseIndex([self.chunks[0],self.chunks[0]],[[1.0]+[0.0]*383]*2,FixedEmbedder())
        with self.assertRaises(psycopg.errors.UniqueViolation):
            import_index(broken,'test')
        self.index.assert_current()
        self.assertEqual(self.index.search('refund')[0]['text'],'refund terms')

    def test_changed_corpus_fails_closed(self):
        from nexusiq.postgres import import_index
        changed=DenseIndex.build([replace(self.chunks[0],text='new refund')]+self.chunks[1:],FixedEmbedder())
        import_index(changed,'test')
        with self.assertRaises(StorageUnavailable):
            self.index.search('refund')

    def test_business_foreign_keys_reject_orphan_orders(self):
        import psycopg
        from nexusiq.postgres import connect
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            with connect() as conn:
                conn.execute("INSERT INTO nexusiq.orders VALUES(%s,%s,%s,%s,%s,%s)",('atlascloud','orphan-test','missing-customer','AC-ST','2026-06-01',29))

    def test_migrations_are_repeatable(self):
        from nexusiq.postgres import migrate
        self.assertEqual(migrate()['applied'],[])

    def test_hybrid_branches_apply_access_filters(self):
        from nexusiq.hybrid import HybridIndex, FullTextIndex
        hybrid=HybridIndex(self.reference,'test')
        fts=FullTextIndex(self.reference,'test')
        self.assertEqual([h['source_id'] for h in fts.search('refund')],['allowed'])
        hits=hybrid.search('refund',filters={'region':'APAC'})
        self.assertEqual([h['source_id'] for h in hits],['allowed'])
        self.assertEqual(hits[0]['branch_ranks'],{'fts':1,'dense':1})
        self.assertEqual(hybrid.search('refund',role='guest'),[])
        self.assertEqual(hybrid.search('refund',filters={'region':"APAC' OR 1=1 --"}),[])

    def test_hybrid_falls_back_when_fts_has_no_match(self):
        from nexusiq.hybrid import HybridIndex, FullTextIndex
        hybrid=HybridIndex(self.reference,'test')
        self.assertEqual(FullTextIndex(self.reference,'test').search('unfindableword'),[])
        hits=hybrid.search('unfindableword')
        self.assertTrue(hits)
        self.assertTrue(all(set(h['branch_ranks'])=={'dense'} for h in hits))
        self.assertEqual(hybrid.search(''),[])
        for k in [True,0,21]:
            with self.assertRaises(ValueError): hybrid.search('refund',k)

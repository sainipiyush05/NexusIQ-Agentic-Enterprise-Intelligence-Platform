import csv
import json
import tempfile
import threading
import unittest
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from nexusiq.data import seed_data
from nexusiq.retrieval import SearchIndex, chunk_document
from nexusiq.evaluation import evaluate
from nexusiq.server import make_handler

class FoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.tmp.name)
        cls.manifest = seed_data(cls.data)
        cls.index = SearchIndex.load(cls.data)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_seed_reproducibility_and_foreign_keys(self):
        first = self.manifest['dataset_sha256']
        self.assertEqual(first, seed_data(self.data)['dataset_sha256'])
        with (self.data/'customers.csv').open() as f:
            ids = {r['customer_id'] for r in csv.DictReader(f)}
        for table in ['orders', 'tickets', 'subscriptions']:
            with (self.data/f'{table}.csv').open() as f:
                self.assertTrue(all(r['customer_id'] in ids for r in csv.DictReader(f)))

    def test_chunks_preserve_boundaries_and_identity(self):
        meta = self.manifest['documents'][0]
        text = '# Title\n## First\n'+' '.join(f'word{i}' for i in range(300))+'\n## Second\nSecond section.'
        chunks = chunk_document(meta, text, max_words=30, overlap=5)
        self.assertTrue(all(len(c.text.split())<=30 for c in chunks))
        self.assertEqual(chunks, chunk_document(meta,text,30,5))
        self.assertEqual(len(chunks),len({c.source_id for c in chunks}))
        self.assertEqual(chunks[-1].section,'Second')
        with self.assertRaises(ValueError):
            chunk_document(meta,text,30,30)

    def test_retrieval_acl_before_ranking(self):
        self.assertEqual([],self.index.search('refund',tenant_id='other'))
        self.assertEqual([],self.index.search('refund',role='guest'))
        denied = replace(self.index.chunks[0],tenant_id='secret',roles=('admin',))
        index = SearchIndex([denied]+self.index.chunks)
        self.assertNotIn('secret',{h['tenant_id'] for h in index.search('policy')})

    def test_policy_evidence_and_filtering(self):
        result = self.index.answer('What is the Enterprise refund window in APAC?',filters={'region':'APAC','plan':'Enterprise'})
        inferred = self.index.answer('What is the Enterprise refund window in APAC?')
        self.assertTrue(all(h['region']=='APAC' and h['plan']=='Enterprise' for h in inferred['citations']))
        self.assertFalse(result['abstained'])
        self.assertIn('30 calendar days',result['answer'])
        self.assertEqual(result['citations'][0]['document_id'],'apac-enterprise-refund-v1')
        self.assertTrue(all(h['region']=='APAC' and h['plan']=='Enterprise' for h in result['citations']))
        self.assertTrue(all(h['source_id'] in self.index.by_id for h in result['citations']))

    def test_empty_query_and_absent_evidence(self):
        self.assertEqual([],self.index.search(''))
        self.assertTrue(self.index.answer('What is the CEO home address?')['abstained'])
        self.assertTrue(self.index.answer('What is the spaceship refund window?')['abstained'])
        with self.assertRaises(ValueError):
            self.index.search('refund',top_k=0)

    def test_tampered_corpus_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            m = seed_data(path)
            (path/m['documents'][0]['path']).write_text('tampered')
            with self.assertRaises(ValueError):
                SearchIndex.load(path)

    def test_evaluation_smoke_thresholds(self):
        report = evaluate(self.data)
        self.assertEqual(report['cases'],24)
        self.assertGreaterEqual(report['recall_at_5'],0.9)
        self.assertGreaterEqual(report['expected_fact_rate'],0.9)
        self.assertEqual(report['abstention_accuracy'],1)

    def test_http_validates_input_and_resolves_citations(self):
        server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.index))
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base+'/v1/health/ready') as response:
                self.assertEqual(json.load(response)['status'],'ok')
            req = Request(base+'/v1/query',data=json.dumps({'query':'APAC Enterprise refund window'}).encode(),headers={'Content-Type':'application/json'})
            with urlopen(req) as response:
                answer=json.load(response)
            with urlopen(base+'/v1/sources/'+answer['citations'][0]['source_id']) as response:
                self.assertEqual(json.load(response)['document_id'],'apac-enterprise-refund-v1')
            search_req=Request(base+'/v1/search',data=json.dumps({'query':'refund'}).encode(),headers={'Content-Type':'application/json'})
            with urlopen(search_req) as response:
                search=json.load(response)
            self.assertTrue(search['candidate_only'])
            self.assertTrue(search['citations'])
            for payload in [{'query':'refund','top_k':True},{'query':''},{'query':'refund','role':'admin'},[]]:
                req=Request(base+'/v1/query',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
                with self.assertRaises(HTTPError) as error:
                    urlopen(req)
                self.assertEqual(error.exception.code,400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

class StorageFailureTests(unittest.TestCase):
    def test_http_storage_failures_are_controlled(self):
        from nexusiq.storageerrors import StorageUnavailable
        class UnavailableIndex:
            chunks=[]
            by_id={}
            def assert_current(self):
                raise StorageUnavailable('internal detail not for clients')
            def search(self,*args,**kwargs):
                raise StorageUnavailable('internal detail not for clients')
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(UnavailableIndex()))
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base+'/v1/health/live') as response:
                self.assertEqual(response.status,200)
            requests=[base+'/v1/health/ready',base+'/v1/sources/any',Request(base+'/v1/search',data=b'{"query":"refund"}',headers={'Content-Type':'application/json'})]
            for request in requests:
                with self.assertRaises(HTTPError) as error:
                    urlopen(request)
                self.assertEqual(error.exception.code,503)
                self.assertNotIn('internal detail',error.exception.read().decode())
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__=='__main__':
    unittest.main()

import json
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dataclasses import asdict
from nexusiq.generation import (ExtractiveProvider,GroundedAnswerService,InvalidGeneration,GenerationUnavailable,OllamaProvider,validate_output)
from nexusiq.retrieval import Chunk,SearchIndex

CONFIG=dict(max_context_characters=16000,max_output_bytes=65536,timeout_seconds=2,model='mock-test-only')
class FakeProvider:
    name='test'
    def __init__(self,result):self.result=result;self.seen=[]
    def generate(self,query,hits,context):self.seen=hits;return self.result

class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.chunk=Chunk('allowed','doc','Refund','Rules','Refunds are allowed within 14 days.','doc.md','atlascloud',('analyst',),'APAC','Growth')
        private=Chunk('private','secret','Refund','Rules','Refund secrets','secret.md','other',('admin',),'APAC','Growth')
        self.index=SearchIndex([self.chunk,private]);self.hits=[asdict(self.chunk)]
        self.good={'status':'answered','claims':[{'source_id':'allowed','quote':'within 14 days'}]}
    def test_exact_quote_and_schema_validation(self):
        self.assertEqual(validate_output(self.good,self.hits),self.good)
        for bad in [None,[],{},dict(status={},claims=[]),dict(status='answered',claims=[]),dict(status='insufficient_evidence',claims=self.good['claims']),dict(self.good,extra='invented')]:
            with self.assertRaises(InvalidGeneration):validate_output(bad,self.hits)
    def test_fabricated_sources_and_quotes_are_rejected(self):
        for claim in [{'source_id':'private','quote':'Refund secrets'},{'source_id':'allowed','quote':'within 90 days'},{'source_id':'allowed','quote':''},{'source_id':None,'quote':'Refunds'},{'source_id':'allowed','quote':'Refunds','text':'invented claim'}]:
            with self.assertRaises(InvalidGeneration):validate_output(dict(status='answered',claims=[claim]),self.hits)
        with self.assertRaises(InvalidGeneration):validate_output(dict(status='answered',claims=self.good['claims']*2),self.hits)
    def test_invalid_provider_output_fails_closed(self):
        p=FakeProvider(dict(status='answered',claims=[{'source_id':'allowed','quote':'90 days'}]))
        result=GroundedAnswerService(self.index,p,CONFIG).answer('refund')
        self.assertTrue(result['abstained']);self.assertEqual(result['citations'],[])
        self.assertEqual(result['reason'],'invalid_provider_output')
        self.assertNotIn('90 days',result['answer'])
    def test_provider_receives_authorized_sources_only(self):
        p=FakeProvider(self.good);result=GroundedAnswerService(self.index,p,CONFIG).answer('refund')
        self.assertEqual([h['source_id'] for h in p.seen],['allowed'])
        self.assertEqual(result['answer'],'[1] within 14 days')
        self.assertEqual(result['validation']['answer_sufficiency'],'not_verified')
    def test_no_evidence_and_input_bounds(self):
        p=FakeProvider(self.good);service=GroundedAnswerService(self.index,p,CONFIG)
        self.assertTrue(service.answer('unfindableword')['abstained']);self.assertEqual(p.seen,[])
        for query,k in [('',5),('refund',True),('refund',11),('x'*1001,5)]:
            with self.assertRaises(ValueError):service.answer(query,k)
    def test_offline_extracts_are_not_claimed_as_llm_answers(self):
        result=GroundedAnswerService(self.index,ExtractiveProvider(),CONFIG).answer('refund')
        self.assertEqual(result['mode'],'cited_extracts');self.assertTrue(result['candidate_only'])
        self.assertIn('no LLM',result['limitations'])
    def test_context_bound_does_not_truncate_quotes(self):
        from dataclasses import replace
        large=replace(self.chunk,text='refund '*1000)
        result=GroundedAnswerService(SearchIndex([large]),ExtractiveProvider(),dict(CONFIG,max_context_characters=1000)).answer('refund')
        self.assertTrue(result['abstained']);self.assertEqual(result['reason'],'no_evidence_in_context')
    def test_adapter_rejects_remote_endpoints_and_missing_model(self):
        for endpoint in ['https://example.com/api/generate','http://127.0.0.1:1/wrong','http://user@localhost/api/generate']:
            with self.assertRaises(ValueError):OllamaProvider(dict(CONFIG,endpoint=endpoint))
        with self.assertRaises(ValueError):OllamaProvider(dict(CONFIG,endpoint='http://localhost:11434/api/generate',model=None))
    def test_local_adapter_http_contract_with_simulated_provider(self):
        requests=[];good=self.good
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                body=json.dumps(dict(done=True,response=json.dumps(good))).encode()
                self.send_response(200);self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            provider=OllamaProvider(dict(CONFIG,endpoint=f'http://127.0.0.1:{server.server_port}/api/generate'))
            self.assertEqual(provider.generate('refund',self.hits,[]),good)
            self.assertFalse(requests[0]['stream']);self.assertEqual(requests[0]['format']['type'],'object')
            self.assertIn('untrusted',requests[0]['system'])
        finally:server.shutdown();server.server_close();thread.join()
    def test_answer_endpoint_and_safe_provider_errors(self):
        from nexusiq.server import make_handler
        class BrokenProvider:
            name='unavailable-test'
            def generate(self,*args):raise GenerationUnavailable('internal private failure')
            def assert_ready(self):raise GenerationUnavailable('internal readiness detail')
        service=GroundedAnswerService(self.index,BrokenProvider(),CONFIG)
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.index,service));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/v1/answer',json.dumps({'query':'refund'}).encode(),{'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as exc:urllib.request.urlopen(req)
            self.assertEqual(exc.exception.code,503)
            self.assertNotIn('private',exc.exception.read().decode())
            with self.assertRaises(urllib.error.HTTPError) as ready:
                urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/v1/health/ready')
            self.assertEqual(ready.exception.code,503)
            self.assertNotIn('detail',ready.exception.read().decode())
            self.assertEqual(urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/v1/health/live').status,200)
        finally:server.shutdown();server.server_close();thread.join()

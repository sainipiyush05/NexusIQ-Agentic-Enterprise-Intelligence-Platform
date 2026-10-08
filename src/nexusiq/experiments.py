"""Development-only chunk and reranker comparison; production indexes stay intact."""
import hashlib
import json
import time
from .config import DATA, ROOT
from .benchmark import FIXTURES, load_benchmark_index, run_benchmark
from .retrieval import chunk_document, SearchIndex
from .dense import DenseIndex, document_text, fingerprint
from .embeddings import LocalEmbedder
from .rerank import LocalReranker, RerankedIndex

VARIANTS = ((24, 6), (48, 12), (120, 15))


def variant_chunks(max_words, overlap):
    chunks = []
    documents = [(DATA, d) for d in json.loads((DATA/'manifest.json').read_text())['documents']]
    documents += [(FIXTURES, d) for d in json.loads((FIXTURES/'manifest.json').read_text())]
    for base, doc in documents:
        text = (base/doc['path']).read_text()
        if hashlib.sha256(text.encode()).hexdigest() != doc['sha256']:
            raise ValueError('Experiment source checksum mismatch')
        chunks.extend(chunk_document(doc, text, max_words, overlap))
    return chunks


def run_experiments():
    embedder, reranker = LocalEmbedder(), LocalReranker()
    original = load_benchmark_index()
    results = []
    for max_words, overlap in VARIANTS:
        print(f"Experiment: {max_words} words / {overlap} overlap", flush=True)
        chunks = variant_chunks(max_words, overlap)
        lengths = embedder.model.tokenizer([document_text(c) for c in chunks], truncation=False, return_length=True)['length']
        start = time.perf_counter()
        dense = DenseIndex.build(chunks, embedder)
        build_ms = (time.perf_counter()-start)*1000
        artifact = ROOT/'.data/experiments'/f'dense-{max_words}-{overlap}.json'
        dense.save(artifact)
        reports = {}
        for name, index in [('bm25', SearchIndex(chunks)), ('dense', dense), ('dense_reranked', RerankedIndex(dense, reranker))]:
            report = run_benchmark('dev', 5, index=index, baseline=name, validation_index=original,
                                   chunker_version=f'section-word-v1-{max_words}-{overlap}')
            contexts = []
            for case in report['cases']:
                texts = [document_text(index.by_id[h['source_id']]) for h in case['retrieved_sources']]
                contexts.append(sum(embedder.model.tokenizer(texts, truncation=False, return_length=True)['length']) if texts else 0)
            reports[name] = dict(report, context_tokens=dict(tokenizer=embedder.metadata['model_id'],
                mean=round(sum(contexts)/len(contexts),2), maximum=max(contexts), note='Sum of per-chunk embedding tokenizer lengths; excludes prompt/query and is not LLM billing.'))
        candidate_report = run_benchmark('dev', 20, index=dense, validation_index=original, chunker_version=f'section-word-v1-{max_words}-{overlap}')
        results.append(dict(candidate_evidence_recall_at_20=candidate_report['overall']['evidence_recall_at_k'], max_words=max_words, overlap=overlap, chunks=len(chunks), corpus_fingerprint=fingerprint(chunks),
                            embedding_tokens=dict(total=sum(lengths), maximum=max(lengths)), build_ms=round(build_ms,3),
                            artifact_bytes=artifact.stat().st_size, reports=reports))
    return dict(split='dev', top_k=5, candidate_k=20, embedding=embedder.metadata, reranker=reranker.metadata, variants=results,
                limitations=['No holdout scoring or production index changes.', 'Draft labels and shared wording patterns limit conclusions.',
                'Evidence-unit recall is document+section based; splitting may inflate it relative to complete quote coverage.',
                'Quotes crossing chunk boundaries count as absent in single-chunk fact coverage.',
                'Timing includes raw search plus guarded response search, on CPU; no LLM generation.'])

"""Small commands for building and comparing the semantic baseline."""
from .config import ROOT
from .retrieval import SearchIndex
from .benchmark import load_benchmark_index, run_benchmark
from .embeddings import LocalEmbedder
from .dense import DenseIndex


def get_dense_index(scope='demo', rebuild=False):
    if scope not in {'demo', 'benchmark'}:
        raise ValueError('scope must be demo or benchmark')
    chunks = (load_benchmark_index() if scope=='benchmark' else SearchIndex.load()).chunks
    embedder = LocalEmbedder()
    path = ROOT/'data/indexes'/f'{scope}-dense.json'
    if path.exists() and not rebuild:
        return DenseIndex.load(path,chunks,embedder)
    index = DenseIndex.build(chunks,embedder)
    index.save(path)
    return index


def compare_retrieval(split='dev', top_k=5):
    dense = get_dense_index('benchmark')
    lexical = run_benchmark(split,top_k)
    semantic = run_benchmark(split,top_k,index=dense,baseline='MiniLM exact cosine retrieval + unchanged extractive response guard')
    return dict(split=split,top_k=top_k,embedding=dense.embedder.metadata,lexical=lexical,dense=semantic,delta_evidence_recall_at_k=round(semantic['overall']['evidence_recall_at_k']-lexical['overall']['evidence_recall_at_k'],4), note='Same corpus, labels, cutoff and trusted identity. No gold filters. Retrieval improvements do not prove answer safety; the original subject-based response guard is unchanged.')

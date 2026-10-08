"""PostgreSQL full-text and exact vector retrieval, fused within one snapshot."""
import json
from .postgres import PostgresIndex, connect, db_guard
from .embeddings import normalize_vector


def reciprocal_rank_fusion(rankings, constant=60):
    if type(constant) is not int or constant <= 0:
        raise ValueError('RRF constant must be a positive integer')
    hits, scores, branches = {}, {}, {}
    for name, ranking in rankings.items():
        seen = set()
        for hit in ranking:
            source = hit['source_id']
            if source in seen:
                continue
            seen.add(source)
            rank = len(seen)
            hits.setdefault(source, hit)
            scores[source] = scores.get(source, 0) + 1 / (constant + rank)
            branches.setdefault(source, {})[name] = rank
    return [dict(hits[source], score=scores[source], branch_ranks=branches[source])
            for source in sorted(hits, key=lambda s: (-scores[s], s))]


class HybridIndex(PostgresIndex):
    retriever_name = 'hybrid'
    candidate_k = 20
    rrf_constant = 60
    fields = 'source_id,document_id,title,section,body AS text,path,tenant_id,roles,region,plan'
    access = 'scope=%s AND tenant_id=%s AND %s=ANY(roles) AND (%s::text IS NULL OR region=%s) AND (%s::text IS NULL OR plan=%s)'

    @db_guard
    def search(self, query, top_k=5, tenant_id='atlascloud', role='analyst', filters=None):
        from psycopg.rows import dict_row
        if type(top_k) is not int or not 1 <= top_k <= 20:
            raise ValueError('top_k must be an integer between 1 and 20')
        filters = filters or {}
        if set(filters) - {'region', 'plan'}:
            raise ValueError('Only region and plan filters are supported')
        if not query.strip():
            return []
        lexical_only = self.retriever_name == 'fts'
        vector = None if lexical_only else normalize_vector(self.embedder.encode([query])[0])
        if vector is not None and len(vector) != 384:
            raise ValueError('Query vector dimension mismatch')
        params = (self.scope, tenant_id, role, filters.get('region'), filters.get('region'), filters.get('plan'), filters.get('plan'))
        limit = top_k if lexical_only else self.candidate_k
        with connect(reader=True) as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            self.assert_current(conn)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(f"WITH q AS (SELECT websearch_to_tsquery('english', %s) AS query) SELECT {self.fields},ts_rank_cd(search_vector,q.query) AS score FROM nexusiq.chunks CROSS JOIN q WHERE {self.access} AND search_vector @@ q.query ORDER BY score DESC,source_id LIMIT %s", (query, *params, limit))
                lexical = cur.fetchall()
                if lexical_only:
                    return lexical
                encoded = json.dumps(vector)
                cur.execute(f'SELECT {self.fields},1-(embedding <=> %s::vector) AS score FROM nexusiq.chunks WHERE {self.access} ORDER BY embedding <=> %s::vector,source_id LIMIT %s', (encoded, *params, encoded, limit))
                dense = cur.fetchall()
        return reciprocal_rank_fusion({'fts': lexical, 'dense': dense}, self.rrf_constant)[:top_k]

    def answer(self, *args, **kwargs):
        from .retrieval import SearchIndex
        result = SearchIndex.answer(self, *args, **kwargs)
        result['mode'] = self.retriever_name + '_extract'
        result['limitations'] = 'Evidence extracts only; experimental response guard. Search scores do not establish answer sufficiency.'
        return result


class FullTextIndex(HybridIndex):
    retriever_name = 'fts'


def compare_hybrid(split='dev', top_k=5):
    from .semantic import get_dense_index
    from .benchmark import run_benchmark, load_benchmark_index
    reference = get_dense_index('benchmark')
    indexes = {'bm25': load_benchmark_index(), 'dense': PostgresIndex(reference, 'benchmark'),
               'fts': FullTextIndex(reference, 'benchmark'), 'hybrid': HybridIndex(reference, 'benchmark')}
    reports = {name: run_benchmark(split, top_k, index=index, baseline=name + ' raw retrieval + current extractive guard') for name, index in indexes.items()}
    return dict(split=split, candidate_k=20, rrf_constant=60, embedding=reference.embedder.metadata,
                reports=reports, note='Fixed equal-weight RRF; no holdout tuning. FTS is cover-density ranking, not BM25. Timings include raw search and a second guarded search.')

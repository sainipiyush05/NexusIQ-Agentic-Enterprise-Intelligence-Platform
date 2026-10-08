"""Compare real pgvector retrieval with the persisted in-process reference."""
from .semantic import get_dense_index
from .postgres import PostgresIndex, import_index, connect
from .benchmark import load_cases


def verify():
    reference=get_dense_index('benchmark')
    import_index(reference,'benchmark')
    database=PostgresIndex(reference,'benchmark')
    matched=0; differences=[]; max_error=0
    for case in load_cases('dev'):
        expected=reference.search(case['query'])
        actual=database.search(case['query'])
        ids=[r['source_id'] for r in expected]
        dbids=[r['source_id'] for r in actual]
        if ids==dbids: matched+=1
        else: differences.append(dict(id=case['id'],reference=ids,database=dbids))
        scores={r['source_id']:r['score'] for r in actual}
        for row in expected:
            if row['source_id'] in scores:
                max_error=max(max_error,abs(row['score']-scores[row['source_id']]))
    with connect(reader=True) as conn:
        version=conn.execute("SELECT current_setting('server_version'),(SELECT extversion FROM pg_extension WHERE extname='vector')").fetchone()
        counts={table:conn.execute(f'SELECT count(*) FROM nexusiq.{table}').fetchone()[0] for table in ['customers','subscriptions','orders','tickets']}
    report=dict(postgresql=version[0],pgvector=version[1],development_cases=105,top_5_order_matches=matched,max_score_absolute_error=round(max_error,8),differences=differences,business_counts=counts,heldout_scored=False)
    if matched!=105 or max_error>0.00001:
        raise ValueError(f'Database/reference comparison failed: {report}')
    return report

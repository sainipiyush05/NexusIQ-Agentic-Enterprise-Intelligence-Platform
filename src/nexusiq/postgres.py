"""Transactional persistence and exact pgvector retrieval."""
import csv
import hashlib
import json
from functools import wraps
from .config import ROOT, DATA
from .dense import fingerprint
from .embeddings import normalize_vector
from .localdb import db_config
from .storageerrors import StorageUnavailable
from .retrieval import SearchIndex


def db_guard(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        import psycopg
        try:
            return function(*args,**kwargs)
        except psycopg.Error as exc:
            raise StorageUnavailable('Persistent retrieval storage is unavailable') from exc
    return wrapped


@db_guard
def connect(reader=False):
    import psycopg
    return psycopg.connect(**db_config()['reader' if reader else 'owner'])


def migrate():
    with connect() as conn:
        conn.execute('CREATE SCHEMA IF NOT EXISTS nexusiq')
        conn.execute('CREATE TABLE IF NOT EXISTS nexusiq.schema_migrations(version text PRIMARY KEY,sha256 text NOT NULL)')
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('nexusiq:migrations'))")
        applied=[]
        for path in sorted((ROOT/'db/migrations').glob('*.sql')):
            body=path.read_text(); checksum=hashlib.sha256(body.encode()).hexdigest()
            row=conn.execute('SELECT sha256 FROM nexusiq.schema_migrations WHERE version=%s',(path.name,)).fetchone()
            if row:
                if row[0]!=checksum:
                    raise ValueError('Applied migration has changed; create a new migration instead')
                continue
            conn.execute(body)
            conn.execute('INSERT INTO nexusiq.schema_migrations VALUES(%s,%s)',(path.name,checksum))
            applied.append(path.name)
    return dict(applied=applied)


def import_index(index,scope='demo'):
    from psycopg.types.json import Jsonb
    if scope not in {'demo','benchmark','test'} or index.embedder.metadata['dimension']!=384:
        raise ValueError('Supported scope and 384-dimensional model required')
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('nexusiq:'+scope,))
        conn.execute('INSERT INTO nexusiq.datasets(scope,corpus_fingerprint,embedding_metadata) VALUES(%s,%s,%s) ON CONFLICT(scope) DO UPDATE SET corpus_fingerprint=excluded.corpus_fingerprint,embedding_metadata=excluded.embedding_metadata,imported_at=now()', (scope,fingerprint(index.chunks),Jsonb(index.embedder.metadata)))
        conn.execute('DELETE FROM nexusiq.chunks WHERE scope=%s',(scope,))
        rows=[(scope,c.source_id,c.document_id,c.title,c.section,c.text,c.path,c.tenant_id,list(c.roles),c.region,c.plan,json.dumps(v)) for c,v in zip(index.chunks,index.vectors)]
        with conn.cursor() as cur:
            cur.executemany('INSERT INTO nexusiq.chunks (scope,source_id,document_id,title,section,body,path,tenant_id,roles,region,plan,embedding) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)',rows)
    return dict(scope=scope,chunks=len(rows),corpus_fingerprint=fingerprint(index.chunks))


def seed_business(directory=DATA):
    from psycopg import sql
    tables={
      'customers': ['tenant_id','customer_id','region','plan','join_date'],
      'subscriptions':['tenant_id','customer_id','product_id','status','monthly_price','snapshot_date'],
      'orders':['tenant_id','order_id','customer_id','product_id','order_date','revenue'],
      'tickets':['tenant_id','ticket_id','customer_id','opened_at','category','resolution_hours'],
    }
    manifest=json.loads((directory/'manifest.json').read_text())
    records={}
    for table in tables:
        path=directory/f'{table}.csv'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['tables'][path.name]:
            raise ValueError('Business data checksum mismatch')
        with path.open() as f:
            records[table]=list(csv.DictReader(f))
    counts={}
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('nexusiq:business'))")
        for table in reversed(list(tables)):
            conn.execute(sql.SQL('DELETE FROM nexusiq.{} WHERE tenant_id=%s').format(sql.Identifier(table)),('atlascloud',))
        for table,columns in tables.items():
            statement=sql.SQL('INSERT INTO nexusiq.{} ({}) VALUES ({})').format(sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,columns)),sql.SQL(',').join(sql.Placeholder() for _ in columns))
            with conn.cursor() as cur:
                cur.executemany(statement,[tuple(row.get(col,'atlascloud') for col in columns) for row in records[table]])
            counts[table]=len(records[table])
    return counts


class PostgresIndex(SearchIndex):
    retriever_name="postgres"
    def __init__(self,reference,scope='demo'):
        super().__init__(reference.chunks)
        self.embedder=reference.embedder
        self.scope=scope
        self.expected_fingerprint=fingerprint(reference.chunks)
        self.assert_current()

    @db_guard
    def assert_current(self,conn=None):
        if conn is None:
            with connect(reader=True) as c:
                return self.assert_current(c)
        row=conn.execute('SELECT corpus_fingerprint,embedding_metadata FROM nexusiq.datasets WHERE scope=%s',(self.scope,)).fetchone()
        if not row or row[0]!=self.expected_fingerprint or row[1]!=self.embedder.metadata:
            raise StorageUnavailable('Database index is absent/stale or uses a different embedding model; run db-import')

    @db_guard
    def search(self,query,top_k=5,tenant_id='atlascloud',role='analyst',filters=None):
        from psycopg.rows import dict_row
        if type(top_k) is not int or not 1<=top_k<=20:
            raise ValueError('top_k must be an integer between 1 and 20')
        filters=filters or {}
        if set(filters)-{'region','plan'}:
            raise ValueError('Only region and plan filters are supported')
        if not query.strip(): return []
        vector=normalize_vector(self.embedder.encode([query])[0])
        if len(vector)!=384: raise ValueError('Query vector dimension mismatch')
        with connect(reader=True) as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            self.assert_current(conn)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT source_id,document_id,title,section,body AS text,path,tenant_id,roles,region,plan,1-(embedding <=> %s::vector) AS score FROM nexusiq.chunks WHERE scope=%s AND tenant_id=%s AND %s=ANY(roles) AND (%s::text IS NULL OR region=%s) AND (%s::text IS NULL OR plan=%s) ORDER BY embedding <=> %s::vector,source_id LIMIT %s",(json.dumps(vector),self.scope,tenant_id,role,filters.get('region'),filters.get('region'),filters.get('plan'),filters.get('plan'),json.dumps(vector),top_k))
                hits=cur.fetchall()
        for hit in hits: hit['score']=round(hit['score'],6)
        return hits

    def answer(self,*args,**kwargs):
        answer=super().answer(*args,**kwargs)
        answer['mode']='postgres_dense_extract'
        answer['limitations']='Exact pgvector retrieval; evidence extracts only, experimental response guard.'
        return answer

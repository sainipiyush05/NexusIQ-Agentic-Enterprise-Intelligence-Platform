"""Download and import the public Olist dataset without mixing it with AtlasCloud."""

import csv
import hashlib
import json
from pathlib import Path

from .config import DATA

HANDLE = "olistbr/brazilian-ecommerce"
RAW = DATA / "olist" / "raw"
MANIFEST = DATA / "olist" / "manifest.json"

# Import order respects foreign keys. The source spelling `lenght` is retained.
FILES = (
    ("olist_customers_dataset.csv", "customers", ("customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state")),
    ("olist_sellers_dataset.csv", "sellers", ("seller_id", "seller_zip_code_prefix", "seller_city", "seller_state")),
    ("olist_products_dataset.csv", "products", ("product_id", "product_category_name", "product_name_lenght", "product_description_lenght", "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm")),
    ("olist_orders_dataset.csv", "orders", ("order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date")),
    ("olist_order_items_dataset.csv", "order_items", ("order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value")),
    ("olist_order_payments_dataset.csv", "order_payments", ("order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value")),
    ("olist_order_reviews_dataset.csv", "order_reviews", ("review_id", "order_id", "review_score", "review_comment_title", "review_comment_message", "review_creation_date", "review_answer_timestamp")),
    ("olist_geolocation_dataset.csv", "geolocation", ("geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state")),
    ("product_category_name_translation.csv", "product_category_translation", ("product_category_name", "product_category_name_english")),
)


def download(source_dir=RAW, handle=HANDLE, force=False):
    """Fetch with KaggleHub; source_dir remains outside tracked source files."""
    try:
        import kagglehub
    except ImportError as exc:
        raise RuntimeError("Install the dataset extra: uv sync --extra dataset --locked") from exc
    source_dir = Path(source_dir)
    source_dir.parent.mkdir(parents=True, exist_ok=True)
    return Path(kagglehub.dataset_download(handle, output_dir=str(source_dir), force_download=force))


def inspect_source(source_dir=RAW, handle=HANDLE):
    """Check the exact CSV headers and record row counts and SHA-256 hashes."""
    source_dir = Path(source_dir)
    result = {"dataset_handle": handle, "files": {}, "row_counts": {}}
    for filename, table, columns in FILES:
        path = source_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing Olist file: {path}")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            header = tuple(next(reader, ()))
            if header != columns:
                raise ValueError(f"Unexpected columns in {filename}: {header}")
            count = 0
            for row in reader:
                if len(row) != len(columns):
                    raise ValueError(f"Malformed CSV row in {filename} at record {count + 1}")
                count += 1
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        result["files"][filename] = {"sha256": digest.hexdigest(), "rows": count}
        result["row_counts"][table] = count
    return result


def import_source(source_dir=RAW, handle=HANDLE, connector=None):
    """Replace the isolated Olist schema in one transaction after validating files."""
    from psycopg import sql
    from psycopg.types.json import Jsonb
    from .postgres import connect

    source_dir = Path(source_dir)
    manifest = inspect_source(source_dir, handle)
    connector = connector or connect
    with connector() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('nexusiq:olist-import'))")
        for _, table, _ in reversed(FILES):
            conn.execute(sql.SQL("DELETE FROM olist.{}").format(sql.Identifier(table)))
        for filename, table, columns in FILES:
            statement = sql.SQL("COPY olist.{} ({}) FROM STDIN WITH (FORMAT csv, HEADER true)").format(
                sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, columns))
            )
            with conn.cursor() as cur, cur.copy(statement) as copy, (source_dir / filename).open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    copy.write(block)
        conn.execute("INSERT INTO olist.imports(dataset_handle, files, row_counts) VALUES (%s,%s,%s)",
                     (handle, Jsonb(manifest["files"]), Jsonb(manifest["row_counts"])))
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def status(connector=None):
    """Report actual database counts, including useful review text units."""
    from psycopg import sql
    from .postgres import connect

    connector = connector or connect
    counts = {}
    with connector(reader=True) as conn:
        for _, table, _ in FILES:
            counts[table] = conn.execute(
                sql.SQL("SELECT count(*) FROM olist.{}").format(sql.Identifier(table))
            ).fetchone()[0]
        text_count = conn.execute("SELECT count(*) FROM olist.order_reviews WHERE nullif(btrim(coalesce(review_comment_title,'') || ' ' || coalesce(review_comment_message,'')), '') IS NOT NULL").fetchone()[0]
        latest = conn.execute("SELECT imported_at, dataset_handle FROM olist.imports ORDER BY imported_at DESC LIMIT 1").fetchone()
    business_rows = sum(counts[name] for name in counts if name not in {"geolocation", "product_category_translation"})
    return {"tables": counts, "business_rows": business_rows,
            "all_rows": sum(counts.values()), "review_text_units": text_count,
            "latest_import": {"at": latest[0].isoformat(), "handle": latest[1]} if latest else None}


def search_reviews(query, limit=5, connector=None):
    """Rank source-attributed Olist review text using PostgreSQL full-text search."""
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        raise ValueError("Query must contain 1-500 characters")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("Limit must be an integer from 1 to 20")
    from psycopg.rows import dict_row
    from .postgres import connect
    connector = connector or connect
    with connector(reader=True) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SELECT set_config('statement_timeout', '5s', true)")
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT source_row, review_id, order_id, review_score,
                       review_comment_title AS title, review_comment_message AS text,
                       ts_rank(to_tsvector('simple', coalesce(review_comment_title,'') || ' ' || coalesce(review_comment_message,'')), websearch_to_tsquery('simple', %s)) AS score
                FROM olist.order_reviews
                WHERE to_tsvector('simple', coalesce(review_comment_title,'') || ' ' || coalesce(review_comment_message,'')) @@ websearch_to_tsquery('simple', %s)
                ORDER BY score DESC, source_row LIMIT %s
            """, (query, query, limit))
            return [dict(row) for row in cur.fetchall()]

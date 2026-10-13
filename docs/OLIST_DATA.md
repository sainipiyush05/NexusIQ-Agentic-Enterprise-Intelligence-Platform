# Olist public dataset import

NexusIQ downloads the [Olist Brazilian E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) through [KaggleHub](https://github.com/Kaggle/kagglehub). The raw files are ignored under `data/generated/olist/raw/`. This dataset describes the Olist marketplace in Brazil during 2016–2018; it is separate from NexusIQ's fictional AtlasCloud SaaS tenant and synthetic policy corpus.

## Run

From the repository root, after setting up the local PostgreSQL database:

```sh
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra database --extra dataset --locked
make db-use-local
make db-migrate
make olist-download
make olist-import
make olist-status
PYTHONPATH=src .venv/bin/python -m nexusiq olist-search-reviews --query 'produto' --limit 5
```

To pin a version, run `olist-download --handle olistbr/brazilian-ecommerce/versions/N` and `olist-import --handle olistbr/brazilian-ecommerce/versions/N` through the Python CLI. The default handle follows the latest Kaggle version. The manifest records the handle and each file's SHA-256, row count, and expected columns. For a pre-downloaded copy, use `olist-import --source-dir /path/to/csvs`. Imported rows live in the PostgreSQL `olist` schema. No data is written into `nexusiq.customers`, `nexusiq.orders`, or the AtlasCloud chunk index.

## Imported tables

| Olist table | Rows in verified download | Source file |
| --- | ---: | --- |
| `olist.customers` | 99,441 | `olist_customers_dataset.csv` |
| `olist.sellers` | 3,095 | `olist_sellers_dataset.csv` |
| `olist.products` | 32,951 | `olist_products_dataset.csv` |
| `olist.orders` | 99,441 | `olist_orders_dataset.csv` |
| `olist.order_items` | 112,650 | `olist_order_items_dataset.csv` |
| `olist.order_payments` | 103,886 | `olist_order_payments_dataset.csv` |
| `olist.order_reviews` | 99,224 | `olist_order_reviews_dataset.csv` |
| `olist.geolocation` | 1,000,163 | `olist_geolocation_dataset.csv` |
| `olist.product_category_translation` | 71 | `product_category_name_translation.csv` |

The seven business tables total **550,688 rows**. All nine tables total **1,550,922 rows**, though the geolocation CSV contains repeated ZIP-code observations and should not be described as 1 million distinct customers or orders. The source review table has **42,697** records with nonempty title or message text. Search returns source row, review ID, order ID, rating, title, text, and full-text score. It uses the PostgreSQL `simple` text configuration because reviews are primarily Portuguese. The `olist.imports` table records import history and file hashes. Re-import validates the files, deletes only `olist` rows, and copies all CSVs in one transaction; a failed copy rolls back.

The existing read-only SQL tool intentionally allowlists only the AtlasCloud tables, and the existing pgvector/RAG benchmark covers only AtlasCloud policies. Olist is queryable through PostgreSQL and the dedicated review-search CLI, but it has **not** been added to that benchmark, embedding index, API, or LangGraph workflow. Review texts are user feedback, not policy documents. A meaningful RAG expansion needs a separately labeled evaluation set and explicit provenance/citation behavior.

"""Benchmark and evaluation suite for the large-scale Olist public marketplace dataset.

Measures full-text retrieval accuracy, latency percentiles over 42,697 text reviews,
sentiment alignment, and analytical SQL performance over 550,688 business rows.
"""
import json
import statistics
import time
from pathlib import Path

from .config import REPORTS
from .olist import search_reviews, status
from .postgres import connect

QUERIES = [
    # Positive sentiment queries (expected rating: 4-5 stars)
    ("recomendo", "pos"),
    ("otimo", "pos"),
    ("excelente", "pos"),
    ("muito bom", "pos"),
    ("satisfeito", "pos"),
    ("perfeito", "pos"),
    ("maravilhoso", "pos"),
    ("adorei", "pos"),
    ("entrega rapida", "pos"),
    ("chegou antes do prazo", "pos"),
    ("super recomendo", "pos"),
    ("produto de qualidade", "pos"),

    # Negative sentiment queries (expected rating: 1-2 stars)
    ("pessimo", "neg"),
    ("atraso", "neg"),
    ("defeito", "neg"),
    ("nao recebi", "neg"),
    ("veio quebrado", "neg"),
    ("cancelar", "neg"),
    ("errado", "neg"),
    ("horrivel", "neg"),
    ("demorou muito", "neg"),
    ("falta de respeito", "neg"),
    ("nao recomendo", "neg"),
    ("propaganda enganosa", "neg"),

    # Category / Product queries
    ("produto original", "neutral"),
    ("embalagem", "neutral"),
    ("qualidade", "neutral"),
    ("foto", "neutral"),
    ("material", "neutral"),
    ("tamanho", "neutral"),
    ("marca", "neutral"),
    ("cor", "neutral"),

    # Fulfillment & Seller queries
    ("atendimento", "neutral"),
    ("vendedor", "neutral"),
    ("contato", "neutral"),
    ("resposta", "neutral"),
    ("correios", "neutral"),
    ("rastreio", "neutral"),
    ("suporte", "neutral"),
    ("reembolso", "neutral"),
]

SQL_BENCHMARKS = [
    (
        "customer_state_distribution",
        "Geographic Customer Aggregation",
        "SELECT customer_state, count(*) AS customers FROM olist.customers GROUP BY customer_state ORDER BY customers DESC",
        99441,
    ),
    (
        "order_status_aggregation",
        "Order Fulfillment Status Breakdown",
        "SELECT order_status, count(*) AS orders FROM olist.orders GROUP BY order_status",
        99441,
    ),
    (
        "items_price_freight_metrics",
        "Item Price and Freight Summary",
        "SELECT count(*), round(avg(price)::numeric, 2) AS avg_price, round(avg(freight_value)::numeric, 2) AS avg_freight FROM olist.order_items",
        112650,
    ),
    (
        "payments_method_revenue",
        "Payment Types and Gross Volume",
        "SELECT payment_type, count(*) AS tx_count, round(sum(payment_value)::numeric, 2) AS total_val FROM olist.order_payments GROUP BY payment_type",
        103886,
    ),
    (
        "review_score_distribution",
        "Customer Rating Distribution",
        "SELECT review_score, count(*) AS reviews FROM olist.order_reviews GROUP BY review_score ORDER BY review_score DESC",
        99224,
    ),
    (
        "seller_item_volume",
        "Top Seller Fulfillment Volume",
        "SELECT seller_id, count(*) AS items_sold, round(sum(price)::numeric, 2) AS total_sales FROM olist.order_items GROUP BY seller_id ORDER BY items_sold DESC LIMIT 10",
        112650,
    ),
    (
        "order_item_cross_join",
        "Cross-Table Orders and Items Revenue Join",
        "SELECT o.order_status, count(i.order_item_id) AS items_count, round(sum(i.price)::numeric, 2) AS revenue FROM olist.orders o JOIN olist.order_items i ON o.order_id = i.order_id GROUP BY o.order_status",
        212091,
    ),
    (
        "order_review_fk_integrity",
        "Order-to-Review Foreign Key Referential Check",
        "SELECT count(*) FROM olist.order_reviews r JOIN olist.orders o ON r.order_id = o.order_id",
        99224,
    ),
]


def run_benchmark():
    """Execute complete retrieval, SQL, and scale evaluations over the Olist schema."""
    db_status = status()
    total_business_rows = db_status["business_rows"]
    all_rows = db_status["all_rows"]
    review_units = db_status["review_text_units"]

    # 1. Full-Text Search Retrieval Benchmark
    query_results = []
    latencies = []
    sentiment_total = 0
    sentiment_correct = 0
    total_hits = 0

    for query, polarity in QUERIES:
        start = time.perf_counter()
        hits = search_reviews(query, limit=5)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        latencies.append(duration_ms)
        total_hits += len(hits)

        query_sentiment_correct = 0
        query_sentiment_total = 0
        if polarity in ("pos", "neg"):
            for hit in hits:
                score = hit["review_score"]
                sentiment_total += 1
                query_sentiment_total += 1
                if polarity == "pos" and score >= 4:
                    sentiment_correct += 1
                    query_sentiment_correct += 1
                elif polarity == "neg" and score <= 2:
                    sentiment_correct += 1
                    query_sentiment_correct += 1

        query_results.append({
            "query": query,
            "polarity": polarity,
            "hits": len(hits),
            "latency_ms": duration_ms,
            "avg_rank_score": round(sum(h["score"] for h in hits) / len(hits), 4) if hits else 0.0,
            "sentiment_alignment": round(query_sentiment_correct / query_sentiment_total, 4) if query_sentiment_total else None,
        })

    latencies_sorted = sorted(latencies)
    hit_rate = sum(1 for r in query_results if r["hits"] > 0) / len(query_results)
    sentiment_accuracy = (sentiment_correct / sentiment_total) if sentiment_total > 0 else 0.0

    retrieval_metrics = {
        "total_queries": len(QUERIES),
        "hit_rate": round(hit_rate, 4),
        "total_hits_retrieved": total_hits,
        "sentiment_evaluated_reviews": sentiment_total,
        "sentiment_aligned_reviews": sentiment_correct,
        "sentiment_accuracy": round(sentiment_accuracy, 4),
        "mean_latency_ms": round(statistics.mean(latencies), 2),
        "median_latency_ms": round(statistics.median(latencies), 2),
        "p90_latency_ms": round(latencies_sorted[int(len(latencies_sorted) * 0.90)], 2),
        "p95_latency_ms": round(latencies_sorted[int(len(latencies_sorted) * 0.95)], 2),
        "p99_latency_ms": round(latencies_sorted[-1], 2),
    }

    # 2. SQL Analytics Benchmark over large tables
    sql_results = []
    sql_latencies = []
    with connect(reader=True) as conn:
        for q_id, desc, sql, rows_scanned in SQL_BENCHMARKS:
            start = time.perf_counter()
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            sql_latencies.append(duration_ms)
            sql_results.append({
                "id": q_id,
                "description": desc,
                "rows_scanned": rows_scanned,
                "rows_returned": len(rows),
                "latency_ms": duration_ms,
            })

    sql_metrics = {
        "queries_evaluated": len(SQL_BENCHMARKS),
        "total_rows_scanned_in_benchmark": sum(b[3] for b in SQL_BENCHMARKS),
        "mean_sql_latency_ms": round(statistics.mean(sql_latencies), 2),
        "median_sql_latency_ms": round(statistics.median(sql_latencies), 2),
        "p95_sql_latency_ms": round(sorted(sql_latencies)[int(len(sql_latencies) * 0.95)], 2),
        "max_sql_latency_ms": round(max(sql_latencies), 2),
    }

    # 3. Compile report payload
    report = {
        "dataset_name": "Olist Brazilian E-Commerce",
        "tables": db_status["tables"],
        "scale": {
            "business_rows": total_business_rows,
            "all_rows": all_rows,
            "review_text_units": review_units,
        },
        "retrieval_benchmark": retrieval_metrics,
        "sql_analytics_benchmark": sql_metrics,
        "query_details": query_results,
        "sql_details": sql_results,
    }

    # Write JSON and Markdown reports
    REPORTS.mkdir(exist_ok=True)
    json_path = REPORTS / "olist_benchmark.json"
    json_path.write_text(json.dumps(report, indent=2) + "\n")

    md_content = f"""# Olist Large-Scale Dataset Benchmark Report

Measured performance across **{total_business_rows:,} business rows** and **{review_units:,} text review units** in PostgreSQL.

## 1. Scale Overview
- **Customers**: {db_status['tables'].get('customers', 0):,}
- **Orders**: {db_status['tables'].get('orders', 0):,}
- **Order Items**: {db_status['tables'].get('order_items', 0):,}
- **Order Payments**: {db_status['tables'].get('order_payments', 0):,}
- **Order Reviews**: {db_status['tables'].get('order_reviews', 0):,} ({review_units:,} with non-empty text)
- **Products**: {db_status['tables'].get('products', 0):,}
- **Sellers**: {db_status['tables'].get('sellers', 0):,}
- **Total Business Rows**: **{total_business_rows:,}**
- **All Database Rows**: **{all_rows:,}**

## 2. Full-Text Search Retrieval ({len(QUERIES)} Test Queries)
- **Hit Rate**: **{retrieval_metrics['hit_rate'] * 100:.1f}%**
- **Sentiment Alignment Accuracy**: **{retrieval_metrics['sentiment_accuracy'] * 100:.1f}%** ({retrieval_metrics['sentiment_aligned_reviews']}/{retrieval_metrics['sentiment_evaluated_reviews']} reviews)
- **Mean Retrieval Latency**: **{retrieval_metrics['mean_latency_ms']} ms**
- **Median Retrieval Latency (p50)**: **{retrieval_metrics['median_latency_ms']} ms**
- **95th Percentile Latency (p95)**: **{retrieval_metrics['p95_latency_ms']} ms**
- **99th Percentile Latency (p99)**: **{retrieval_metrics['p99_latency_ms']} ms**

## 3. SQL Analytics Latency ({len(SQL_BENCHMARKS)} Queries over 550k+ Rows)
- **Total Rows Scanned in Suite**: **{sql_metrics['total_rows_scanned_in_benchmark']:,}**
- **Mean SQL Execution Time**: **{sql_metrics['mean_sql_latency_ms']} ms**
- **Median Execution Time (p50)**: **{sql_metrics['median_sql_latency_ms']} ms**
- **95th Percentile Latency (p95)**: **{sql_metrics['p95_sql_latency_ms']} ms**
- **Maximum Execution Time**: **{sql_metrics['max_sql_latency_ms']} ms**
"""
    md_path = REPORTS / "olist_benchmark.md"
    md_path.write_text(md_content)

    return report

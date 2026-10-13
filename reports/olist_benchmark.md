# Olist Large-Scale Dataset Benchmark Report

Measured performance across **550,688 business rows** and **42,697 text review units** in PostgreSQL.

## 1. Scale Overview
- **Customers**: 99,441
- **Orders**: 99,441
- **Order Items**: 112,650
- **Order Payments**: 103,886
- **Order Reviews**: 99,224 (42,697 with non-empty text)
- **Products**: 32,951
- **Sellers**: 3,095
- **Total Business Rows**: **550,688**
- **All Database Rows**: **1,550,922**

## 2. Full-Text Search Retrieval (40 Test Queries)
- **Hit Rate**: **100.0%**
- **Sentiment Alignment Accuracy**: **93.3%** (112/120 reviews)
- **Mean Retrieval Latency**: **7.19 ms**
- **Median Retrieval Latency (p50)**: **6.46 ms**
- **95th Percentile Latency (p95)**: **18.22 ms**
- **99th Percentile Latency (p99)**: **20.33 ms**

## 3. SQL Analytics Latency (8 Queries over 550k+ Rows)
- **Total Rows Scanned in Suite**: **938,607**
- **Mean SQL Execution Time**: **16.37 ms**
- **Median Execution Time (p50)**: **15.49 ms**
- **95th Percentile Latency (p95)**: **28.41 ms**
- **Maximum Execution Time**: **28.41 ms**

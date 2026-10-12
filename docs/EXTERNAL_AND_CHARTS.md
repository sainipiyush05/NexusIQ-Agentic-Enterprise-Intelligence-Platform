# 06C: external rates and validated charts

The `ExchangeRateTool` reads one currency pair from Frankfurter's public v2 single-pair endpoint. It supports USD, EUR, GBP, and INR, with an optional historical date. The URL is constructed from this fixed allowlist, HTTPS host, and optional ISO date; user input cannot supply an arbitrary URL. Requests have a three-second timeout, an 8 KiB body cap, no redirects, and at most two attempts. Only network errors and HTTP 429/5xx responses are retried; invalid requests or data fail immediately. The adapter checks JSON content type, date, pair, and finite positive rate before returning a typed value, source URL, latency, and attempt count. No customer or document data is sent to the provider.

The workflow recognizes a narrow exchange-rate question containing exactly two supported currencies. Its `fx` node shares the existing three-tool-call budget and returns an insufficient-evidence result if the provider fails. The reported date is the provider's observation date; historical requests may resolve to an earlier published observation. Rates are public reference data, not transaction prices or a business forecasting signal.

```sh
make fx-smoke
PYTHONPATH=src .venv/bin/python -m nexusiq workflow-query --question 'What is the USD to EUR exchange rate on 2026-06-30 and how many customers are in APAC?'
```

`chart-customers` executes one fixed aggregate through the 06A tenant-scoped read-only SQL tool. The chart renderer checks the table, tenant, policy metadata, non-truncation, region names, unique rows, integer counts, and query fingerprint shape before producing an accessible SVG. It does not render arbitrary SQL rows or user-supplied HTML.

```sh
make chart-customers
```

This writes `reports/customer_regions_dev.svg`. On the seeded local database, the chart has 70 AMER, 61 APAC, and 69 EMEA customers (200 total). `reports/external_chart_dev.md` records the local live smoke. Unit tests use injected transport and SQL results, so the regression suite does not depend on the public API or running database. The chart is a descriptive view of synthetic data, not a performance or business metric.

Provider contract: [Frankfurter API v2 documentation](https://frankfurter.dev/). The public service can change or be unavailable; the workflow fails closed rather than substituting a guessed rate.

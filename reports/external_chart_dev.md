# 06C local verification — 2026-10-13

The live `fx-rate` command requested USD/EUR for 2026-06-30 from Frankfurter v2. The provider returned 0.87656 EUR per USD for 2026-06-30 in one attempt (683.34 ms in this run). The mixed workflow request then returned the same rate and the SQL result of 61 APAC customers in two tool calls.

`chart-customers` queried the seeded local PostgreSQL database through the read-only tool and wrote `reports/customer_regions_dev.svg`: AMER 70, APAC 61, EMEA 69, total 200. The query result was not truncated. Unit tests cover schema validation, retry policy, invalid payloads, fixed URL construction, chart data checks, mixed workflow routing, and provider-outage abstention. The full suite passed 110 tests (12 optional checks skipped in the installed-dependency run). The eight original workflow scenarios still passed 8/8.

This is one live network smoke test and synthetic local data. The rate is a historical reference observation, not a transaction quote. Neither the smoke test nor the chart establishes broader answer accuracy or production availability.

# Domain: AtlasCloud SaaS

AtlasCloud is a fictional collaboration software company. All records and policies are synthetic.

- Tenant: `atlascloud`; regions: APAC, EMEA, AMER.
- Plans: Starter, Growth, Enterprise; products: AC-ST, AC-GR, AC-EN.
- Customers: C0001-C0200. Orders, subscriptions and tickets reference these IDs.
- Policy corpus: refund, support, retention and security policies for each region/plan combination.
- Data snapshot: 2026-07-01; historical events end before that timestamp.
- A future churn task will predict cancellation during July-September using features available before July. This milestone does not generate labels or train a model.

## Tables

`customers(customer_id, tenant_id, region, plan, join_date)`

`subscriptions(customer_id, product_id, status, monthly_price, snapshot_date)`

`orders(order_id, customer_id, product_id, order_date, revenue)`

`tickets(ticket_id, customer_id, opened_at, category, resolution_hours)`

Document manifest fields include `document_id`, `title`, `tenant_id`, `roles`, `region`, `plan`, `effective_date`, `version`, `path` and `sha256`.

## Retrieval behavior

Every chunk retains document identity, section, source path, tenant and access roles. Filtering runs before ranking. The current local server chooses a fixed atlascloud analyst context; the browser cannot select another role. This demonstrates filter logic, not an authentication system.

## Reproducibility

Seed 42 is the default. Generated records and documents are disposable artifacts under `data/generated/`. The manifest hash excludes wall-clock time, so regenerating with the same seed produces identical output. Do not use synthetic demo metrics as business claims.

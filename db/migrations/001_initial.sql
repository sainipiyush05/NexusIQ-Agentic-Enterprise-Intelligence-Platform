CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS nexusiq;
CREATE TABLE nexusiq.datasets (
 scope text PRIMARY KEY CHECK (scope IN ('demo','benchmark','test')),
 corpus_fingerprint text NOT NULL,
 embedding_metadata jsonb NOT NULL,
 imported_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE nexusiq.chunks (
 scope text REFERENCES nexusiq.datasets(scope) ON DELETE CASCADE,
 source_id text NOT NULL, document_id text NOT NULL, title text NOT NULL,
 section text NOT NULL, body text NOT NULL, path text NOT NULL,
 tenant_id text NOT NULL, roles text[] NOT NULL, region text NOT NULL, plan text NOT NULL,
 embedding vector(384) NOT NULL,
 PRIMARY KEY (scope,source_id)
);
CREATE INDEX chunks_access ON nexusiq.chunks(scope,tenant_id,region,plan);
CREATE TABLE nexusiq.customers (
 tenant_id text NOT NULL, customer_id text NOT NULL, region text NOT NULL,
 plan text NOT NULL, join_date date NOT NULL, PRIMARY KEY(tenant_id,customer_id)
);
CREATE TABLE nexusiq.subscriptions (
 tenant_id text NOT NULL, customer_id text NOT NULL, product_id text NOT NULL,
 status text NOT NULL, monthly_price numeric(12,2) NOT NULL CHECK(monthly_price>=0),
 snapshot_date date NOT NULL, PRIMARY KEY(tenant_id,customer_id),
 FOREIGN KEY(tenant_id,customer_id) REFERENCES nexusiq.customers(tenant_id,customer_id)
);
CREATE TABLE nexusiq.orders (
 tenant_id text NOT NULL, order_id text NOT NULL, customer_id text NOT NULL,
 product_id text NOT NULL, order_date date NOT NULL,
 revenue numeric(12,2) NOT NULL CHECK(revenue>=0), PRIMARY KEY(tenant_id,order_id),
 FOREIGN KEY(tenant_id,customer_id) REFERENCES nexusiq.customers(tenant_id,customer_id)
);
CREATE TABLE nexusiq.tickets (
 tenant_id text NOT NULL, ticket_id text NOT NULL, customer_id text NOT NULL,
 opened_at date NOT NULL, category text NOT NULL, resolution_hours integer NOT NULL CHECK(resolution_hours>=0),
 PRIMARY KEY(tenant_id,ticket_id),
 FOREIGN KEY(tenant_id,customer_id) REFERENCES nexusiq.customers(tenant_id,customer_id)
);
CREATE ROLE nexusiq_project_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
GRANT USAGE ON SCHEMA nexusiq TO nexusiq_project_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA nexusiq TO nexusiq_project_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA nexusiq GRANT SELECT ON TABLES TO nexusiq_project_reader;
ALTER ROLE nexusiq_project_reader SET default_transaction_read_only=on;
ALTER ROLE nexusiq_project_reader SET statement_timeout='5s';
GRANT CONNECT ON DATABASE nexusiq_project TO nexusiq_project_reader;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

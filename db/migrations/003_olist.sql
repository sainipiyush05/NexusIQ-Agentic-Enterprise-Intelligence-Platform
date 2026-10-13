-- Public Olist marketplace data is isolated from the fictional AtlasCloud tenant.
CREATE SCHEMA IF NOT EXISTS olist;

CREATE TABLE olist.customers (
  customer_id text PRIMARY KEY, customer_unique_id text NOT NULL,
  customer_zip_code_prefix text, customer_city text, customer_state text
);
CREATE TABLE olist.sellers (
  seller_id text PRIMARY KEY, seller_zip_code_prefix text,
  seller_city text, seller_state text
);
CREATE TABLE olist.products (
  product_id text PRIMARY KEY, product_category_name text,
  product_name_lenght integer, product_description_lenght integer,
  product_photos_qty integer, product_weight_g numeric,
  product_length_cm numeric, product_height_cm numeric, product_width_cm numeric
);
CREATE TABLE olist.orders (
  order_id text PRIMARY KEY, customer_id text NOT NULL REFERENCES olist.customers(customer_id),
  order_status text, order_purchase_timestamp timestamp,
  order_approved_at timestamp, order_delivered_carrier_date timestamp,
  order_delivered_customer_date timestamp, order_estimated_delivery_date timestamp
);
CREATE TABLE olist.order_items (
  order_id text NOT NULL REFERENCES olist.orders(order_id), order_item_id integer NOT NULL,
  product_id text REFERENCES olist.products(product_id), seller_id text REFERENCES olist.sellers(seller_id),
  shipping_limit_date timestamp, price numeric(12,2), freight_value numeric(12,2),
  PRIMARY KEY(order_id, order_item_id)
);
CREATE TABLE olist.order_payments (
  order_id text NOT NULL REFERENCES olist.orders(order_id), payment_sequential integer NOT NULL,
  payment_type text, payment_installments integer, payment_value numeric(12,2),
  PRIMARY KEY(order_id, payment_sequential)
);
CREATE TABLE olist.order_reviews (
  source_row bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  review_id text, order_id text NOT NULL REFERENCES olist.orders(order_id),
  review_score integer, review_comment_title text, review_comment_message text,
  review_creation_date timestamp, review_answer_timestamp timestamp
);
CREATE INDEX olist_review_text_idx ON olist.order_reviews
  USING gin (to_tsvector('simple', coalesce(review_comment_title,'') || ' ' || coalesce(review_comment_message,'')));
CREATE INDEX olist_order_customer_idx ON olist.orders(customer_id);
CREATE INDEX olist_item_product_idx ON olist.order_items(product_id);
CREATE TABLE olist.geolocation (
  geolocation_zip_code_prefix text, geolocation_lat numeric,
  geolocation_lng numeric, geolocation_city text, geolocation_state text
);
CREATE INDEX olist_geo_zip_idx ON olist.geolocation(geolocation_zip_code_prefix);
CREATE TABLE olist.product_category_translation (
  product_category_name text PRIMARY KEY, product_category_name_english text
);
CREATE TABLE olist.imports (
  imported_at timestamptz NOT NULL DEFAULT now(),
  dataset_handle text NOT NULL, files jsonb NOT NULL, row_counts jsonb NOT NULL
);

GRANT USAGE ON SCHEMA olist TO nexusiq_project_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA olist TO nexusiq_project_reader;

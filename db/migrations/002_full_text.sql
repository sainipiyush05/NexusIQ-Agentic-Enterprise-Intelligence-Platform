ALTER TABLE nexusiq.chunks ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
  to_tsvector('english', title || ' ' || section || ' ' || body)
) STORED;
CREATE INDEX chunks_full_text ON nexusiq.chunks USING gin(search_vector);

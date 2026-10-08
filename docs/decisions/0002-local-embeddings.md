# Decision 0002: a pinned local semantic baseline

Use `sentence-transformers/all-MiniLM-L6-v2` as the first measurable local embedding candidate, not as a presumed best model. Pin its Hugging Face commit in `config/embeddings.json`, run on CPU, normalize document and query vectors, and rank by exact cosine similarity. A later experiment should compare at least two embedding models.

The provider adapter batches encoding, checks tokenizer lengths and rejects silent truncation. Documents are embedded as title, section and body. The persisted artifact fingerprints full chunks including access metadata, records model/package versions, validates vector count and dimensions, and checks its content hash. Query vectors are computed with the same pinned provider.

Keep demo and benchmark indexes separate. Only the benchmark includes archived/conflicting/training fixtures. Apply trusted tenant, role and explicit filters before ranking. Do not add a similarity threshold and claim it detects missing evidence: thresholds need calibration against development cases.

Exact search is appropriate for the current small corpus. PostgreSQL/pgvector persistence and ANN indexing remain separate parts. Save numerical data as JSON, not pickle. Atomic replacement protects against interrupted saves; content hashes detect accidental changes, not malicious tampering by a trusted writer.

The current extractive response's subject guard stays unchanged during the retrieval comparison. Its false abstentions and unsupported answers remain open issues for grounded-generation work. Dense retrieval alone does not fix response correctness.

Official references: https://sbert.net/docs/sentence_transformer/usage/usage.html and https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 .

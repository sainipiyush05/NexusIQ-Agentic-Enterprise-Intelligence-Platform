# Decision 0001: local foundation before production services

Start with a dependency-free Python prototype so data, source provenance and evaluation can be verified immediately. The local HTTP adapter is deliberately temporary; migrate it to FastAPI in part 07A. BM25 provides a lexical comparator for the dense and hybrid retrieval experiments; it is not a replacement for semantic embeddings.

Use synthetic SaaS data with shared customer, product, plan and region identifiers. Keep ML snapshots separate from future outcomes. Do not add paid infrastructure until retrieval and tool behavior are measurable.

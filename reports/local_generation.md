# NexusIQ 04A.2 — local model runtime verified

Implemented a local Transformers provider using pinned Qwen2.5-0.5B-Instruct. The model runs on CPU from cached safetensors with remote code disabled; there are no paid API calls or external inference requests. The optional Ollama adapter remains available but was not installed.

## Runtime controls

- Actual chat-template token count checked before inference; oversized inputs are rejected without truncation.
- Input plus output budgets checked against model context capacity.
- Greedy decoding, maximum 384 output tokens, one generation at a time; busy requests return 503.
- Cooperative 45-second generation deadline checked between decoding steps; it is not a hard process-level wall-clock limit.
- Complete EOS-terminated JSON required; no automatic repair of malformed model output.
- Exact quote/source-ID validation before rendering; invalid output returns no claims.
- Provider readiness checked alongside database readiness.
- Model loading is cache-only; explicit download command required for a missing cache.

All 55 tests passed with real PostgreSQL, embeddings, reranking and local generation enabled. Fixed an import-order-dependent cross-encoder configuration-cache bug by consistently passing the project cache folder. The real causal-model test generated a valid exact quote and rejected an oversized prompt.

## Six preselected development probes

These are smoke probes, not a full generation benchmark. They use the benchmark-only corpus and five dense candidates. No held-out cases were scored. Invalid output is recorded separately from model abstention.

| Case | Category | Result | Labeled quote coverage | Time seconds |
| --- | --- | --- | --- | --- |
| g001 | direct_fact | answered | 1.0 | 22.84 |
| g002 | paraphrase | rejected by validator | 0.0 | 14.81 |
| g145 | exact_identifier | answered | 0.5 | 14.18 |
| g154 | multi_source | rejected by validator | 0.0 | 13.36 |
| g158 | unanswerable | answered | n/a | 21.00 |
| g162 | unanswerable | answered | n/a | 17.30 |

Observed failures: the paraphrase and multi-source outputs were rejected. The product answer gave prices for multiple products but omitted the requested seat limit. Both unsupported questions received irrelevant quotes instead of deliberate abstention. The direct-fact response included the correct quote plus unnecessary quotes for other plans/versions. Exact provenance checks cannot establish relevance, policy freshness, or answer sufficiency.

Decision: keep the default offline/retrieval modes. Expose the small model only in an explicitly experimental preview; it is unsuitable as the final answerer. A stronger model and full development evaluation are needed before promotion. The preview renders only exact validated quotations, not unrestricted generated prose.

Token preflight: all 105 development prompts fit the 4096-token input budget; range 556-749, mean 650.04. This measurement includes the actual schema, system prompt, chat template, question and five retrieved sources.

HTTP verification: readiness returned 200 with database and model loaded. A live APAC Growth request produced invalid model output; the API correctly rejected it and returned no claims. This is a guard check, not successful semantic abstention. The browser also completed a live APAC Starter request in about 43.5 seconds, returning three exact policy quotes (including other plans); all three displayed source endpoints resolved. The preview labels relevance as unverified.

Model: `Qwen/Qwen2.5-0.5B-Instruct` at `7ae557604adf67be50417f59c2c2f167def9a775`. Runtime and version details are in `reports/generation_probes_dev.json`.

Commands: `make cache-generation-model`, `make generation-probes`, `make serve-local-llm`. Experimental preview: http://127.0.0.1:8004/. Select **Experimental LLM-selected quotes**. Existing previews remain available.

Next small part: 04A.3 — broaden development evaluation, report failure reasons and question-specific evidence precision, then compare a stronger model or stricter evidence-selection approach. Conflicts, adversarial document behavior and complete abstention evaluation remain pending. Draft labels still need human review.

Parent 04A remains in progress. 04B semantic verification of paraphrased claims remains planned.

Implementation references: [Qwen model card](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct), [Transformers generation documentation](https://huggingface.co/docs/transformers/en/main_classes/text_generation).

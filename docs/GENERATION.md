# NexusIQ 04A.1 — structured cited-answer foundation

Implemented `/v1/answer` alongside existing search/query endpoints. The browser offers evidence search or cited extracts. Every displayed claim is an exact quote tied to a retrieved source ID. Server-side validation rejects extra fields, inconsistent statuses, empty/oversized quotes, duplicate claims, unknown source IDs and invented quotes. Invalid provider output returns no claims; unavailable providers return a safe 503.

The renderer prints only validated quotes, never model-authored explanatory prose. This prevents fabricated prose from being rendered through this contract. It does not establish that a quote is relevant, sufficient, current, or resistant to adversarial selection. A genuine quoted statement can still be unsuitable as an answer.

The working provider is `extractive`: it emits retrieved candidate text and is explicitly labeled as offline extracts, with `candidate_only=true` and sufficiency unverified. It has no semantic abstention detector; when dense search returns candidates for an unsupported question, this path can still display them. This is not LLM answer generation.

Added an optional loopback-only Ollama adapter using a JSON schema, zero-temperature generation, bounded response bytes, a timeout, and separate system instructions / serialized untrusted evidence. Redirects and inherited HTTP proxies are disabled. It has no tools or write actions. This adapter was tested against a simulated HTTP provider only. There is no local Ollama runtime/model configured. A local Transformers provider was subsequently implemented and tested; see `reports/local_generation.md` for its observed quality failures. Context is bounded in characters, not measured in generation tokens; model-specific context and truncation behavior need verification with the chosen runtime.

Validation: all 51 tests passed with real embedding, reranker and PostgreSQL integrations enabled. Ten new tests cover provenance/schema errors, private-source rejection, context/input bounds, offline labeling, local endpoint restrictions, simulated HTTP schema requests and safe API errors. The live PostgreSQL-backed offline `/v1/answer` produced five cited extracts for an APAC Growth refund query; all five exact quotes were checked against their source endpoints. Browser selection, displayed result and source links were verified.

The preview is http://127.0.0.1:8003/. Select **Cited extracts**. It may show other plans or related policy candidates; the output remains clearly marked as sufficiency unverified.

## Running

- `make serve-answers`: PostgreSQL retrieval with offline cited extracts on port 8003.
- Optional local LLM: configure `model` and the loopback `/api/generate` endpoint in `config/generation.json`, then run `.venv/bin/python -m nexusiq serve --retriever postgres --generation ollama --port 8003` with `PYTHONPATH=src`. Requires a running local Ollama server and an already-installed model. The project does not install or pull a model automatically.

## Remaining small parts

1. 04A.2: complete using pinned local Qwen; token limits and readiness verified, model remains experimental.
2. 04A.3: development evaluation for sufficiency, abstention, conflicts and adversarial content, recording model/version and latency. Holdout remains unscored.
3. 04B: semantic citation verification for paraphrased claims, with precision/recall measurement before permitting free-form answers.

The parent 04A milestone remains **in progress**. No generated-answer benchmark or injection-resistance claim is made. Existing draft labels still need human review.

API behavior follows the [Ollama structured-output documentation](https://docs.ollama.com/capabilities/structured-outputs) and [generate endpoint documentation](https://docs.ollama.com/api/generate).

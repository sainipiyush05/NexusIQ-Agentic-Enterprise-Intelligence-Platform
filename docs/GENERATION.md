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
3. 04B: evaluate an offline NLI verifier for atomic paraphrased claims against exact, authorized source quotes. This is a diagnostic check, not proof or permission to enable free-form answers.

The 04A.3 fixed development sample and scoring definitions are recorded in `reports/generation_evaluation_dev.md`. Run `make generation-eval` for the same 13 cases; `--all-dev` evaluates all 105 development cases. The holdout is not accessible through this command.

The full development run is now recorded in `reports/generation_full_dev.md` and `reports/generation_full_dev.json`. Run `make generation-eval-full` to reproduce it. The current local model fails evidence-selection and abstention checks, so it remains an experimental preview. Milestone 04A.4 compares a stricter local selector below.

Milestone 04A.4 adds an optional `ranked_extracts` provider. It selects exact cited sentences using the cached cross-encoder plus explicit scope and sufficiency rules; it is a candidate extractor, not an LLM. Its development comparison, failure cases and limitations are in `reports/generation_ranked_comparison_dev.md`. Run `make generation-ranked-full`, `make generation-ranked-challenges`, or `make serve-ranked` for the localhost preview. The default provider remains `extractive`.

Milestone 04B adds `CitationVerifier` in `src/nexusiq/citationverify.py`. Supply one atomic claim, a source ID, an exact quote, and a mapping of sources already authorized for that request. It first rejects unknown sources and quotes absent from their source, then runs the pinned local NLI model with the quote as premise and claim as hypothesis. Its verdict is `supported`, `unsupported`, or `uncertain`; a long pair or low-confidence signal remains uncertain. It never silently truncates evidence. The model is [cross-encoder/nli-MiniLM2-L6-H768](https://huggingface.co/cross-encoder/nli-MiniLM2-L6-H768), pinned in `config/citation_verification.json`; the model card documents its three label positions. Run `make cache-citation-model` once, then `make citation-eval` offline. The small authored development cases live in `evals/citations/dev.jsonl`, with a case-level report in `reports/citation_verification_dev.json`. Provenance and NLI are separate checks. NLI scores are diagnostic and do not establish source reliability, whole-answer sufficiency, numerical precision, or protection against misleading quoted text. The live answer endpoint still returns only cited extracts and does not claim semantic verification.

The parent 04A milestone remains **in progress**. No generated-answer benchmark or injection-resistance claim is made. Existing draft labels still need human review.

API behavior follows the [Ollama structured-output documentation](https://docs.ollama.com/capabilities/structured-outputs) and [generate endpoint documentation](https://docs.ollama.com/api/generate).

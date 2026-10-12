# 06B: bounded local analyst workflow

The workflow accepts one question under the fixed `atlascloud` analyst identity. Its planner recognizes a small set of document-policy questions, reviewed count/revenue SQL templates, churn questions containing exactly one `Cdddd` customer ID, and exchange-rate questions with two supported currencies. It can split up to three subquestions joined by `and`; unrecognized or write/action requests stop before any tool runs. LangGraph records explicit plan, cursor, steps, results, trace, answer, citations, and reason state. The graph caps tool calls at three and also has a recursion limit.

The document route uses the existing authorized dense retrieval and ranked cited-sentence selector. SQL uses only fixed templates and the 06A read-only tool, which enforces tenant predicates, a reader role, statement timeout and result cap. Churn scoring loads the checksum-checked 05B model artifact and July synthetic snapshot; only the local analyst can request it. The 06C FX route uses a fixed-host public adapter described in `docs/EXTERNAL_AND_CHARTS.md`. Tool errors and missing evidence produce partial or insufficient-evidence responses. Each result includes route status, per-tool duration and overall latency for later evaluation and tracing.

Prepare local data and the dedicated database as in `docs/DATABASE.md`, seed churn data and create the 05B model artifact as in `docs/CHURN.md`, and cache the embedding/reranker models as in `docs/GENERATION.md`. Install locked extras:

```sh
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra embeddings --extra database --extra ml --extra workflow --locked
make workflow-smoke
make workflow-eval
PYTHONPATH=src .venv/bin/python -m nexusiq workflow-query --question 'What is the APAC Enterprise refund window and how many Enterprise customers are in APAC?'
```

The eight author-created cases live in `evals/workflow/dev.jsonl`. `reports/workflow_dev.json` records route, status, content, reason, budget checks and per-case latency. These checks verify control flow and selected facts only; they do not measure semantic answer quality. The document selector returns exact candidate extracts, and the churn score is a synthetic experimental estimate with weak calibration. No free-form SQL generation, cross-tool reasoning, independent holdout, authenticated API, or production readiness is claimed. Next: 06C typed external API adapter and charts from validated results.

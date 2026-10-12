.PHONY: seed test eval serve
seed:
	PYTHONPATH=src python3 -m nexusiq seed

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

eval:
	PYTHONPATH=src python3 -m nexusiq evaluate

serve:
	PYTHONPATH=src python3 -m nexusiq serve

validate-evals:
	PYTHONPATH=src python3 -m nexusiq validate-evals

benchmark:
	PYTHONPATH=src python3 -m nexusiq benchmark --split dev

build-dense:
	PYTHONPATH=src .venv/bin/python -m nexusiq build-dense

compare-retrieval:
	PYTHONPATH=src .venv/bin/python -m nexusiq compare-retrieval

serve-dense:
	PYTHONPATH=src .venv/bin/python -m nexusiq serve --retriever dense

db-start:
	PYTHONPATH=src .venv/bin/python -m nexusiq db-start

db-migrate:
	PYTHONPATH=src .venv/bin/python -m nexusiq db-migrate

db-seed:
	PYTHONPATH=src .venv/bin/python -m nexusiq db-seed

db-import:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq db-import

db-verify:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq db-verify

db-stop:
	PYTHONPATH=src .venv/bin/python -m nexusiq db-stop

serve-postgres:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq serve --retriever postgres

db-use-local:
	PYTHONPATH=src .venv/bin/python -m nexusiq db-use-local

compare-hybrid:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq compare-hybrid

serve-hybrid:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq serve --retriever hybrid

retrieval-experiments:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq retrieval-experiments

serve-reranked:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq serve --retriever reranked --port 8002

serve-answers:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq serve --retriever postgres --generation extractive --port 8003

cache-generation-model:
	HF_HOME=$$PWD/.cache/huggingface HF_HUB_DISABLE_XET=1 PYTHONPATH=src .venv/bin/python -m nexusiq cache-generation-model

cache-citation-model:
	HF_HOME=$$PWD/.cache/huggingface HF_HUB_DISABLE_XET=1 PYTHONPATH=src .venv/bin/python -m nexusiq cache-citation-model

citation-eval:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq citation-eval

churn-seed:
	PYTHONPATH=src python3 -m nexusiq churn-seed

churn-snapshots:
	PYTHONPATH=src python3 -m nexusiq churn-snapshots

churn-eval:
	PYTHONPATH=src .venv/bin/python -m nexusiq churn-eval

churn-advanced:
	PYTHONPATH=src .venv/bin/python -m nexusiq churn-advanced

sql-smoke:
	PYTHONPATH=src .venv/bin/python -m nexusiq sql-query --sql 'SELECT region, COUNT(*) AS customers FROM customers GROUP BY region ORDER BY customers DESC' --max-rows 10

workflow-smoke:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq workflow-query --question 'What is the APAC Enterprise refund window?'

workflow-eval:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq workflow-eval

fx-smoke:
	PYTHONPATH=src .venv/bin/python -m nexusiq fx-rate --base USD --quote EUR --date 2026-06-30

chart-customers:
	PYTHONPATH=src .venv/bin/python -m nexusiq chart-customers

generation-probes:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq generation-probes

generation-eval:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq generation-eval

generation-eval-full:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq generation-eval --all-dev

generation-ranked-full:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq generation-eval --all-dev --provider ranked_extracts

generation-challenges:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq generation-challenges

generation-ranked-challenges:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq generation-challenges --provider ranked_extracts

serve-local-llm:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq serve --retriever postgres --generation local_transformers --port 8004

serve-ranked:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq serve --retriever dense --generation ranked_extracts --port 8005

serve-api:
	PYTHONPATH=src .venv/bin/python -m nexusiq serve --api --port 8000

serve-api-ranked:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq serve --api --retriever dense --generation ranked_extracts --port 8000

issue-token:
	PYTHONPATH=src .venv/bin/python -m nexusiq issue-token --user-id demo-analyst --tenant-id atlascloud --role analyst

test-e2e:
	PYTHONPATH=src .venv/bin/python scripts/test_e2e.py

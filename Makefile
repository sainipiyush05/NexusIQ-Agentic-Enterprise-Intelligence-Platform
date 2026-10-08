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

generation-probes:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq generation-probes

serve-local-llm:
	HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONPATH=src .venv/bin/python -m nexusiq serve --retriever postgres --generation local_transformers --port 8004

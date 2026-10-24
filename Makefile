# On Windows without make, use tasks.ps1 (same targets).
PY ?= python

.PHONY: up down seed demo eval test lint
up:
	docker compose up -d --wait
down:
	docker compose down
seed:
	$(PY) scripts/generate_data.py
	$(PY) -m incidentiq.store.ingest
demo:
	$(PY) -m incidentiq.cli diagnose --demo
eval:
	$(PY) -m incidentiq.eval --split test --llm replay --out results/latest/
test:
	$(PY) -m pytest -m "not db"
lint:
	ruff check .

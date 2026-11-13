# On Windows without make, use tasks.ps1 (same targets).
PY ?= python
RUN ?= v1-tools
SPLIT ?= dev

.PHONY: up down seed demo eval eval-record test lint
up:
	docker compose up -d --wait
down:
	docker compose down
seed:
	$(PY) scripts/generate_data.py
	$(PY) -m incidentiq.store.ingest
demo:
	$(PY) -m incidentiq.cli diagnose --demo
# Replays every recorded run and checks it reproduces the committed results exactly.
eval:
	$(PY) -m incidentiq.eval --run all --split all --llm replay --check
# Records (or resumes recording) one run with the live model, e.g. make eval-record RUN=v1-tools SPLIT=all
eval-record:
	$(PY) -m incidentiq.eval --run $(RUN) --split $(SPLIT) --llm live
test:
	$(PY) -m pytest -m "not db"
lint:
	ruff check .

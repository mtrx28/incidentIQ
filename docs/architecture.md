# Architecture

A short description of how the pieces fit. For the overview and diagram see the [README](../README.md).

## The graph (`incidentiq/agents/graph.py`)

State is one Pydantic model (`GraphState`): the incident (alert only), the pending plan, observations (redacted tool results, each carrying evidence items), hypotheses, planner and observer notes, `step_count` and `max_steps` (default 8), the diagnosis, and `validation_errors`/`retries` for the verifier loop.

Nodes and edges:

```
planner --(not done and steps remain)--> act --> observe --> planner
planner --(done, or step_count >= max_steps)--> reporter
reporter --> verifier                      (when the verifier is on)
verifier --(ok, or retries used up)--> END
verifier --(problems and retries left)--> reporter
reporter --> END                           (when the verifier is off: v1, v2)
```

- **planner** (`planner.py`): one LLM call returning a `PlannerDecision` (reasoning, `done`, steps). With the v4 switch on, if the planner finishes without any runbook evidence, a runbook lookup built from the leading hypothesis is forced first.
- **act** (`investigator.py`): runs each planned step through `ToolBox` (`toolbox.py`), which checks the tool name and arguments. Results are redacted, stored as an `Observation`, and a repeated identical call is answered with a "duplicate call" error instead of running. A `ToolError` becomes an error observation the planner can see.
- **observe** (`investigator.py`): one LLM call that updates the hypotheses from the new results. Citations to evidence that was never collected are dropped.
- **reporter** (`reporter.py`): one LLM call returning a `Diagnosis`. The incident ID is copied from the state, not trusted from the model.
- **verifier** (`verifier.py`): pure code by default (see below). After 2 failed retries the diagnosis is kept with `unverified=True`.

LLM output is requested as JSON matching a Pydantic schema. If it fails validation, the client retries with the validation error appended (3 attempts in total).

## Tools (`incidentiq/tools/`)

All read-only. Each returns a `ToolResult` with a summary and citable evidence items.

| Tool | What it does | Evidence IDs |
|---|---|---|
| `metrics_query` | Summarises one time series over a window: min, max, mean, an aggregate, a change point (a shift of at least 3 baseline standard deviations, needing at least 8 points) and a few notable points. | `M-<series>` |
| `log_search` | Filters one incident's logs by service, time range, level and query terms (a line must contain at least one term), ranks by terms matched plus a small ERROR/WARN bonus, returns at most 30 lines. | `L-<line id>` |
| `runbook_retrieve` | Embeds the query and returns the top-k runbook sections by cosine similarity from pgvector (default k=3, max 8). A keyword (BM25) version exists for the v1 benchmark run. | `R-<runbook>-<section>` |

Evidence IDs come from the data (line IDs, series IDs, runbook and section numbers), not from a run counter, so replay and gold labels line up.

## Runbook store (`incidentiq/store/`)

`chunking.py` splits each runbook markdown file into one chunk per `##` section (8 sections per runbook, 18 runbooks, 144 chunks). The embedded text is `"<title> - <heading>: <text>"`. `ingest.py` embeds the chunks with the local sentence-transformers model and loads them into `runbook_chunks` (HNSW index, cosine). `embedding_config` stores the model name and dimension, and ingestion refuses to mix embedders unless `--reset` is given.

## Verifier rules

1. Every cited evidence ID was retrieved in this run.
2. Every recommended action cites a runbook section, and there is at least one action.
3. The cited excerpts support the statement: at least 30% of the statement's key terms appear in them (lexical). With `--llm-entailment`, a statement that fails the lexical check gets a second chance from an LLM yes/no check. Each check records which method decided.
4. The category is one of the 10 allowed values.

Failures produce plain-language messages that go back to the reporter.

## LLM layer (`incidentiq/llm/`)

`LLMClient.complete(messages, response_schema=None)` redacts the messages, calls `generate`, redacts the reply, and parses and retries when a schema is given. Modes, chosen by `INCIDENTIQ_LLM`:

- `replay` (default): answers from `data/llm_cache/`, keyed by a SHA-256 of the model, messages and schema name. A missing key raises `CacheMiss` with instructions.
- `live`: calls any OpenAI-compatible endpoint (temperature 0), writes each reply to the cache, spaces calls out for the free tier's per-minute limit, and stops with `QuotaExhausted` at the daily limit. Rerunning continues from the cache.
- `mock`: a deterministic stub for unit tests.

## Evaluation (`incidentiq/eval/`)

`variants.py` defines the five benchmark versions as switches (`kind`, `retrieval`, `verifier`, `tuned`). `runner.py` runs a variant over incidents and records the per-incident LLM stats and prompt-leak check. `metrics.py` scores. `report.py` writes `results.json`, `results.md` and `traces.jsonl` deterministically (sorted keys, no timestamps), which is what lets replay reproduce them byte for byte. `__main__.py` is the CLI. The v0 baseline is `agents/baseline.py`.

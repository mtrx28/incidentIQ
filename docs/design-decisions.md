# Design decisions

Short reasons for the main choices, and what each one costs.

## LangGraph for the control loop

The task has distinct steps with branching: plan, run tools, update beliefs, write the answer, check it, maybe retry. Expressing these as graph nodes with conditional edges keeps each node small and testable alone (`tests/test_graph.py` runs the graph with a mock LLM), and puts the two safety limits in plain view: the tool-call cap (`max_steps`, 8) and the verifier retry limit (2). Cost: one more dependency, and the graph is small enough that a plain loop would also have worked.

## Three read-only tools

The agent can only read: query a metric series, search logs, retrieve runbook sections. It cannot change anything, which keeps the project in "recommend, don't act" territory. Tool arguments are checked before running, and errors come back as readable messages the planner can act on, because during development a bad timestamp crashed a tool and cost the agent its first steps (see `results/TUNING_LOG.md`).

## pgvector for runbook retrieval

Runbook retrieval is the one place dense embeddings are used. Chunks are one per runbook section so a citation points at exactly one section. Postgres with pgvector (Docker) was chosen over an in-memory index so the store looks like a real deployment: a table, an HNSW cosine index, and a config row recording which embedding model built it (mixing embedders silently ruins similarity, so ingestion refuses to). With 144 chunks Postgres will often scan sequentially anyway; the index is there so the design holds at a larger scale. The embedder is a small local model (`all-MiniLM-L6-v2`, 384 dimensions) so no API key is needed. Retrieval alone was also measured without any LLM (README, "Retrieval only"), including a keyword (BM25) alternative, so its share of the end-to-end score is visible.

## Pydantic for outputs

Every diagnosis is a `Diagnosis` model: a category from a fixed list, claims that each need at least one evidence ID, recommended actions, and an `unverified` flag. Output that does not validate is rejected and retried with the error message appended. This makes the output machine-checkable, which the verifier and the scoring both rely on.

## A verifier that checks grounding, not truth

The verifier's rules are deterministic: IDs exist, actions cite runbooks, the category is allowed, and the cited text overlaps the claim. It deliberately stops short of judging whether the claim is right. Its lexical support check is cheap and reproducible but approximate, and it is the same check one of the reported metrics uses, which is why the gold-ID support measure is reported next to it (see [evaluation.md](evaluation.md)). An optional LLM entailment check exists for statements the lexical check rejects.

## Replay mode

Model replies are recorded once (live mode writes each reply to `data/llm_cache/`, keyed by a hash of the request) and replayed afterwards. This makes the demo and the whole benchmark runnable offline with no key, and `make eval` can check that every committed result is reproduced exactly. Costs: base prompts are frozen (a changed prompt makes its recordings unreachable, so `tests/test_prompts.py` pins their hashes, and deliberate changes go through the `tuned` switch); prompts must be deterministic; and the free tier's daily quota meant recording was spread over several sessions, which is why live mode resumes from the cache.

## Redaction before the LLM

Logs contain PII and secrets, and a prompt sent to a hosted model is data leaving the building. So tool output is redacted before it enters the graph state, and the LLM client redacts every prompt and reply again as a second layer. Placeholders are typed and stable within an incident so the agent can still reason about "the same user". The limits of regex redaction are measured and reported honestly in [redaction.md](redaction.md): perfect on the generator's own formats, 59.5% on an independent hand-written set.

## The evaluation lives in the repo, with a dev/test split

Results are committed (`results/`), the README tables are generated from them and a test fails if they drift, and the tuning protocol is written down (`results/TUNING_LOG.md`). The point is that every number in the README can be checked, including the unflattering ones: the single-call baseline scores highest on the original data, and a higher-volume condition meant to test that is pre-registered but not yet run ([benchmark-scale100.md](benchmark-scale100.md)).

## Synthetic data, generated with a fixed seed

Real incident data with real PII would not be shareable. A seeded generator (`scripts/generate_data.py`) produces byte-identical data every run, writes the gold labels at generation time, and injects PII with a manifest of exactly where each value is. The cost is realism: log noise is template-based and the runbooks were written by the same author as the data.

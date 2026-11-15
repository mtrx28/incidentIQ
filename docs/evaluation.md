# Evaluation

This page describes how the benchmark is run and scored, what the numbers can and cannot support, and the weaknesses noticed while building it. The results tables are in the [README](../README.md); raw files are in `results/`.

## Data and split

- 40 synthetic incidents, 4 for each of 10 root-cause categories, on 6 services. Ten of them are hard cases (one per category): cause visible only in logs, only in metrics, overlapping symptoms, or needing the runbook to disambiguate.
- Each incident has ground truth: category, a short statement, gold evidence IDs (log lines, metric series, runbook sections) and a gold runbook section.
- Split, fixed in `data/split.json`: **dev** = 15 incidents (used while tuning prompts and stopping rules), **test** = 25 incidents (held out; used only for reported numbers).
- The agent is only given the alert. Ground truth is loaded by the harness only.

## The five versions

| Run | What changes |
|---|---|
| `v0-baseline` | One LLM call with the alert and the last 100 log lines (all services, up to the alert time). No tools, no loop, no runbooks. |
| `v1-tools` | Plan-act-observe loop with metrics, log search and keyword (BM25) runbook search. No verifier. |
| `v2-retrieval` | v1 with dense-embedding runbook retrieval (pgvector; one chunk per section with title and heading prepended). Note that this changes two things at once: the search method and the chunk text. |
| `v3-verifier` | v2 plus the citation verifier and up to 2 reporter retries. |
| `v4-final` | v3 plus prompt and stopping-rule changes written from dev failures only. |

All runs use the same model (`gemini-3.5-flash-lite`, temperature 0), the same data and the same scoring. Each run was recorded once and is replayed from the cache.

## Protocol

1. Prompts and tools for v1 to v3 were frozen before the benchmark was recorded (`tests/test_prompts.py` pins the base prompts).
2. v4 was written using dev-split failures only. The test split was not run until v4 was frozen. It was then run with `--quiet`, which suppresses per-incident lines, so individual test failures were not looked at before the freeze. The reason is simple: if a prompt change is chosen after seeing which test incidents failed, the test score measures the fit to those incidents, not generalisation.
3. Every change made for v4 and the reasoning for stopping after one iteration are in [`results/TUNING_LOG.md`](../results/TUNING_LOG.md).
4. `python -m incidentiq.eval --run all --split all --llm replay --check` replays every run and fails unless `results.json`, `results.md` and `traces.jsonl` are byte-identical to the committed files.
5. After the runs were recorded, a short factual note per misdiagnosed incident was written from the traces (`results/<run>/failure_notes.json`, shown in each `results.md`). These notes are descriptive and were not used to change any version. Because they exist for the test split, **any new version designed after reading them would no longer have an unseen test split**.

## Metric definitions

Copied from the docstring of `incidentiq/eval/metrics.py`:

```
accuracy            predicted root-cause category equals the true one.
strict accuracy     category correct AND the diagnosis cites at least one gold log or metric ID,
                    i.e. it points at the evidence that actually shows the cause.
citation validity   share of cited IDs (claims and actions) that were retrieved in this run.
citation support    share of statements whose cited evidence supports them, two ways:
                      lexical  the verifier's own overlap check (so, for runs with the verifier
                               on, this measure partly grades its own homework);
                      gold     the statement cites at least one gold evidence ID (stricter, and
                               independent of the verifier).
gold recall         share of the incident's gold evidence IDs that appear in the citations.
gold runbook cited  an action cites the gold runbook section.
Failed runs (the model never produced valid output) count as wrong with no citations.
```

`results.md` also reports "cause evidence retrieved at all" (any gold log or metric ID appeared in a tool result), tool calls, LLM calls, reporter retries, tokens, and recorded LLM latency per incident.

### The circularity caveat

The **lexical** support check is the same check the verifier applies (share of a statement's key terms found in the evidence it cites, threshold 0.3). In v3 and v4 the verifier makes the reporter rewrite statements until they pass that check, so a high lexical score there is partly the verifier agreeing with itself. It is not independent evidence that claims are grounded. The **gold** support check does not depend on the verifier. It asks whether the statement cites at least one gold evidence ID, which is strict (a correct statement citing equivalent evidence outside the gold set does not count). In these results the lexical rate rose from 87.0% (v2) to 98.0% (v3), while the gold rate did not rise (38.0% to 36.7%) and accuracy did not rise.

### Confidence intervals

Accuracy intervals are 95% Wilson score intervals for a proportion (`wilson()` in `metrics.py`), for example 20 of 25 gives 60.9% to 91.1%. They treat incidents as independent draws and do not include any variation from the model, since each run was recorded once. With 25 incidents they are wide, and most differences between versions fall inside them. No significance test is reported or claimed.

## Paired comparison on the test split

Counts of incidents whose outcome changed between two versions on the same 25 test incidents. Generated from `results/*/results.json` by `scripts/make_readme_tables.py`. No incident details are listed on purpose; see the protocol above.

<!-- BEGIN GENERATED:paired (python scripts/make_readme_tables.py --write) -->
| Comparison (test split) | wrong to right | right to wrong | both right | both wrong |
|---|---|---|---|---|
| v1-tools to v4-final | 5 | 1 | 15 | 4 |
| v0-baseline to v4-final | 0 | 3 | 20 | 2 |
<!-- END GENERATED:paired -->

How to read it: v4 gains some incidents and loses others relative to v1, and the gains are not shown to be more than chance with this sample. Relative to v0, v4 is not distinguishable on accuracy. The intervals for all three overlap.

## The `scale100` condition

The original logs are sparse (about 3 lines per minute across all services) and the cause lines sit minutes from the alert, which is why a plain log dump (v0) scores near ceiling. The pre-registered `scale100` condition adds about 100 times the log volume of healthy-traffic noise. It compares two single-call baselines (v0a naive, v0b filtered to WARN and ERROR), v4-final as recorded, and v5-scale. The design, protocol and disclosures are in [benchmark-scale100.md](benchmark-scale100.md); how v5 was built and chosen on dev is in [../results/scale100/TUNING_LOG.md](../results/scale100/TUNING_LOG.md). It was added after seeing that the baseline was already near ceiling, which the pre-registration discloses.

Test split (25 incidents), all four runs recorded once and replay-checked byte for byte:

| Version | Test accuracy | 95% Wilson interval |
|---|---|---|
| v0 naive baseline | 4% (1/25) | 0.7% to 19.5% |
| v0b filtered baseline | 88% (22/25) | 70.0% to 95.8% |
| v4-final | 76% (19/25) | 56.6% to 88.5% |
| v5-scale | 88% (22/25) | 70.0% to 95.8% |

Reading: v5-scale ties the filtered baseline and does not exceed it. It is far above the naive dump. Its 3-incident lead over v4 is inside overlapping intervals. The full table with the other metrics is in the [README](../README.md); raw files are in `results/scale100/`.

Protocol notes for this condition: the test split for v0a, v0b and v4 was recorded to a folder outside the repository and not read until every run was recorded and the replay checks passed. The v5 test run printed its own summary table when it finished, so v5's test score was seen before the rest were read; nothing was changed afterwards. v5 was frozen at commit `81d1665` before any v5 test call. Failure notes for the misses of v0b, v4 and v5 were written from the traces after all runs existed and were not used to change any version.

## Observations

Weaknesses and oddities noticed while building the benchmark. None of these were fixed; they are recorded so readers can weigh the results.

1. **Strict accuracy equals plain accuracy in every run.** The strict metric (category correct and a gold log or metric ID cited) never differed from accuracy, so here it adds no information.
2. **Single recording per version.** Each version was run once at temperature 0. Run-to-run variation of the model is not measured, so the intervals understate the uncertainty.
3. **v1 to v2 changes two things at once** (search method and chunk text), so the effect of embeddings alone is not isolated.
4. **Metric windows too short to test.** `metrics_query` needs at least 8 points to test for a change, and a 30-minute window at 5-minute steps has 7. In each of v1 to v3, 43 of the 106 to 108 metric queries returned a "too few points" summary. v4's prompt asks for at least an hour of data, and 0 of 130 did.
5. **Gold-ID support is conservative.** The gold set per incident is small (a handful of IDs) and a claim can be right while citing other lines that show the same thing. Gold support and gold recall may therefore understate real grounding.
6. **Lexical support can both over- and under-reject.** In v3 and v4, four correct diagnoses had a statement rejected at 14% to 27% overlap while citing the metric it described. A hand check with a changed date in an otherwise supported statement still scored 62% overlap, so dates and numbers can pass. This was not measured systematically.
7. **Unverified diagnoses still count for accuracy.** A diagnosis marked `unverified` is scored like any other. v3 ended 6 of 40 diagnoses unverified (4 because no runbook had been retrieved, so no recommended action could cite one; 2 for an unsupported claim). v4 ended 3 of 40 (1 and 2 respectively).
8. **Recorded latency is not comparable across splits.** v4's recorded LLM latency is 17.6 s per incident on test and 116.8 s on dev, because latency is whatever was observed when each reply was first obtained (free-tier waits included). Calls and tokens are the better cost measures.
9. **The v4 changes encode patterns of this data.** Some v4 guidance (WARN and INFO lines hold causes, check resource metrics) is ordinary SRE practice but was written from the synthetic data's patterns. `results/TUNING_LOG.md` says the same.
10. **The forced runbook step can confirm a wrong hypothesis.** It builds its query from the leading hypothesis, so it can retrieve text that appears to support it (also in the tuning log).
11. **Per-category and per-case breakdowns are tiny.** Test has 1 to 3 incidents per category and per hard-case type, so those tables are descriptive only.
12. **One category per incident.** Overlapping-symptom incidents are scored on a single category, so a diagnosis naming the second cause is wrong.
13. **The recorded cache is committed** (`data/llm_cache/`), and every one of its 1,278 files is read by the committed replays (original runs, scale100 and the demo), so nothing is left over from tuning.
14. **The demo uses the verifier but not the v4 prompt changes** (`incidentiq.cli` does not pass the tuned switch), so `make demo` shows the v3 configuration, not the final one.
15. **Test-split failure notes exist** (original condition and scale100). See protocol step 5: reading them before designing a new version would contaminate the test split.

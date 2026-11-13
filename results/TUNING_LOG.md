# How v4 was tuned (and what was not)

Protocol: prompts and stopping rules may be changed using **dev-split failures only** (15
incidents). The held-out **test** split (25 incidents) was not run until v4 was frozen, and it was
run with `--quiet`, which hides per-incident lines. This log records every change and why.

## Before v4: changes that fed the base prompts

During the M6 smoke test (three dev incidents: INC-006, INC-015, INC-019) the model sent
timestamps like `02:30:00Z`, which crashed a tool, and wasted its first three steps on rejected
calls. Fixes made to the base prompts and tools before anything was recorded for the benchmark:
the prompt now shows a full ISO timestamp, tools return a readable error for bad timestamps, and
a 7-point metric window now says "too few points" instead of "no significant change". The base
prompts have been frozen since (`tests/test_prompts.py`).

## What dev showed for v1-v3 (all three scored 11/15, 73%)

All four misses (INC-016, INC-019, INC-020, INC-024) were diagnosed as `downstream_timeout`:

- The generic symptom lines (`upstream returned 503 for /api/v1/...`, `request failed
  status=500`) appear under every cause. The model read them as "a dependency is failing" and went
  looking at dependencies, then kept the hypothesis even when the dependency's metrics were normal.
- It filtered logs to `level=ERROR`. The lines that name the cause are often WARN or INFO (pool
  warnings, rate limiting, cache problems), so the cause evidence was never retrieved.
- It queried only `error_rate_pct` and `latency_p99_ms`, never resource or traffic metrics, and
  it used 30-minute windows, too short for change detection.

## v4 changes (one iteration)

- Planner rules: do not filter to ERROR only; generic 5xx lines are symptoms, so choose
  `downstream_timeout` only with evidence about the dependency itself; check resource and traffic
  metrics of the alerting service; query at least an hour of metrics; if dependencies look healthy,
  look at the alerting service.
- Reporter rule: choose the category the cause evidence supports; cite the evidence that
  identifies the cause, not only symptom lines.
- Stopping rule: if the planner finishes without any runbook evidence, force one
  `runbook_retrieve` step for the leading hypothesis first.

## Dev result and why tuning stopped

v4 on dev: **12/15 (80%)**, against 11/15 (73%) for v3 and 14/15 (93%) for the single-call
baseline. It fixed INC-016, INC-019 and INC-024 and broke INC-014 and INC-021, which v3 had right.
INC-020 stayed wrong (cache outage read as pool exhaustion). The net change is one incident, which
is noise at this sample size.

I stopped after one iteration. The remaining dev misses each need a different fix (a generic
keyword query that matched nothing, a forced runbook lookup that confirmed a wrong hypothesis,
cache failure versus the pool saturation it causes). Fixing them one by one would fit 15
incidents, not improve the system, and any gain would not be expected to carry over to the test
split.

## Known weaknesses of the v4 changes

- The forced runbook step is built from the leading hypothesis, so it can retrieve text that
  appears to confirm a wrong hypothesis (INC-014).
- Some v4 guidance (WARN/INFO lines hold causes, check resource metrics) encodes patterns of this
  synthetic data. It is also ordinary SRE practice, but it may transfer less well to real logs.

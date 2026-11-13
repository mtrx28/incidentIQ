# scale100: how v5 was built, tested on dev, and chosen

Pre-registration: `docs/benchmark-scale100.md` (committed before any scale100 run). This log is
committed before any v5 run on the test split. Everything below uses the **dev** split (15
incidents) only. Test results for the baselines and v4 were recorded outside the repository and
have not been read at the time of writing.

## Gate G1

On scale100 dev: v0a (naive baseline) 3/15, v0b (filtered baseline) 14/15, v4-final as recorded
13/15. The pre-registered rule was "build v5 only if v4 dev accuracy is below v0b dev accuracy".
13/15 is below 14/15, so the rule was triggered. The margin is one incident, which is noise at
this sample size; the rule was followed as written, not argued with.

## What v5 is (the pre-registered scope, nothing more)

v5 = v4 plus a rarity-ranked `log_search` (score = number of distinct query terms matched +
1/log2(2 + f), f = lines sharing the message template; no level bonus), a default window of 30
minutes before to 5 minutes after the alert when neither start nor end is given, and a header
with counts by level and the most frequent templates. The model cannot choose the search mode.
Code commit: `81d1665`.

## One design review before recording

The four open design questions were ruled on before any v5 run (ranking when no query term is
given; header computed over the filtered set; no default window when only one of start/end is
given; interaction with v4's own advice to search from about 10 minutes before the alert). No
rule of the design was changed. One wording change was made to the v5 planner addendum: it now
says explicitly that giving a start or an end switches the default window off. Final addendum
hash `05a3a787e3ac3a36`; v5 planner prompt hash `b21caa19efcc4f66`. The v4 prompts and all base
prompts are unchanged and pinned in `tests/test_prompts.py`.

## Iteration 1 (dev)

v5 scored **13/15 (87%)**, the same total as v4, on **different incidents**:

- v5 got INC-014 and INC-021 right. v4 had missed both, and also missed both in the
  original-condition dev run.
- v5 missed INC-019 and INC-036, which v4 got right.

Other dev numbers, v5 against v4: gold evidence recall 60% vs 54%; lexical citation support 100%
vs 97%; tool calls per incident 4.9 vs 5.7; LLM calls 7.0 vs 7.7; prompt tokens 24,376 vs 23,843;
gold runbook cited 67% for both. The share of incidents where the cause evidence was retrieved
at all was **lower**, 87% vs 93%.

## Review of the two new dev misses (is there a defect inside the v5 scope?)

None was found.

- INC-036 (expired certificate): the agent's log search used the query "deploy version config
  error". The cause lines contain "certificate has expired" and "SSL handshake failed", none of
  the query terms, so they were filtered out before ranking. The term "config" matched 113
  routine heartbeat lines. One gold line (a renewal-failure warning about an hour before the
  onset) was outside the window anyway. This is a planner choice of query terms.
- INC-019 (metrics-only): there are no log lines to find. The agent never queried the
  connection-pool metric that holds the answer. This is a planner choice of metrics.

## Decision

- Iteration 2 was **not run** (one of the two allowed iterations was used). The pre-registered
  rule allows a second iteration only for a defect inside the v5 scope, and running one to
  change planner choices on two dev incidents would be tuning to noise.
- G2 (drop v5 if its dev accuracy is below v4's after at most two iterations): 13/15 is not
  below 13/15, so v5 survives.
- Final agent for the headline: **v5**, chosen on dev by a rule written before the run. This is
  a **tie** resolved in favour of the newer variant by a pre-written rule. It is not evidence
  that v5 is better than v4. Both v4 and v5 will be reported on the test split.
- v5 is frozen at commit `81d1665`.

## Caveats

- n = 15. The swap of two incidents each way is consistent with ordinary variation, and no
  repeated-run variance was measured (every run is a single recording at temperature 0).
- Nothing here shows that the rarity ranking helps. Any claim about it has to come from the test
  split, and even then only as "no significant difference" unless the intervals do not overlap.

## Budget

v5 iteration 1 used 105 new live calls. Counted calls so far: 624 of the 1,300 cap (cache files
minus the 491 present at the first quota stop; a 10% margin is kept on top).

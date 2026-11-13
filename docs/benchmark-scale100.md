# Pre-registration: the `scale100` condition

Condition name: `scale100`. The only change from the original benchmark is log volume.
- Each of the 6 services gets exactly 8,500 added noise lines per incident over the same 3-hour window (about 47 lines/min per service, about 100x the original volume).
- Realism anchor: under 1 line per second per service, about 0.3% of the request volume our own metrics imply (about 1,720 requests/second across services).
- Added lines use only the existing NOISE[service] and UNIVERSAL templates, chosen uniformly (original level mix preserved). No new templates, no benign ERROR noise, and no cause, symptom, distractor or PII lines.
- Line IDs for added lines start at L-5000 and go up in (timestamp, service) order. Added lines are merged with the original lines by timestamp; on a tie the original lines come first, in their file order, then the added lines. Original lines keep their relative order and IDs exactly; original line IDs, gold labels, the PII manifest, metrics, runbooks, alerts and the dev/test split are unchanged. Random seed: f"{SEED}-{incident_id}-scale". Generated at load time when INCIDENTIQ_LOG_SCALE=100 (never committed; about 250 MB); the default value 1 reproduces everything byte for byte.
- Baselines: v0a is the existing v0 (last 100 log lines, all services, up to the alert time). v0b is the last 100 WARN and ERROR lines of the alerting service up to the alert time. Both run unchanged.
- Systems compared: v0a, v0b, v4-final as recorded (the existing agent), and v5-scale (defined after dev analysis; scope: rarity-ranked log_search, a default window of 30 minutes before to 5 minutes after the alert, and a count/template header; at most 2 dev iterations; no changes to data, metrics, verifier or the test split; no category-specific keywords).
- Protocol: tune only on dev; test runs use --quiet; headline = best baseline vs best agent with Wilson 95% intervals; all numbers reported; hard stop at 3 days or 1,300 live calls.
- Disclosures: history (on the original data v0 scored 92% and v1 64% on the test split, so the condition was added after seeing that the baseline was already near ceiling); every cause line in this data is WARN or ERROR, so level filtering remains easy; template-based noise is easier than real logs.

## History disclosure

On the original data, v0 (the last 100 log lines) scored 92% and v1 scored 64% on the test split. The scale100 condition was added after seeing that the baseline was already near ceiling, so it was not planned in advance of those results.

## How to run

    python -m incidentiq.eval --run v0b-filtered-baseline --condition scale100 --split dev --llm live

Results go to `results/scale100/<run>/`. The data loader reads `INCIDENTIQ_LOG_SCALE` (1 or 100; anything else is an error).

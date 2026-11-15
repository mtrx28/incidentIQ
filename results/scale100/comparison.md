# Benchmark versions

Held-out **test** split unless noted. Same model and data for every row; only the system changes. Accuracy intervals are 95% Wilson intervals.

| Version | Test accuracy | Strict | Cite validity | Support (lexical / gold) | Gold recall | Gold runbook cited | LLM calls | Dev accuracy |
|---|---|---|---|---|---|---|---|---|
| v0-baseline | 4.0% (1/25, 0.7%-19.5%) | 0.0% | 100.0% | 85.7% / 0.0% | 0.0% | 0.0% | 1.0 | 20.0% |
| v0b-filtered-baseline | 88.0% (22/25, 70.0%-95.8%) | 88.0% | 100.0% | 96.7% / 80.0% | 38.2% | 0.0% | 1.0 | 93.3% |
| v4-final | 76.0% (19/25, 56.6%-88.5%) | 76.0% | 100.0% | 99.2% / 46.3% | 41.3% | 44.0% | 7.3 | 86.7% |
| v5-scale | 88.0% (22/25, 70.0%-95.8%) | 84.0% | 99.4% | 94.1% / 56.3% | 61.8% | 52.0% | 6.5 | 86.7% |

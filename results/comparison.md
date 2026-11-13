# Benchmark versions

Held-out **test** split unless noted. Same model and data for every row; only the system changes. Accuracy intervals are 95% Wilson intervals.

| Version | Test accuracy | Strict | Cite validity | Support (lexical / gold) | Gold recall | Gold runbook cited | LLM calls | Dev accuracy |
|---|---|---|---|---|---|---|---|---|
| v0-baseline | 92.0% (23/25, 75.0%-97.8%) | 92.0% | 100.0% | 98.7% / 71.6% | 48.2% | 0.0% | 1.0 | 93.3% |
| v1-tools | 64.0% (16/25, 44.5%-79.8%) | 64.0% | 100.0% | 89.5% / 34.7% | 31.3% | 12.0% | 6.6 | 73.3% |
| v2-retrieval | 64.0% (16/25, 44.5%-79.8%) | 64.0% | 100.0% | 87.0% / 38.0% | 33.4% | 24.0% | 6.6 | 73.3% |
| v3-verifier | 60.0% (15/25, 40.7%-76.6%) | 60.0% | 100.0% | 98.0% / 36.7% | 31.4% | 24.0% | 7.4 | 73.3% |
| v4-final | 80.0% (20/25, 60.9%-91.1%) | 80.0% | 100.0% | 98.3% / 52.5% | 53.6% | 44.0% | 7.2 | 80.0% |

# Windows equivalent of the Makefile. Usage: .\tasks.ps1 up|down|seed|demo|eval|test|lint
param([Parameter(Mandatory = $true)][ValidateSet("up", "down", "seed", "demo", "eval", "test", "lint")][string]$Task)
$py = if ($env:PY) { $env:PY } else { "python" }
switch ($Task) {
    "up"   { docker compose up -d --wait }
    "down" { docker compose down }
    "seed" { & $py scripts/generate_data.py; & $py -m incidentiq.store.ingest }
    "demo" { & $py -m incidentiq.cli diagnose --demo }
    "eval" { & $py -m incidentiq.eval --split test --llm replay --out results/latest/ }
    "test" { & $py -m pytest -m "not db" }
    "lint" { ruff check . }
}

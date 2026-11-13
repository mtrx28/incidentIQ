# Windows equivalent of the Makefile.
# Usage: .\tasks.ps1 up|down|seed|demo|eval|eval-record|test|lint [-Run v1-tools] [-Split dev]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("up", "down", "seed", "demo", "eval", "eval-record", "test", "lint")]
    [string]$Task,
    [string]$Run = "v1-tools",
    [string]$Split = "dev"
)
$py = if ($env:PY) { $env:PY } else { "python" }
switch ($Task) {
    "up"          { docker compose up -d --wait }
    "down"        { docker compose down }
    "seed"        { & $py scripts/generate_data.py; & $py -m incidentiq.store.ingest }
    "demo"        { & $py -m incidentiq.cli diagnose --demo }
    "eval"        { & $py -m incidentiq.eval --run all --split all --llm replay --check }
    "eval-record" { & $py -m incidentiq.eval --run $Run --split $Split --llm live }
    "test"        { & $py -m pytest -m "not db" }
    "lint"        { ruff check . }
}

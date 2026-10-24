"""Static definitions for the synthetic platform: services, metrics, and the 10 root causes.

Each CauseSpec says what an incident of that category looks like in metrics and logs.
Templates may use {name} placeholders filled from the per-incident context, plus
{int:lo:hi}, {hex:n} and {pii:type} which are drawn fresh each time a line is rendered.
"""

from dataclasses import dataclass, field

SEED = 20260301

POINTS = 36  # metric points per series (5-minute resolution, 3 hour window)
STEP_MIN = 5
ONSET_IDX = 20  # the anomaly starts at this point (100 minutes into the window)

SERVICES = ["auth", "checkout", "inventory", "notifications", "payments", "search"]
DEPENDENCIES = {
    "auth": [],
    "checkout": ["payments", "inventory", "auth"],
    "inventory": [],
    "notifications": ["auth"],
    "payments": ["auth"],
    "search": ["inventory"],
}

METRICS = [
    "cache_hit_ratio_pct",
    "cpu_pct",
    "db_pool_in_use_pct",
    "disk_used_pct",
    "error_rate_pct",
    "latency_p99_ms",
    "memory_pct",
    "request_rate_rps",
    "restarts",
]
PCT_METRICS = {m for m in METRICS if m.endswith("_pct")}

_REQUEST_RATE = {"auth": 450, "checkout": 220, "inventory": 300, "notifications": 90,
                 "payments": 140, "search": 520}
_LATENCY = {"auth": 90, "checkout": 260, "inventory": 120, "notifications": 180,
            "payments": 210, "search": 150}


def baseline(service: str, metric: str) -> tuple[float, float]:
    """(mean, noise standard deviation) of a healthy series."""
    if metric == "request_rate_rps":
        return _REQUEST_RATE[service], _REQUEST_RATE[service] * 0.04
    if metric == "latency_p99_ms":
        return _LATENCY[service], _LATENCY[service] * 0.06
    return {
        "cache_hit_ratio_pct": (93.0, 1.0),
        "cpu_pct": (38.0, 3.0),
        "db_pool_in_use_pct": (30.0, 3.0),
        "disk_used_pct": (42.0, 0.3),
        "error_rate_pct": (0.4, 0.12),
        "memory_pct": (56.0, 1.5),
        "restarts": (0.0, 0.0),
    }[metric]


def series_id(service: str, metric: str) -> str:
    """Stable evidence ID for a (service, metric) series, e.g. M-001. Same in every incident."""
    index = sorted((s, m) for s in SERVICES for m in METRICS).index((service, metric))
    return f"M-{index + 1:03d}"


@dataclass(frozen=True)
class Anomaly:
    """A change injected into one metric series.

    role: "svc" (the affected service), "dep" (its dependency) or "other" (a bystander).
    shape: step | ramp | spike | saw.
    target: absolute value, or "x4.2" meaning 4.2 times the healthy mean.
    lead: points before the onset at which a ramp/saw starts.
    span: points after the onset at which a ramp reaches its target.
    period: sawtooth period in points.
    """

    role: str
    metric: str
    shape: str
    target: float | str
    lead: int = 0
    span: int = 1
    period: int = 0


@dataclass(frozen=True)
class Line:
    """A log line template. offset_s is seconds relative to the onset."""

    role: str  # "svc" or "dep"
    level: str
    offset_s: int
    message: str


@dataclass(frozen=True)
class CauseSpec:
    category: str
    runbook: int  # runbook number holding the matching mitigation
    alert_kinds: list[str]  # "error_rate" and/or "latency"
    statement: str
    symptom_metrics: list[Anomaly]  # always present: what made the alert fire
    cause_metrics: list[Anomaly]  # cause-specific signatures (hidden in "logs_only")
    telltale_logs: list[Line]  # lines that reveal the cause (gold evidence)
    ambiguous_logs: list[Line]  # vaguer lines used in "runbook_needed" incidents
    services: list[str] = field(default_factory=lambda: list(SERVICES))


@dataclass(frozen=True)
class Distractor:
    """A red herring: noise that resembles another root cause but is unrelated."""

    name: str
    looks_like: str
    logs: list[tuple[str, str]]  # (level, message), emitted on a bystander service
    metric: Anomaly | None = None


CAUSES: list[CauseSpec] = [
    CauseSpec(
        category="bad_deployment",
        runbook=1,
        alert_kinds=["error_rate"],
        statement="Release v{ver} of {svc} introduced an unhandled NullPointerException; "
        "errors began right after the rolling deploy replaced v{prev_ver}.",
        symptom_metrics=[
            Anomaly("svc", "error_rate_pct", "step", 14.0),
            Anomaly("svc", "latency_p99_ms", "step", "x1.5"),
        ],
        cause_metrics=[Anomaly("svc", "restarts", "spike", 6.0)],
        telltale_logs=[
            Line("svc", "INFO", -150, "deploy started release=v{ver} previous=v{prev_ver} "
                 "strategy=rolling by=ci-bot sha={hex:7}"),
            Line("svc", "INFO", -40, "deploy completed release=v{ver} replicas=6/6 ready"),
            Line("svc", "ERROR", 15, "unhandled exception in OrderMapper.map: NullPointerException "
                 "release=v{ver} (field 'discount_code' missing)"),
            Line("svc", "ERROR", 50, "at com.shop.{svc}.OrderMapper.map(OrderMapper.java:88) "
                 "release=v{ver} request_id=req-{hex:8}"),
        ],
        ambiguous_logs=[
            Line("svc", "ERROR", 15, "handler failed: unexpected null value request_id=req-{hex:8}"),
            Line("svc", "ERROR", 50, "handler failed: unexpected null value request_id=req-{hex:8}"),
        ],
    ),
    CauseSpec(
        category="db_connection_pool_exhaustion",
        runbook=2,
        alert_kinds=["error_rate", "latency"],
        statement="The {svc} database connection pool (max {pool_max}) was fully saturated, so "
        "requests queued for a connection and timed out.",
        symptom_metrics=[
            Anomaly("svc", "error_rate_pct", "step", 18.0),
            Anomaly("svc", "latency_p99_ms", "ramp", 6000.0, lead=3, span=4),
        ],
        cause_metrics=[Anomaly("svc", "db_pool_in_use_pct", "ramp", 100.0, lead=4, span=3)],
        telltale_logs=[
            Line("svc", "ERROR", 10, "HikariPool-1 - Connection is not available, request timed out "
                 "after 30000ms (total={pool_max}, active={pool_max}, idle=0, waiting={int:20:60})"),
            Line("svc", "ERROR", 40, "Unable to acquire JDBC Connection "
                 "url=jdbc:postgresql://{svc}_app:{pii:secret_password}@{db}:5432/{dbname}"),
            Line("svc", "WARN", 95, "connection pool exhausted: max={pool_max} active={pool_max} "
                 "waiting={int:30:80}"),
        ],
        ambiguous_logs=[
            Line("svc", "ERROR", 10, "database request timed out after 30000ms"),
            Line("svc", "ERROR", 70, "database request timed out after 30000ms"),
        ],
    ),
    CauseSpec(
        category="slow_query_missing_index",
        runbook=3,
        alert_kinds=["error_rate", "latency"],
        statement="A schema migration dropped the index on orders.customer_ref, so a hot query on "
        "{svc} fell back to a sequential scan and slowed every request.",
        symptom_metrics=[Anomaly("svc", "error_rate_pct", "step", 6.0)],
        cause_metrics=[
            Anomaly("svc", "latency_p99_ms", "ramp", 5500.0, lead=2, span=3),
            Anomaly("svc", "db_pool_in_use_pct", "ramp", 70.0, lead=2, span=4),
        ],
        telltale_logs=[
            Line("svc", "INFO", -300, "schema migration {mig}_drop_idx_orders_customer_ref "
                 "completed in {int:2:9}s"),
            Line("svc", "WARN", 20, "slow query took {int:4200:9500}ms: SELECT * FROM orders WHERE "
                 "customer_ref = $1 rows_examined=4213877"),
            Line("svc", "WARN", 75, "query plan: Seq Scan on orders (rows=4213877) "
                 "filter=(customer_ref = $1) no usable index"),
        ],
        ambiguous_logs=[
            Line("svc", "ERROR", 20, "database request timed out after 5000ms"),
            Line("svc", "ERROR", 75, "database request timed out after 5000ms"),
        ],
    ),
    CauseSpec(
        category="downstream_timeout",
        runbook=4,
        alert_kinds=["error_rate", "latency"],
        statement="{dep}-service became slow, so calls from {svc} exceeded their 5000ms timeout "
        "and the circuit breaker opened.",
        symptom_metrics=[
            Anomaly("svc", "error_rate_pct", "step", 22.0),
            Anomaly("svc", "latency_p99_ms", "step", 5100.0),
        ],
        cause_metrics=[
            Anomaly("dep", "latency_p99_ms", "ramp", 9000.0, lead=1, span=2),
            Anomaly("dep", "cpu_pct", "step", 92.0),
        ],
        telltale_logs=[
            Line("svc", "ERROR", 10, "timeout calling {dep}-service after 5000ms (attempt 3/3) "
                 "endpoint=/v1/{ep}"),
            Line("svc", "ERROR", 30, "outbound call failed to={dep}-service "
                 "Authorization: Bearer {pii:secret_token} status=timeout"),
            Line("svc", "WARN", 60, "circuit breaker OPEN for {dep}-service failures=50/50 window=30s"),
            Line("dep", "WARN", 5, "request queue depth {int:800:2000} exceeds limit 500, "
                 "worker threads saturated"),
        ],
        ambiguous_logs=[
            Line("svc", "ERROR", 10, "upstream call exceeded deadline endpoint=/v1/{ep}"),
            Line("svc", "ERROR", 40, "upstream call exceeded deadline endpoint=/v1/{ep}"),
        ],
        services=["checkout", "payments", "search", "notifications"],
    ),
    CauseSpec(
        category="memory_leak_oom",
        runbook=5,
        alert_kinds=["error_rate"],
        statement="A memory leak in {svc} drove heap usage to the limit and the kernel OOM-killed "
        "the container repeatedly.",
        symptom_metrics=[Anomaly("svc", "error_rate_pct", "step", 9.0)],
        cause_metrics=[
            Anomaly("svc", "memory_pct", "saw", 99.0, lead=9, period=12),
            Anomaly("svc", "restarts", "spike", 4.0),
        ],
        telltale_logs=[
            Line("svc", "WARN", -240, "GC overhead {int:80:96}% heap_used={int:92:99}% "
                 "pause_ms={int:900:2500}"),
            Line("svc", "ERROR", 5, "java.lang.OutOfMemoryError: Java heap space"),
            Line("svc", "ERROR", 25, "container {svc}-7c9f killed: OOMKilled exit_code=137 "
                 "restarts={int:2:6}"),
        ],
        ambiguous_logs=[
            Line("svc", "WARN", 5, "pod {svc}-7c9f restarted (restart_count={int:2:6})"),
            Line("svc", "WARN", 120, "pod {svc}-7c9f restarted (restart_count={int:3:7})"),
        ],
    ),
    CauseSpec(
        category="disk_full",
        runbook=6,
        alert_kinds=["error_rate"],
        statement="The data volume on {svc} filled to 100%, so writes failed with ENOSPC.",
        symptom_metrics=[Anomaly("svc", "error_rate_pct", "step", 25.0)],
        cause_metrics=[Anomaly("svc", "disk_used_pct", "ramp", 100.0, lead=12, span=0)],
        telltale_logs=[
            Line("svc", "WARN", -600, "disk usage {int:94:99}% on /data (threshold 90%)"),
            Line("svc", "ERROR", 5, "write failed: No space left on device (errno=28) "
                 "path=/var/log/{svc}/app.log"),
            Line("svc", "ERROR", 35, "WAL archiving failed: could not write file: "
                 "No space left on device"),
        ],
        ambiguous_logs=[
            Line("svc", "ERROR", 5, "failed to write temp file for upload path=/data/tmp/{hex:8}"),
            Line("svc", "ERROR", 45, "I/O error on write path=/data/tmp/{hex:8}"),
        ],
    ),
    CauseSpec(
        category="expired_tls_cert",
        runbook=7,
        alert_kinds=["error_rate"],
        statement="The TLS certificate for {svc}.internal.shop expired at {expiry} and was not "
        "renewed, so clients could not complete handshakes.",
        symptom_metrics=[Anomaly("svc", "error_rate_pct", "step", 40.0)],
        cause_metrics=[
            Anomaly("svc", "latency_p99_ms", "step", 25.0),
            Anomaly("svc", "request_rate_rps", "step", "x0.4"),
        ],
        telltale_logs=[
            Line("svc", "WARN", -3600, "certificate renewal job failed: acme challenge timeout "
                 "(last success {int:80:89} days ago)"),
            Line("svc", "ERROR", 5, "SSL handshake failed: certificate has expired "
                 "notAfter={expiry} subject=CN={svc}.internal.shop"),
            Line("svc", "ERROR", 30, "x509: certificate has expired or is not yet valid: "
                 "current time {now} is after {expiry}"),
        ],
        ambiguous_logs=[
            Line("svc", "ERROR", 5, "TLS connection error: handshake failure peer={svc}.internal.shop"),
            Line("svc", "ERROR", 30, "TLS connection error: handshake failure peer={svc}.internal.shop"),
        ],
    ),
    CauseSpec(
        category="misconfiguration",
        runbook=8,
        alert_kinds=["error_rate"],
        statement="A config change set {cfg_key} to '{bad_val}' (was '{good_val}') and {svc} "
        "began failing as it restarted with the bad value.",
        symptom_metrics=[Anomaly("svc", "error_rate_pct", "step", 30.0)],
        cause_metrics=[Anomaly("svc", "restarts", "spike", 3.0)],
        telltale_logs=[
            Line("svc", "INFO", -90, "config reload: {cfg_key} changed from '{good_val}' to "
                 "'{bad_val}' by=config-bot via config-service"),
            Line("svc", "ERROR", 10, "startup validation failed: {cfg_key}='{bad_val}' is not "
                 "accepted, running in degraded mode"),
            Line("svc", "ERROR", 45, "request rejected: invalid configuration {cfg_key}='{bad_val}'"),
        ],
        ambiguous_logs=[
            Line("svc", "ERROR", 10, "handler failed: invalid argument in request processing "
                 "request_id=req-{hex:8}"),
            Line("svc", "ERROR", 50, "handler failed: invalid argument in request processing "
                 "request_id=req-{hex:8}"),
        ],
    ),
    CauseSpec(
        category="traffic_spike_rate_limit",
        runbook=9,
        alert_kinds=["error_rate", "latency"],
        statement="Inbound traffic to {svc} jumped to about four times normal; autoscaling hit "
        "its ceiling and rate limiting plus load shedding rejected requests.",
        symptom_metrics=[
            Anomaly("svc", "error_rate_pct", "step", 16.0),
            Anomaly("svc", "latency_p99_ms", "ramp", 2800.0, lead=0, span=2),
        ],
        cause_metrics=[
            Anomaly("svc", "request_rate_rps", "step", "x4.2"),
            Anomaly("svc", "cpu_pct", "ramp", 96.0, lead=0, span=2),
        ],
        telltale_logs=[
            Line("svc", "WARN", 5, "rate limit exceeded client={client} limit=1000rps "
                 "current={int:3000:5000}rps -> 429"),
            Line("svc", "WARN", 30, "load shedding enabled: queue_depth={int:3000:6000} max=2000"),
            Line("svc", "INFO", 60, "autoscaler: max replicas reached (12/12) cpu={int:90:99}%"),
        ],
        ambiguous_logs=[
            Line("svc", "ERROR", 5, "request rejected: service unavailable (overloaded)"),
            Line("svc", "ERROR", 40, "request rejected: service unavailable (overloaded)"),
        ],
    ),
    CauseSpec(
        category="cache_stampede_outage",
        runbook=10,
        alert_kinds=["error_rate", "latency"],
        statement="The Redis cache in front of {svc} went down; every request fell through to the "
        "database, which saturated under the resulting stampede.",
        symptom_metrics=[
            Anomaly("svc", "error_rate_pct", "step", 11.0),
            Anomaly("svc", "latency_p99_ms", "ramp", 4500.0, lead=0, span=3),
        ],
        cause_metrics=[
            Anomaly("svc", "cache_hit_ratio_pct", "step", 4.0),
            Anomaly("svc", "db_pool_in_use_pct", "ramp", 96.0, lead=0, span=3),
        ],
        telltale_logs=[
            Line("svc", "ERROR", -20, "redis connection refused: redis-{shard}.cache.internal:6379 "
                 "(ECONNREFUSED)"),
            Line("svc", "WARN", 15, "cache miss ratio {int:92:99}%, falling back to database "
                 "key=product:{sku}"),
            Line("svc", "WARN", 45, "thundering herd: {int:800:2500} concurrent loads for "
                 "key=product:featured"),
        ],
        ambiguous_logs=[
            Line("svc", "WARN", 15, "cache lookup failed, falling back to origin"),
            Line("svc", "WARN", 60, "cache lookup failed, falling back to origin"),
        ],
    ),
]
CAUSE_BY_NAME = {c.category: c for c in CAUSES}

DISTRACTORS: list[Distractor] = [
    Distractor("deprecated_api_client", "bad_deployment",
               [("WARN", "deprecated API version v1 used by client=mobile-app/3.4.1, "
                 "sunset scheduled")]),
    Distractor("unrelated_cert_expiring", "expired_tls_cert",
               [("WARN", "certificate for dashboard.corp.shop expires in 21 days")]),
    Distractor("nightly_analytics_query", "slow_query_missing_index",
               [("WARN", "slow query took 1840ms: analytics_nightly_rollup (expected, batch job)")]),
    Distractor("minor_gc_pause", "memory_leak_oom",
               [("WARN", "GC pause 180ms heap_used=71%")]),
    Distractor("partner_webhook_retry", "downstream_timeout",
               [("WARN", "webhook delivery to partner-x retry 2/5 status=502"),
                ("WARN", "webhook delivery to partner-x retry 3/5 status=502")]),
    Distractor("log_volume_notice", "disk_full",
               [("WARN", "log volume on node-7 at 71%, rotation scheduled")]),
    Distractor("session_cache_eviction", "cache_stampede_outage",
               [("WARN", "cache eviction rate elevated key_prefix=session: evicted=412")]),
    Distractor("config_drift_notice", "misconfiguration",
               [("WARN", "config key LEGACY_TIMEOUT_MS is deprecated and ignored")]),
    Distractor("bystander_cpu_blip", "traffic_spike_rate_limit",
               [("INFO", "autoscaler: scaled replicas 3 -> 4 (scheduled report job)")],
               Anomaly("other", "cpu_pct", "spike", 63.0)),
    Distractor("pool_warning_bystander", "db_connection_pool_exhaustion",
               [("WARN", "connection pool utilisation 74% (threshold 70%)")],
               Anomaly("other", "db_pool_in_use_pct", "spike", 74.0)),
]

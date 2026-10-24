"""Tools and chunking, tested against the committed dataset. No database or model needed."""

import pytest

from incidentiq import data
from incidentiq.config import DATA_DIR
from incidentiq.store.chunking import chunk_directory, chunk_runbook
from incidentiq.tools import ToolError
from incidentiq.tools.logs import MAX_RESULTS, log_search, search_logs
from incidentiq.tools.metrics import find_change_point, metrics_query, query_metric


def _incident(category: str, hard_case: str | None = None) -> str:
    for incident_id in data.list_incident_ids():
        t = data.load_ground_truth(incident_id)
        if t.root_cause_category == category and t.hard_case == hard_case:
            return incident_id
    raise LookupError(category)


# --- metrics ------------------------------------------------------------------------------


def test_disk_full_shows_a_change_and_hits_the_ceiling():
    inc = _incident("disk_full")
    svc = data.load_incident(inc).service
    s = query_metric(inc, svc, "disk_used_pct")
    assert s.maximum > 95 and s.change_point is not None
    assert s.series_id in data.load_ground_truth(inc).gold_evidence_ids


def test_a_healthy_series_has_no_change_point():
    inc = _incident("disk_full")
    svc = data.load_incident(inc).service
    assert query_metric(inc, svc, "cpu_pct").change_point is None


def test_metrics_result_is_compact_and_cites_the_series_id():
    inc = _incident("bad_deployment")
    svc = data.load_incident(inc).service
    result = metrics_query(inc, svc, "error_rate_pct")
    assert len(result.evidence) == 1 and result.evidence[0].kind == "metric"
    assert result.evidence[0].evidence_id.startswith("M-")
    assert len(result.evidence[0].excerpt) < 700  # a summary, not thousands of rows


def test_metrics_time_range_filters_points():
    inc = _incident("bad_deployment")
    incident = data.load_incident(inc)
    s = query_metric(inc, incident.service, "error_rate_pct",
                     start=incident.window_start, end=incident.start_time)
    assert s.change_point is not None and s.end <= incident.start_time
    full = query_metric(inc, incident.service, "error_rate_pct")
    assert s.points < full.points


def test_metrics_aggregations():
    inc = _incident("bad_deployment")
    svc = data.load_incident(inc).service
    assert query_metric(inc, svc, "error_rate_pct", aggregation="max").aggregate == \
        query_metric(inc, svc, "error_rate_pct").maximum


@pytest.mark.parametrize("kwargs", [
    {"service": "nope", "metric": "cpu_pct"},
    {"service": "auth", "metric": "nope"},
    {"service": "auth", "metric": "cpu_pct", "aggregation": "median"},
])
def test_metrics_bad_arguments_raise_tool_error(kwargs):
    with pytest.raises(ToolError):
        query_metric("INC-001", **kwargs)


def test_metrics_empty_range_raises_tool_error():
    with pytest.raises(ToolError):
        query_metric("INC-001", "auth", "cpu_pct", start="2030-01-01T00:00:00Z")


def test_change_point_detects_a_step():
    points = [(f"2026-01-01T00:{i:02d}:00Z", 1.0 + (i % 2) * 0.1) for i in range(10)]
    points += [(f"2026-01-01T01:{i:02d}:00Z", 9.0) for i in range(10)]
    cp = find_change_point(points)
    assert cp and cp.ts == "2026-01-01T01:00:00Z"


# --- logs ---------------------------------------------------------------------------------


def test_log_search_finds_the_telltale_line_and_cites_its_id():
    inc = _incident("disk_full")
    result = log_search(inc, query="No space left on device")
    gold = {i for i in data.load_ground_truth(inc).gold_evidence_ids if i.startswith("L-")}
    assert gold & {e.evidence_id for e in result.evidence}
    assert all(e.kind == "log" for e in result.evidence)


def test_log_search_caps_results_and_stays_in_time_order():
    inc = _incident("bad_deployment")
    lines, total = search_logs(inc, level="ERROR", limit=500)
    assert len(lines) <= MAX_RESULTS and total >= len(lines)
    assert [ln.ts for ln in lines] == sorted(ln.ts for ln in lines)


def test_log_search_filters_by_service_level_and_time():
    inc = _incident("bad_deployment")
    incident = data.load_incident(inc)
    lines, _ = search_logs(inc, service=incident.service, level="warn",
                           start=incident.window_start, end=incident.start_time)
    assert lines and all(
        ln.service == incident.service and ln.level == "WARN" and ln.ts <= incident.start_time
        for ln in lines)


def test_precise_query_beats_a_bare_level_filter():
    inc = _incident("db_connection_pool_exhaustion")
    lines, _ = search_logs(inc, query="connection pool exhausted", limit=3)
    assert any("pool exhausted" in ln.message for ln in lines)


def test_log_search_is_deterministic():
    assert search_logs("INC-001", query="timeout") == search_logs("INC-001", query="timeout")


@pytest.mark.parametrize("kwargs", [{"service": "nope"}, {"level": "LOUD"}])
def test_log_search_bad_arguments_raise_tool_error(kwargs):
    with pytest.raises(ToolError):
        search_logs("INC-001", **kwargs)


# --- runbook chunking (database tests live in test_runbook_store.py) -----------------------


def test_one_chunk_per_section_with_stable_ids():
    chunks = chunk_directory()
    assert len(chunks) == 18 * 8
    assert len({c.section_id for c in chunks}) == len(chunks)
    mitigation = next(c for c in chunks if c.section_id == "R-02-5")
    assert mitigation.heading == "Mitigation" and "pool" in mitigation.title.lower()


def test_embed_text_carries_title_and_heading():
    chunk = chunk_directory()[0]
    assert chunk.title in chunk.embed_text and chunk.heading in chunk.embed_text


def test_gold_runbook_sections_exist_as_chunks():
    ids = {c.section_id for c in chunk_directory()}
    for incident_id in data.list_incident_ids():
        gold = data.load_ground_truth(incident_id).gold_runbook_section
        assert gold in ids


def test_chunker_rejects_a_file_without_a_title():
    with pytest.raises(ValueError):
        chunk_runbook("## 1. Summary\n\ntext\n")


def test_runbooks_dir_exists():
    assert (DATA_DIR / "runbooks").is_dir()

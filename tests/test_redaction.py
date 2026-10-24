import json

import pytest

from incidentiq import data
from incidentiq.checksums import luhn_valid, verhoeff_check_digit, verhoeff_valid
from incidentiq.config import ROOT
from incidentiq.eval.redaction_eval import evaluate
from incidentiq.redaction import Redactor, redact, redact_tool_result
from incidentiq.schemas import Evidence, ToolResult
from incidentiq.tools.logs import log_search

# --- checksums ----------------------------------------------------------------------------


def test_verhoeff_known_vector():
    assert verhoeff_check_digit("236") == "3"
    assert verhoeff_valid("2363") and not verhoeff_valid("2364")


def test_luhn_known_numbers():
    assert luhn_valid("4111111111111111") and not luhn_valid("4111111111111112")


# --- one case per detector ----------------------------------------------------------------


@pytest.mark.parametrize("text,secret", [
    ("login failed for priya.sharma42@gmail.com reason=bad", "priya.sharma42@gmail.com"),
    ("sms to +91 98765 43210 sent", "98765 43210"),
    ("sms to +919876543210 sent", "9876543210"),
    ("call +1 415-555-0132 back", "415-555-0132"),
    ("payment card=4111 1111 1111 1111 ok", "4111 1111 1111 1111"),
    ("payment card=4111-1111-1111-1111 ok", "4111-1111-1111-1111"),
    ("kyc id 2345 6789 0124 passed", "2345 6789 0124"),
    ("login from client_ip=203.0.113.77 ok", "203.0.113.77"),
    ("order placed user=Priya Sharma items=3", "Priya Sharma"),
    ("connecting postgres://app:Maple#4821x@db-1:5432/orders", "Maple#4821x"),
    ("headers Authorization: Bearer abcDEF123456ghiJKL789012mnoPQR", "abcDEF123456ghiJKL789012mnoPQR"),
    ("provider call api_key=iq_sk_abcdefghijklmnop12345678 status=200", "iq_sk_abcdefghijklmnop12345678"),
    ("s3 upload aws_access_key_id=AKIAQWERTYUI01234567", "AKIAQWERTYUI01234567"),
    ("indexer loaded kqZ9x2LmN8vB4tYw7RcD1sFhJ3gE5aP", "kqZ9x2LmN8vB4tYw7RcD1sFhJ3gE5aP"),
])
def test_value_is_removed_and_replaced_by_a_placeholder(text, secret):
    clean, findings = redact(text)
    assert secret not in clean
    assert findings and any(f.placeholder in clean for f in findings)


def test_aadhaar_needs_a_valid_checksum_by_default():
    body = "23456789012"
    valid = body + verhoeff_check_digit(body)
    invalid = body + str((int(verhoeff_check_digit(body)) + 1) % 10)
    assert valid not in redact(f"id {valid} ok")[0]
    assert invalid in redact(f"id {invalid} ok")[0]
    assert invalid not in Redactor(verhoeff=False).redact(f"id {invalid} ok")[0]


def test_card_needs_a_valid_luhn_check():
    assert "4111111111111112" in redact("ref 4111111111111112 done")[0]


# --- things that must be left alone -------------------------------------------------------


@pytest.mark.parametrize("text", [
    "2026-03-12T14:02:07Z health check ok latency_ms=3",
    "request failed status=500 path=/api/v1/orders request_id=req-8f3a2c91",
    "POST /api/v1/checkout status=200 duration_ms=212 trace=0123456789abcdef",
    "ranking model loaded version=v3.4.1 sha=9f2c1ab",
    "deploy completed release=v4.2.1 replicas=6/6 ready",
    "connecting to inventory-db-1:5432 pool=20",
    "token validated sub=u-482913 latency_ms=4",
    "password policy check passed",
    "schema migration 20260312_drop_idx_orders_customer_ref completed in 6s",
    "gateway_ref=0123456789ab ledger_entry=482913",
    "slow query took 6770ms: SELECT * FROM orders WHERE customer_ref = $1 rows_examined=4213877",
    "write failed: No space left on device (errno=28) path=/var/log/checkout/app.log",
])
def test_ordinary_log_lines_are_not_altered(text):
    assert redact(text) == (text, [])


# --- placeholders -------------------------------------------------------------------------


def test_same_value_gets_the_same_placeholder_within_one_redactor():
    r = Redactor()
    a, _ = r.redact("login failed for sam@example.org")
    b, _ = r.redact("sent receipt to sam@example.org and lee@example.org")
    assert a == "login failed for [EMAIL_1]"
    assert b == "sent receipt to [EMAIL_1] and [EMAIL_2]"


def test_placeholder_numbering_is_independent_per_redactor():
    assert redact("a@b.org")[0] == redact("c@d.org")[0] == "[EMAIL_1]"


def test_formatting_variants_of_one_card_share_a_placeholder():
    r = Redactor()
    a, _ = r.redact("card 4111 1111 1111 1111")
    b, _ = r.redact("card 4111-1111-1111-1111")
    assert a.split()[-1] == b.split()[-1] == "[CARD_1]"


def test_findings_never_contain_the_value():
    _, findings = redact("login failed for sam@example.org")
    assert not any(hasattr(f, "value") for f in findings)
    assert "sam@example.org" not in repr(findings)


def test_overlapping_matches_are_claimed_once():
    clean, findings = redact("dial postgres://app:s3cretPass@host.example.org/db")
    assert len(findings) == 1 and "host.example.org" in clean


# --- tool results -------------------------------------------------------------------------


def test_tool_result_is_redacted_but_evidence_ids_survive():
    result = ToolResult(
        tool="log_search", args={"query": "sam@example.org", "service": "auth"},
        summary="1 line for sam@example.org",
        evidence=[Evidence(evidence_id="L-0042", kind="log",
                           excerpt="auth WARN login failed for sam@example.org")])
    clean, findings = redact_tool_result(result, Redactor())
    dumped = clean.model_dump_json()
    assert "sam@example.org" not in dumped
    assert clean.evidence[0].evidence_id == "L-0042" and clean.args["service"] == "auth"
    assert len(findings) == 3


# --- regression: injected items never reach the LLM-facing text ---------------------------

KNOWN_MISSES = {tuple(k) for k in json.loads(
    (ROOT / "tests" / "redaction_known_misses.json").read_text(encoding="utf-8"))}


class _NoOpRedactor:
    """Stands in for a broken redactor, to prove the regression test can fail."""

    def redact(self, text):
        return text, []


def _leaks(make_redactor) -> list[tuple]:
    """Fetch each injected line through the real log_search tool, redact it, look for the value."""
    manifest = json.loads((ROOT / "data" / "pii_manifest.json").read_text(encoding="utf-8"))
    leaks, redactors, lines = [], {}, {}
    for item in manifest:
        inc = item["incident_id"]
        if inc not in lines:
            lines[inc] = {ln.line_id: ln for ln in data.load_logs(inc)}
        line = lines[inc][item["line_id"]]
        result = log_search(inc, service=line.service, start=line.ts, end=line.ts, limit=30)
        assert item["line_id"] in {e.evidence_id for e in result.evidence}, "line was not fetched"
        clean, _ = redact_tool_result(result, redactors.setdefault(inc, make_redactor()))
        if item["value"] in clean.model_dump_json():
            leaks.append((inc, item["line_id"], item["start"]))
    return leaks


def test_no_injected_item_survives_the_tool_to_redaction_path():
    """Anything in tests/redaction_known_misses.json is a documented miss; a new leak fails here.

    The full path (agent act node -> LLM client prompt) is tested again in M6.
    """
    new_leaks = [leak for leak in _leaks(Redactor) if leak not in KNOWN_MISSES]
    assert not new_leaks, f"new leaks: {new_leaks[:5]}"


def test_the_leak_regression_test_can_actually_fail():
    assert len(_leaks(_NoOpRedactor)) > 500


def test_overall_recall_on_injected_set_stays_above_the_floor():
    assert evaluate()["recall"]["overall"]["rate"] >= 0.97

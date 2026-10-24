import json

import pytest
from pydantic import BaseModel

from incidentiq.config import load_config
from incidentiq.llm import (
    CacheMiss,
    LiveLLM,
    LLMOutputError,
    MockLLM,
    QuotaExhausted,
    ReplayLLM,
    ResponseCache,
    get_llm,
)
from incidentiq.llm.base import Generation, extract_json
from incidentiq.llm.cache import cache_key
from incidentiq.llm.live import RateLimited
from incidentiq.redaction import Redactor


class Verdict(BaseModel):
    category: str
    confidence: int


def _user(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


# --- cache keys ---------------------------------------------------------------------------


def test_cache_key_is_stable_and_sensitive_to_every_input():
    base = cache_key("m1", _user("hello"), None)
    assert base == cache_key("m1", _user("hello"), None)
    assert len({base, cache_key("m2", _user("hello"), None), cache_key("m1", _user("hello!"), None),
                cache_key("m1", _user("hello"), "Verdict")}) == 4


# --- replay -------------------------------------------------------------------------------


def test_replay_serves_a_recorded_reply(tmp_path):
    cache = ResponseCache(tmp_path)
    messages = _user("what failed?")
    cache.put(cache_key("m", messages, None), "m", messages, None, Generation("the disk", 10, 3, 0.5))
    llm = ReplayLLM("m", cache)
    assert llm.complete(messages) == "the disk"
    assert (llm.stats.prompt_tokens, llm.stats.completion_tokens) == (10, 3)


def test_replay_miss_tells_the_user_how_to_record(tmp_path):
    with pytest.raises(CacheMiss, match="INCIDENTIQ_LLM=live"):
        ReplayLLM("m", ResponseCache(tmp_path)).complete(_user("never recorded"))


def test_replay_is_the_default_mode(monkeypatch):
    monkeypatch.delenv("INCIDENTIQ_LLM", raising=False)
    assert load_config().llm_mode == "replay"
    assert isinstance(get_llm(), ReplayLLM)


# --- live ---------------------------------------------------------------------------------


class FakeTransport:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def __call__(self, messages, json_mode):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return Generation(reply, 5, 2, 0.1)


def _live(tmp_path, transport, **kwargs):
    sleeps: list[float] = []
    llm = LiveLLM("m", transport, ResponseCache(tmp_path), sleep=sleeps.append,
                  clock=lambda: 0.0, **kwargs)
    return llm, sleeps


def test_live_records_the_reply_and_replay_reproduces_it(tmp_path):
    llm, _ = _live(tmp_path, FakeTransport("disk full"))
    assert llm.complete(_user("what failed?")) == "disk full"
    assert ReplayLLM("m", ResponseCache(tmp_path)).complete(_user("what failed?")) == "disk full"


def test_live_answers_from_the_cache_without_calling_the_api(tmp_path):
    transport = FakeTransport("once")
    llm, _ = _live(tmp_path, transport)
    llm.complete(_user("q"))
    llm.complete(_user("q"))
    assert transport.calls == 1


def test_live_spaces_calls_to_stay_under_the_rate_limit(tmp_path):
    llm, sleeps = _live(tmp_path, FakeTransport("a", "b"), min_interval_s=4.0)
    llm.complete(_user("first"))
    llm.complete(_user("second"))
    assert sleeps == [4.0]  # the clock never advances, so the second call waits a full interval


def test_live_backs_off_on_rate_limits_then_succeeds(tmp_path):
    llm, sleeps = _live(tmp_path, FakeTransport(RateLimited("slow down"), RateLimited("again"), "ok"),
                        min_interval_s=0)
    assert llm.complete(_user("q")) == "ok"
    assert sleeps == [10, 20]


def test_live_stops_cleanly_when_the_daily_quota_is_gone(tmp_path):
    llm, _ = _live(tmp_path, FakeTransport(RateLimited("quota PerDay", daily=True)))
    with pytest.raises(QuotaExhausted, match="Rerun tomorrow"):
        llm.complete(_user("q"))


def test_live_gives_up_after_too_many_rate_limits(tmp_path):
    llm, _ = _live(tmp_path, FakeTransport(*[RateLimited("x")] * 3), max_retries=2, min_interval_s=0)
    with pytest.raises(QuotaExhausted):
        llm.complete(_user("q"))


def test_live_without_an_api_key_fails_with_a_clear_message(monkeypatch):
    monkeypatch.setenv("INCIDENTIQ_LLM", "live")
    monkeypatch.setenv("LLM_API_KEY", "")
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        get_llm()


# --- structured output --------------------------------------------------------------------


def test_structured_reply_is_parsed_into_the_model():
    llm = MockLLM(default='{"category": "disk_full", "confidence": 3}')
    result = llm.complete(_user("diagnose"), response_schema=Verdict)
    assert result == Verdict(category="disk_full", confidence=3)


def test_markdown_fences_around_json_are_tolerated():
    assert json.loads(extract_json('Sure!\n```json\n{"a": 1}\n```')) == {"a": 1}


def test_invalid_reply_is_retried_with_the_validation_error_appended():
    llm = MockLLM(rules=[("diagnose", [
        '{"category": "disk_full"}', '{"category": "disk_full", "confidence": 2}'])])
    result = llm.complete(_user("diagnose"), response_schema=Verdict)
    assert result.confidence == 2 and llm.stats.retries == 1
    retry_prompt = llm.sent[1]
    assert retry_prompt[-2]["role"] == "assistant"
    assert "confidence" in retry_prompt[-1]["content"] and "Field required" in retry_prompt[-1]["content"]


def test_non_json_reply_is_retried():
    llm = MockLLM(rules=[("diagnose", ["I think it is the disk.",
                                       '{"category": "x", "confidence": 1}'])])
    assert llm.complete(_user("diagnose"), response_schema=Verdict).category == "x"
    assert "not valid JSON" in llm.sent[1][-1]["content"]


def test_gives_up_after_the_retry_budget():
    llm = MockLLM(default='{"category": 5}')
    with pytest.raises(LLMOutputError, match="3 attempts"):
        llm.complete(_user("diagnose"), response_schema=Verdict)
    assert llm.stats.calls == 3


def test_retries_are_recorded_so_replay_reproduces_them(tmp_path):
    bad_then_good = FakeTransport('{"category": "x"}', '{"category": "x", "confidence": 1}')
    llm, _ = _live(tmp_path, bad_then_good, min_interval_s=0)
    expected = llm.complete(_user("diagnose"), response_schema=Verdict)
    assert ReplayLLM("m", ResponseCache(tmp_path)).complete(
        _user("diagnose"), response_schema=Verdict) == expected


# --- mock ---------------------------------------------------------------------------------


def test_mock_picks_the_first_matching_rule():
    llm = MockLLM(rules=[("plan", "PLAN"), ("report", "REPORT")], default="?")
    assert llm.complete(_user("make a plan")) == "PLAN"
    assert llm.complete(_user("write the report")) == "REPORT"
    assert llm.complete(_user("hello")) == "?"


# --- the redaction guard ------------------------------------------------------------------


def test_nothing_sensitive_reaches_the_model_or_the_cache(tmp_path):
    transport = FakeTransport("Contact sam@example.org about it")
    llm, _ = _live(tmp_path, transport, min_interval_s=0)
    out = llm.complete([
        {"role": "system", "content": "You are an on-call assistant."},
        {"role": "user", "content": "Login failed for priya@example.com with "
                                    "api_key=iq_sk_abcdefghijklmnop12345678"}])
    sent = json.dumps(llm.sent)
    assert "priya@example.com" not in sent and "iq_sk_abcdefghijklmnop12345678" not in sent
    assert "[EMAIL_1]" in sent and "[SECRET_1]" in sent
    assert "sam@example.org" not in out  # replies are redacted too
    cached = "".join(p.read_text(encoding="utf-8") for p in tmp_path.rglob("*.json"))
    assert "sam@example.org" not in cached and "priya@example.com" not in cached


def test_a_shared_redactor_keeps_placeholders_consistent_with_earlier_text():
    shared = Redactor()
    clean_observation, _ = shared.redact("login failed for sam@example.org")
    llm = MockLLM(redactor=shared)
    llm.complete(_user(f"{clean_observation}. Also lee@example.org failed."))
    assert "[EMAIL_2]" in llm.sent[0][0]["content"] and "[EMAIL_1]" in llm.sent[0][0]["content"]


def test_start_incident_resets_placeholder_numbering():
    llm = MockLLM()
    llm.complete(_user("a@b.org"))
    llm.start_incident()
    llm.complete(_user("c@d.org"))
    assert llm.sent[1][0]["content"] == "[EMAIL_1]"

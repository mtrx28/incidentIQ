"""The base prompts are frozen.

Recorded model answers are keyed by a hash of the prompt text. If a base prompt changes, every
recording that used it becomes unreachable and replay mode fails with a cache miss. A deliberate
change (for example a new benchmark stage) must go through the `tuned` switch instead, or the
recordings must be redone and these hashes updated on purpose.
"""

import hashlib
import json

from incidentiq import data
from incidentiq.agents.baseline import baseline_messages
from incidentiq.agents.prompts import observer_messages, planner_messages, reporter_messages
from incidentiq.schemas import Evidence, GraphState, Observation


def _state() -> GraphState:
    s = GraphState(incident=data.load_incident("INC-001"))
    s.observations.append(Observation(
        step=1, tool="log_search", args={"service": "auth"}, reason="r", summary="1 line",
        evidence=[Evidence(evidence_id="L-0001", kind="log", excerpt="x")]))
    s.validation_errors = ["problem one"]
    return s


def _hash(messages) -> str:
    return hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()[:16]


def test_base_prompts_have_not_changed():
    s = _state()
    assert _hash(planner_messages(s, ["auth"], ["cpu_pct"])) == "a619dccdde17c127"
    assert _hash(observer_messages(s, 1)) == "ebb937b58811b12f"
    assert _hash(reporter_messages(s)) == "059ef6b58091f49b"
    assert _hash(baseline_messages(s, s.observations[0].evidence)) == "c7ff840511ac23ed"
    # v0b (scale100 condition) is a sibling prompt; the v0a hash above must stay as it was.
    assert _hash(baseline_messages(s, s.observations[0].evidence, filtered=True)) == \
        "0c6836d829de1006"


def test_the_tuned_switch_adds_the_v4_rules_and_only_then():
    s = _state()
    plain = planner_messages(s, ["auth"], ["cpu_pct"])[0]["content"]
    tuned = planner_messages(s, ["auth"], ["cpu_pct"], tuned=True)[0]["content"]
    assert tuned.startswith(plain) and "Do not restrict log searches" in tuned
    assert "Do not restrict" not in plain
    assert "downstream_timeout needs evidence" in reporter_messages(s, tuned=True)[0]["content"]
    assert "downstream_timeout needs evidence" not in reporter_messages(s)[0]["content"]


def test_tuned_switch_leaves_the_base_prompt_alone_when_it_has_no_extra_rules(monkeypatch):
    from incidentiq.agents import prompts

    s = _state()
    monkeypatch.setattr(prompts, "TUNED_PLANNER_RULES", "")
    assert planner_messages(s, ["auth"], ["cpu_pct"], tuned=True) == \
        planner_messages(s, ["auth"], ["cpu_pct"])


def test_v4_prompts_and_the_v5_addendum_are_pinned():
    from incidentiq.agents.prompts import TUNED_V5_PLANNER_ADDENDUM

    s = _state()
    assert _hash(planner_messages(s, ["auth"], ["cpu_pct"], tuned=True)) == "d372cad214c8d63a"
    assert _hash(reporter_messages(s, tuned=True)) == "ad7e7562cbf2e313"
    # v5 = the v4 system prompt plus the addendum, and nothing else changes.
    v4 = planner_messages(s, ["auth"], ["cpu_pct"], tuned=True)
    v5 = planner_messages(s, ["auth"], ["cpu_pct"], tuned=True, v5=True)
    assert v5[0]["content"] == f"{v4[0]['content']}\n\n{TUNED_V5_PLANNER_ADDENDUM}"
    assert v5[1] == v4[1]
    assert _hash(v5) == "b21caa19efcc4f66"
    assert hashlib.sha256(TUNED_V5_PLANNER_ADDENDUM.encode()).hexdigest()[:16] == "05a3a787e3ac3a36"

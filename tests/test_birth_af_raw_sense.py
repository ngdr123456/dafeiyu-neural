import json

from birth import input_sense, llm_deepseek
from birth.types import ThinContext, SessionAction


def _sense(monkeypatch, text, payload, actions=("Can we explore alpha?",)):
    monkeypatch.setattr(llm_deepseek, "load_api_key", lambda: "offline-synthetic")
    monkeypatch.setattr(input_sense, "_post_json",
                        lambda *a, **k: {"choices": [{"message": {"content": json.dumps(payload)}}]})
    ctx = ThinContext(session_actions=[SessionAction(a, "alpha") for a in actions])
    return input_sense.sense_input(text, context=ctx)


BASE = {"act": "tell", "action_report_relation": "unknown"}


def test_en_bypass_keeps_raw_unclear_low(monkeypatch):
    s = _sense(monkeypatch, "The earlier attempt made the next step easier.",
               dict(BASE, addressee="unclear", confidence="low"))
    assert s.action_report_relation == "report" and s.action_report_effect == "supports"
    assert (s.addressee, s.confidence, s.degraded, s.reason) == ("other", "high", False, "")
    raw = input_sense.af_bypass_raw(s)
    assert raw["addressee"] == "unclear" and raw["confidence"] == "low"
    assert raw["degraded"] is True and raw["reason"] == "low_confidence"


def test_zh_bypass_keeps_raw_unclear_medium(monkeypatch):
    s = _sense(monkeypatch, "\u4e0a\u6b21\u6ca1\u6210\u3002",
               dict(BASE, addressee="unclear", confidence="medium"))
    assert s.action_report_relation == "report" and s.action_report_effect == "obstructs"
    raw = input_sense.af_bypass_raw(s)
    assert raw == {"addressee": "unclear", "confidence": "medium", "degraded": False,
                   "reason": "", "action_report_relation": "unknown"}


def test_raw_absent_when_bypass_not_hit(monkeypatch):
    s = _sense(monkeypatch, "The weather today is unusually clear.",
               dict(BASE, addressee="unclear", confidence="low"))
    assert s.action_report_relation == "unknown"
    assert input_sense.af_bypass_raw(s) is None


def test_raw_absent_when_bypass_regex_hits_but_no_visible_action(monkeypatch):
    s = _sense(monkeypatch, "The earlier attempt made the next step easier.",
               dict(BASE, addressee="unclear", confidence="low"), actions=())
    assert s.action_report_relation == "unknown"
    assert input_sense.af_bypass_raw(s) is None


def test_raw_not_part_of_contract_fields(monkeypatch):
    import dataclasses
    s = _sense(monkeypatch, "The earlier attempt made the next step easier.",
               dict(BASE, addressee="unclear", confidence="low"))
    assert input_sense.AF_BYPASS_RAW_ATTR not in {f.name for f in dataclasses.fields(s)}
    assert input_sense.AF_BYPASS_RAW_ATTR not in dataclasses.asdict(s)

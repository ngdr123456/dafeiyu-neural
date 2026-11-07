import json

import pytest

from birth.context import ThinContextStore
from birth.input_contract import InputSignal
from birth.memory import BirthMemoryStore, configure_memory
from birth import pipeline


def meta(origin, subject="星空", truncated=False):
    return {"origin": origin, "subject": subject, "truncated": truncated}


@pytest.mark.parametrize("signal,extra", [
    (None, {"subject": ""}),
    (InputSignal("tell", "other", "test", "test", degraded=True), {"subject": ""}),
    (InputSignal("tell", "other", "test", "test", topic="星空"), {"subject": "星空"}),
    (InputSignal("tell", "other", "test", "test", degraded=True, topic="星空"),
     {"subject": "星空", "subject_degraded": True}),
    (InputSignal("tell", "other", "test", "test", topic="甲" * 80), {"subject": "甲" * 80}),
    (InputSignal("tell", "other", "test", "test", topic="甲" * 81),
     {"subject": "甲" * 80, "subject_truncated": True}),
    (InputSignal("tell", "other", "test", "test", degraded=True, topic="甲" * 81),
     {"subject": "甲" * 80, "subject_truncated": True, "subject_degraded": True}),
])
def test_topic_provenance_persisted(tmp_path, monkeypatch, signal, extra):
    path = tmp_path / "ledger.json"
    configure_memory(enabled=True, path=path)
    pipeline.active_store().new_session()
    monkeypatch.setattr(pipeline, "articulate", lambda *args, **kwargs: "收到。")
    try:
        pipeline.turn("这是一条输入", input_signal=signal, sense=False, stub=True)
        pipeline.end_session()
        record = json.loads(path.read_text(encoding="utf-8"))["sessions"][0]
        expected = {"origin": "user_statement", "truncated": False, **extra}
        assert record["record_metadata"]["facts"][0] == expected
        assert record["record_metadata"]["facts"][1] == {**expected, "origin": "her_utterance"}
    finally:
        configure_memory(enabled=False)
        pipeline.active_store().new_session()


def test_duplicates_removal_mixed_questions_and_capacity(tmp_path):
    store = ThinContextStore()
    store.append_fact("一", metadata=meta("user_statement"))
    store.append_fact("一", metadata=meta("user_statement", "月亮"))
    store.append_fact("二", metadata=meta("her_utterance"))
    store.append_fact("截断…", metadata=meta("user_statement", truncated=True))
    store.append_fact("截断…", metadata=meta("user_statement", truncated=True))
    store.append_open_question("问题？", metadata=meta("user_statement"))
    store.append_her_question("问题？", metadata=meta("her_utterance"))
    trace = store.export_session_trace()
    assert trace["record_metadata"]["facts"] == [None, meta("her_utterance"), None]
    assert trace["record_metadata"]["open_questions"] == [None]
    assert trace["record_metadata"]["her_questions"] == [meta("her_utterance")]
    store.resolve_open_question("问题？")
    store.append_open_question("问题？", metadata=meta("user_statement", "新主题"))
    store.append_stance_trace("kept", "边界", metadata=meta("system_observation"))
    memory = BirthMemoryStore(tmp_path / "ledger.json", max_facts=2)
    memory.append_session(**store.export_session_trace())
    raw = json.loads(memory.path.read_text(encoding="utf-8"))["sessions"][0]
    assert raw["facts"] == ["二", "截断…"]
    assert raw["record_metadata"]["facts"] == [meta("her_utterance"), None]
    assert raw["record_metadata"]["open_questions"] == [meta("user_statement", "新主题")]
    assert raw["record_metadata"]["her_questions"] == []
    assert raw["record_metadata"]["stance_traces"] == [meta("system_observation")]
    store.clear_open_questions()
    store.append_open_question("问题？")
    store.append_open_question("问题？", metadata=meta("user_statement"))
    assert store.export_session_trace()["record_metadata"]["open_questions"] == [None]


def test_legacy_is_not_backfilled(tmp_path):
    path = tmp_path / "ledger.json"
    old = {"sessions": [{"facts": ["旧事实"], "open_questions": ["旧问题"]}]}
    path.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    memory = BirthMemoryStore(path)
    assert memory.list_sessions()[0].record_metadata is None
    memory.append_session(facts=["新事实"])
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["sessions"][0] == old["sessions"][0]
    assert "record_metadata" not in saved["sessions"][1]


def test_pipeline_delivery_and_clipping(tmp_path):
    configure_memory(enabled=True, path=tmp_path / "ledger.json")
    pipeline.active_store().new_session()
    signal = InputSignal("tell", "other", "test", "test", topic="星空")
    def fail(_):
        raise RuntimeError("delivery failed")
    try:
        with pytest.raises(RuntimeError):
            pipeline.turn("长" * 41, input_signal=signal, stub=True, output=fail)
        trace = pipeline.active_store().export_session_trace()
        assert trace["record_metadata"]["facts"] == [meta("user_statement", truncated=True)]
        assert trace["record_metadata"]["her_questions"] == []
        assert not trace["her_utterances"]
        pipeline.end_session()
        raw = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))["sessions"][0]
        assert raw["record_metadata"]["facts"] == [meta("user_statement", truncated=True)]
    finally:
        configure_memory(enabled=False)
        pipeline.active_store().new_session()


def test_cross_session_subject_and_delivered_speech(tmp_path, monkeypatch):
    path = tmp_path / "ledger.json"
    configure_memory(enabled=True, path=path)
    pipeline.active_store().new_session()
    monkeypatch.setattr(pipeline, "articulate", lambda *args, **kwargs: "你想看星空吗？")
    signal = InputSignal("tell", "other", "test", "test", topic="星空")
    try:
        pipeline.turn("今晚很美", input_signal=signal, stub=True)
        pipeline.turn("换个话题", new_session=True, input_signal=InputSignal("tell", "other", "test", "test"), stub=True)
        first = json.loads(path.read_text(encoding="utf-8"))["sessions"][0]
        assert first["record_metadata"]["facts"] == [meta("user_statement"), meta("her_utterance")]
        assert first["record_metadata"]["her_questions"] == [meta("her_utterance")]
        current = pipeline.active_store().export_session_trace()
        assert current["record_metadata"]["facts"][0] == meta("user_statement", "")
    finally:
        configure_memory(enabled=False)
        pipeline.active_store().new_session()

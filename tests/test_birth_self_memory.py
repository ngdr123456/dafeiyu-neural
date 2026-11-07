"""Voice ledger delivery, isolation, capacity, and persistence without a model."""

from dataclasses import asdict

import pytest

from birth import pipeline
from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode, take_reject_feedback
from birth.context import ThinContextStore
from birth.memory import BirthMemoryStore, configure_memory
from birth.pipeline import active_store, end_session, turn
from birth.types import HerUtterance


@pytest.fixture(autouse=True)
def clean_state():
    configure_memory(enabled=False)
    active_store().new_session()
    clear_llm_hook()
    set_stub_mode(True)
    take_reject_feedback()
    yield
    configure_memory(enabled=False)
    active_store().new_session()
    clear_llm_hook()
    set_stub_mode(True)
    take_reject_feedback()


def test_stub_turn_records_concrete_context_and_keeps_facts():
    result = turn("你好", new_session=True, stub=True)
    entries = active_store().export_session_trace()["her_utterances"]
    assert entries == [{
        "text": result.utterance, "drive_direction": "hold",
        "stance_posture": "yieldable", "org_grain": "simple", "source": "stub", "complete": True,
    }]
    assert result.brief.drive.direction == "hold"
    assert result.brief.stance.posture == "yieldable"
    assert result.brief.org.grain == "simple"
    assert result.articulate_source == "stub"
    assert "台上说：" + result.utterance in active_store().snapshot().facts_this_session
    assert not hasattr(active_store().snapshot(), "her_utterances")
    assert not hasattr(result.brief.context, "her_utterances")


def test_missing_drive_on_brief_is_recorded_as_empty(monkeypatch):
    original = pipeline.arbitrate

    def without_drive(*args, **kwargs):
        brief = original(*args, **kwargs)
        brief.drive = None
        return brief

    monkeypatch.setattr(pipeline, "arbitrate", without_drive)
    result = turn("你好", new_session=True, stub=True)
    entry, = active_store().export_session_trace()["her_utterances"]
    assert result.brief.drive is None
    assert entry == {"text": result.utterance, "drive_direction": "",
                     "stance_posture": "yieldable", "org_grain": "simple", "source": "stub", "complete": True}


def test_rejected_drafts_record_only_delivered_fallback():
    calls = []
    disaster = "我小时候住在海边，我答应晚点再聊月亮。"

    def hook(brief):
        calls.append(brief)
        return disaster

    set_llm_hook(hook)
    result = turn("你好", new_session=True, stub=False)
    entry, = active_store().export_session_trace()["her_utterances"]
    assert len(calls) == 2
    assert active_store().context.articulate_reject_count > 0
    assert result.articulate_source == "stub_fallback"
    assert entry["text"] == result.utterance != disaster
    assert entry["source"] == "stub_fallback"


def test_export_roundtrip_and_prior_isolation(tmp_path):
    result = turn("你好", new_session=True, stub=True)
    trace = active_store().export_session_trace()
    store = BirthMemoryStore(tmp_path / "memory.json")
    record = store.append_session(**trace)
    assert [asdict(e) for e in record.her_utterances] == trace["her_utterances"]
    assert store.list_sessions()[-1].her_utterances == record.her_utterances
    assert store.list_sessions()[-1].her_utterances[0].text == result.utterance
    assert not hasattr(store.latest_prior(), "her_utterances")


def test_session_end_and_new_session_persist_and_isolate(tmp_path):
    memory = configure_memory(enabled=True, path=tmp_path / "memory.json")
    first = turn("你好", stub=True)
    first_trace = active_store().export_session_trace()["her_utterances"]
    turn("你好", new_session=True, stub=True)
    assert [asdict(e) for e in memory.list_sessions()[-1].her_utterances] == first_trace
    assert first_trace[0]["text"] == first.utterance
    assert len(active_store().export_session_trace()["her_utterances"]) == 1
    assert not hasattr(active_store().snapshot().prior_session, "her_utterances")
    assert end_session()
    assert len(memory.list_sessions()) == 2


def test_voice_only_session_is_persisted(tmp_path):
    memory = configure_memory(enabled=True, path=tmp_path / "memory.json")
    entry = HerUtterance("独立记录", "", "yieldable", "simple", "stub")
    active_store().append_her_utterance(entry)
    assert end_session()
    assert memory.list_sessions()[-1].her_utterances == [entry]


def test_duplicates_and_capacity_in_memory_and_session(tmp_path):
    entry = HerUtterance("重复", "hold", "yieldable", "simple", "stub")
    context = ThinContextStore()
    for _ in range(201):
        context.append_her_utterance(entry)
    assert context.has_session_content()
    entries = context.export_session_trace()["her_utterances"]
    assert len(entries) == 200 and entries == [asdict(entry)] * 200
    last = HerUtterance("最后", "pursue", "yieldable", "rule", "hook")
    context.append_her_utterance(last)
    entries = context.export_session_trace()["her_utterances"]
    assert entries == [asdict(entry)] * 199 + [asdict(last)]
    memory = BirthMemoryStore(tmp_path / "memory.json", max_utterances=3)
    record = memory.append_session(her_utterances=entries)
    assert record.her_utterances == [entry, entry, last]
    assert memory.list_sessions()[-1].her_utterances == [entry, entry, last]
    context.new_session()
    assert context.export_session_trace()["her_utterances"] == []
    assert not context.has_session_content()
    zero = BirthMemoryStore(tmp_path / "zero.json", max_utterances=0)
    assert zero.append_session(her_utterances=entries) is None


def test_delivery_failure_and_empty_output_do_not_enter_ledger(monkeypatch):
    def fail_output(_result):
        raise RuntimeError("delivery failed")

    with pytest.raises(RuntimeError, match="delivery failed"):
        turn("你好", stub=True, output=fail_output)
    assert active_store().export_session_trace()["her_utterances"] == []
    monkeypatch.setattr(pipeline, "articulate", lambda *_args, **_kwargs: "   ")
    turn("你好", new_session=True, stub=True)
    assert active_store().export_session_trace()["her_utterances"] == []


def test_delivered_long_text_is_complete_but_fact_is_clipped(monkeypatch):
    monkeypatch.setattr(pipeline, "articulate", lambda *_args, **_kwargs: "字" * 45)
    result = turn("你好", new_session=True, stub=True)
    entry, = active_store().export_session_trace()["her_utterances"]
    assert result.utterance == "字" * 45
    assert entry["text"] == "字" * 45
    assert "台上说：" + "字" * 40 + "…" in active_store().snapshot().facts_this_session

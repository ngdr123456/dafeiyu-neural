"""Pause must keep the same session; only /new ends it into thin memory."""

from __future__ import annotations

from birth.context import ThinContextStore
from birth.types import ActionFeedback, SessionAction, StanceTrace
from birth import memory as memory_mod
from birth import pipeline
from birth.session_resume import open_session_path


def _reset_store():
    pipeline._STORE = ThinContextStore()


def test_snapshot_roundtrip_keeps_actions_and_feedback(tmp_path):
    memory_mod.configure_memory(enabled=True, path=tmp_path / "birth_memory.json")
    _reset_store()
    store = pipeline.active_store()
    store.context.session_actions.append(SessionAction(text="记得，你说事情堆着。", goal=""))
    store.context.action_feedback.append(
        ActionFeedback(
            action="记得，你说事情堆着。",
            action_order=0,
            evidence="上次的尝试对下一步有帮助",
            span="上次的尝试对下一步有帮助",
            scope="single_action",
            effect="supports",
            relation="supports",
        )
    )
    store.context.facts_this_session.append("用户说：最近有点累")
    store.append_session_turn("上次的尝试对下一步有帮助。", "记得，你说事情堆着。")
    store._record_metadata["stance_traces"][("kept", "同场")] = {"origin": "test"}
    store.context.stance_traces.append(StanceTrace(kind="kept", point="同场", why="试"))
    assert pipeline.checkpoint_open_session() is True
    path = open_session_path()
    assert path is not None and path.is_file()

    _reset_store()
    assert pipeline.active_store().context.session_actions == []
    assert pipeline.resume_open_session() is True
    restored = pipeline.active_store()
    assert restored.context.session_actions == [
        SessionAction(text="记得，你说事情堆着。", goal="")
    ]
    assert restored.context.action_feedback[0].effect == "supports"
    assert restored.context.facts_this_session == ["用户说：最近有点累"]
    assert restored.session_turns() == [
        {"user_text": "上次的尝试对下一步有帮助。", "utterance": "记得，你说事情堆着。"}
    ]
    assert restored._record_metadata["stance_traces"][("kept", "同场")]["origin"] == "test"


def test_pause_does_not_append_thin_memory(tmp_path):
    ledger = tmp_path / "birth_memory.json"
    memory_mod.configure_memory(enabled=True, path=ledger)
    _reset_store()
    pipeline.turn("你好，今天想做饭。", new_session=True, stub=True, sense=False)
    assert pipeline.pause_session() is True
    assert pipeline.active_store().context.session_actions
    if ledger.exists():
        text = ledger.read_text(encoding="utf-8").strip()
        assert text in ("", "[]", '{"sessions": []}')
    assert "action_feedback" not in (ledger.read_text(encoding="utf-8") if ledger.exists() else "")
    assert open_session_path().is_file()


def test_resume_after_new_process(tmp_path):
    memory_mod.configure_memory(enabled=True, path=tmp_path / "birth_memory.json")
    _reset_store()
    pipeline.turn("最近有点累，事情堆着。", new_session=True, stub=True, sense=False)
    pipeline.turn("上次的尝试对下一步有帮助。", stub=True, sense=False)
    store = pipeline.active_store()
    store.context.action_feedback.append(
        ActionFeedback(
            action=store.context.session_actions[-1].text,
            action_order=len(store.context.session_actions) - 1,
            evidence="上次的尝试对下一步有帮助",
            span="上次的尝试对下一步有帮助",
            scope="single_action",
            effect="supports",
            relation="supports",
        )
    )
    pipeline.pause_session()
    actions_before = list(store.context.session_actions)
    turns_before = store.session_turns()
    assert len(turns_before) == 2

    _reset_store()
    assert pipeline.active_store().context.session_actions == []
    assert pipeline.resume_open_session() is True
    restored = pipeline.active_store()
    assert restored.context.session_actions == actions_before
    assert restored.context.action_feedback[0].effect == "supports"
    assert restored.session_turns() == turns_before

    pipeline.turn("嗯。", stub=True, sense=False)
    assert len(restored.session_turns()) == 3


def test_new_session_ends_and_clears_snapshot(tmp_path):
    ledger = tmp_path / "birth_memory.json"
    memory_mod.configure_memory(enabled=True, path=ledger)
    _reset_store()
    pipeline.turn("今天想做饭。", new_session=True, stub=True, sense=False)
    assert open_session_path().is_file()
    pipeline._persist_and_reset_session()
    assert not open_session_path().is_file()
    raw = ledger.read_text(encoding="utf-8")
    assert "做饭" in raw
    assert "action_feedback" not in raw
    _reset_store()
    assert pipeline.resume_open_session() is False
    assert pipeline.active_store().context.session_actions == []


def test_disabled_memory_writes_no_snapshot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    memory_mod.configure_memory(enabled=False, path=tmp_path / "birth_memory.json")
    _reset_store()
    pipeline.turn("你好", new_session=True, stub=True, sense=False)
    assert pipeline.checkpoint_open_session() is False
    assert list(tmp_path.glob("*session*")) == []
    assert not (tmp_path / "birth_session_open.json").exists()

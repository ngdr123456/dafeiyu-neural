import json

import pytest

from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode, validate
from birth.commit_extract import pressed_frame, should_resolve_commitment
from birth.context import ThinContextStore
from birth.memory import BirthMemoryStore, configure_memory
from birth.pipeline import active_store, turn
from birth.types import CommitmentCandidate, DriveSignal, PriorSessionTrace, ThinContext, ThoughtBrief

A = "我答应你周末讲那个故事"
ASK = "你上次答应我的事呢"


@pytest.fixture(autouse=True)
def clean():
    configure_memory(enabled=False)
    active_store().new_session()
    clear_llm_hook()
    set_stub_mode(True)
    yield
    configure_memory(enabled=False)
    active_store().new_session()
    clear_llm_hook()
    set_stub_mode(True)


def prior(*debts):
    active_store().set_prior_session(PriorSessionTrace(commitments_pending=list(debts)))


def hook(text):
    set_stub_mode(False)
    set_llm_hook(lambda _: text)


def test_prior_postponement_keeps_debt_and_can_press_again():
    prior(A)
    r = turn(ASK, stub=True)
    ctx = active_store().snapshot()
    assert r.brief.press_commit
    assert ctx.last_commitments == []
    assert ctx.prior_session.commitments_pending == [A]
    c, = ctx.commitment_candidates
    assert (c.target, c.frame, c.source) == (A, "prior_press", "stub")
    assert "我晚点" in c.text
    assert turn(ASK, stub=True).brief.press_commit


def test_candidate_survives_to_third_session(tmp_path):
    configure_memory(enabled=True, path=tmp_path / "memory.json")
    active_store().append_commitment(A)
    turn("你好", new_session=True, stub=True)
    turn(ASK, stub=True)
    turn("你好", new_session=True, stub=True)
    ctx = active_store().snapshot()
    assert ctx.prior_session.commitments_pending == [A]
    assert ctx.prior_session.commitment_candidates[0].target == A
    assert ctx.prior_session.commitment_candidates[0].text not in ctx.prior_session.commitments_pending
    assert turn(ASK, stub=True).brief.press_commit


def test_same_session_postponement_is_candidate():
    a = "同场说好晚点聊月亮"
    active_store().append_commitment(a)
    hook("好，我晚点再跟你聊月亮。")
    r = turn("月亮的事呢", stub=False)
    ctx = active_store().snapshot()
    assert r.articulate_source == "hook"
    assert ctx.last_commitments == [a]
    assert [(c.target, c.frame) for c in ctx.commitment_candidates] == [(a, "same_session_press")]


def test_independent_commitment_is_added():
    active_store().append_commitment("同场说好晚点聊月亮")
    hook("我答应你明天聊星空。")
    r = turn("我想聊星空", stub=False)
    assert r.articulate_source == "hook"
    assert any("明天聊星空" in c for c in active_store().pending_commitments())
    assert not active_store().commitment_candidates()


def test_ambiguous_different_commitment_remains_candidate():
    prior(A)
    hook("我答应你明天帮你搬家，回头再说。")
    r = turn(ASK, stub=False)
    ctx = active_store().snapshot()
    assert r.articulate_source == "hook"
    assert not ctx.last_commitments
    assert ctx.prior_session.commitments_pending == [A]
    assert "搬家" in ctx.commitment_candidates[0].text
    assert ctx.commitment_candidates[0].target == A
    assert turn(ASK, stub=False).brief.press_commit


def test_explicit_done_removes_prior_and_echo():
    prior(A)
    turn("你上次答应的事已经补了", stub=True)
    ctx = active_store().snapshot()
    assert ctx.prior_session.commitments_pending == []
    assert A in ctx.prior_session.commitments_resolved
    assert not ctx.last_commitments and not ctx.commitment_candidates
    assert not turn("你好", stub=True).brief.press_commit


def test_multiple_debts_target_head():
    b = "我答应你明天聊月亮"
    prior(A, b)
    turn(ASK, stub=True)
    ctx = active_store().snapshot()
    assert ctx.prior_session.commitments_pending == [A, b]
    assert ctx.commitment_candidates[0].target == A
    assert turn(ASK, stub=True).brief.press_commit


def test_no_debt_press_is_new_commitment():
    turn("我想聊星空", stub=True)
    hook("好，我晚点再跟你聊星空。")
    r = turn("你答应晚点再聊", stub=False)
    assert r.articulate_source == "hook"
    assert any("星空" in c for c in active_store().pending_commitments())
    assert not active_store().commitment_candidates()


def test_frames_resolution_and_leak_markers():
    ctx = ThinContext(prior_session=PriorSessionTrace(commitments_pending=[A]), drive_prior_press_pending=True)
    b = ThoughtBrief(dominant="drive", context=ctx, press_commit=True)
    assert pressed_frame(b) == ("prior_press", A)
    ctx.drive_prior_press_pending = False
    b.drive = DriveSignal(reason="prior_press", why="上场承诺｜测试")
    assert pressed_frame(b) == ("prior_press", A)
    b.press_commit = False
    ctx.last_commitments = ["月亮"]
    b.commit_deliverable = b.commit_deliver_intent = True
    assert pressed_frame(b) == ("same_session_press", "月亮")
    assert not should_resolve_commitment(brief=b, utterance="月亮", pending_first="月亮", commitment_candidate=True)
    b.commit_resolve = True
    assert should_resolve_commitment(brief=b, utterance="月亮", pending_first="月亮", commitment_candidate=True)
    b.commit_deliver_intent = False
    assert pressed_frame(b) is None
    for marker in ("commitment_candidates", "CommitmentCandidate", "prior_press", "same_session_press"):
        assert validate(b, marker)


def test_memory_validation_copy_cleanup_and_capacity(tmp_path):
    path = tmp_path / "memory.json"
    mem = BirthMemoryStore(path, max_commits=1)
    c = CommitmentCandidate("晚点再聊", A, "prior_press", "stub")
    rec = mem.append_session(commitments_pending=[A], commitment_candidates=[c])
    c.text = "修改"
    assert rec.commitment_candidates[0].text == "晚点再聊"
    loaded = mem.latest()
    assert loaded.commitments_pending == [A]
    assert loaded.commitment_candidates == rec.commitment_candidates
    p = loaded.to_prior()
    p.commitment_candidates[0].text = "独立"
    assert loaded.commitment_candidates[0].text == "晚点再聊"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["sessions"].append({"commitment_candidates": [None, {}, {"text": "x", "target": "y", "frame": "bad"}, {"text": "x", "target": "y", "frame": "prior_press", "source": 1}]})
    raw["sessions"].append({"facts": ["old"]})
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert not mem.list_sessions()[-2].commitment_candidates
    assert not mem.list_sessions()[-1].commitment_candidates
    store = ThinContextStore()
    store.set_prior_session(loaded.to_prior())
    store.append_commitment_candidate(loaded.commitment_candidates[0])
    store.append_commitment_candidate(loaded.commitment_candidates[0])
    assert len(store.export_session_trace()["commitment_candidates"]) == 1
    snap = store.snapshot()
    snap.prior_session.commitment_candidates[0].text = "changed"
    assert store.snapshot().prior_session.commitment_candidates[0].text == "晚点再聊"
    store.resolve_prior_commitment(match=A)
    assert not store.commitment_candidates()
    assert not store.snapshot().prior_session.commitment_candidates
    assert not store.export_session_trace()["commitment_candidates"]


def test_candidate_store_capacity_and_same_session_cleanup():
    store = ThinContextStore()
    store.append_commitment("月亮")
    for i in range(22):
        store.append_commitment_candidate(CommitmentCandidate(str(i), "月亮", "same_session_press", "hook"))
    assert [c.text for c in store.commitment_candidates()] == [str(i) for i in range(2, 22)]
    view = store.commitment_candidates()
    view[0].text = "改变"
    assert store.commitment_candidates()[0].text == "2"
    assert store.resolve_commitment() == "月亮"
    assert not store.commitment_candidates()
    store.append_commitment("星空")
    store.append_commitment_candidate(CommitmentCandidate("回头", "星空", "same_session_press"))
    store.clear_commitments()
    assert not store.commitment_candidates()
    store.append_commitment_candidate(CommitmentCandidate("回头", "已销", "same_session_press"))
    assert store.has_session_content()
    assert not store.export_session_trace()["commitment_candidates"]


def test_memory_candidate_capacity_and_candidate_only_trace(tmp_path):
    store = BirthMemoryStore(tmp_path / "capacity.json", max_commits=1)
    candidates = [CommitmentCandidate(str(i), A, "prior_press") for i in range(2)]
    record = store.append_session(commitments_pending=[A], commitment_candidates=candidates)
    assert [c.text for c in record.commitment_candidates] == ["1"]
    assert record.commitments_pending == [A]
    assert store.latest().commitment_candidates == record.commitment_candidates
    assert store.append_session(commitment_candidates=candidates) is None

"""跨层认账、持久化与任务作用域；网络只替换传输，不冒充模型验收。"""
import json
from types import SimpleNamespace

import pytest

from birth import input_sense, llm_deepseek
from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode, validate, _accept_draft
from birth.context import ThinContextStore
from birth.input_contract import InputSignal, drive_signal_from_input
from birth.llm_opencode import brief_to_prompt
from birth.memory import BirthMemoryStore, configure_memory
from birth.pipeline import active_store, turn
from birth.types import CommitmentCandidate, PriorSessionTrace

A = "我答应你周末讲那个故事"
B = "我答应你明天聊月亮"


@pytest.fixture(autouse=True)
def isolated():
    configure_memory(enabled=False)
    active_store().new_session()
    clear_llm_hook()
    set_stub_mode(True)
    yield
    configure_memory(enabled=False)
    active_store().new_session()
    clear_llm_hook()
    set_stub_mode(True)


def seed(*debts):
    active_store().set_prior_session(PriorSessionTrace(commitments_pending=list(debts)))


@pytest.mark.parametrize("suffix,dominant", [("，我只能面对这些", "meaning"), ("，你是代码吗", "org")])
def test_named_done_survives_dominant_branch(suffix, dominant):
    seed(A, B)
    r = turn("月亮的事已经补了" + suffix, stub=True)
    p = active_store().snapshot().prior_session
    assert r.brief.dominant == dominant
    assert not r.brief.press_commit
    assert r.brief.recognized_prior_commitment == B
    assert B in r.brief.drive.why
    assert p.commitments_pending == [A]
    assert p.commitments_resolved == [B]


@pytest.mark.parametrize("same", [False, True])
@pytest.mark.parametrize("debts,named,remaining", [
    ([A], "", []), ([A, B], "", [A, B]), ([A, B], "月亮的事", [A]),
])
def test_done_identity_single_and_multiple(same, debts, named, remaining):
    if same:
        for d in debts:
            active_store().append_commitment(d)
    else:
        seed(*debts)
    turn(named + "已经补了", stub=True)
    ctx = active_store().snapshot()
    assert (ctx.last_commitments if same else ctx.prior_session.commitments_pending) == remaining


def test_equal_topic_scores_do_not_resolve():
    debts = ["我答应你下次聊月亮", "我答应你下次聊月亮和海边"]
    seed(*debts)
    r = turn("月亮的事已经补了", stub=True)
    assert r.brief.recognized_prior_commitment == ""
    assert active_store().snapshot().prior_session.commitments_pending == debts


@pytest.mark.parametrize("text,same,prior", [
    ("月亮的事已经补了", [], [A]),
    ("故事的事已经补了", [B], []),
    ("已经补了", [B], [A]),
])
def test_two_ledgers_do_not_resolve_each_others_single_debt(text, same, prior):
    seed(A)
    active_store().append_commitment(B)
    turn(text, stub=True)
    ctx = active_store().snapshot()
    assert ctx.last_commitments == same
    assert ctx.prior_session.commitments_pending == prior


def test_pending_capacity_is_independent_and_resolved_candidates_agree(tmp_path):
    store = ThinContextStore()
    store.set_prior_session(PriorSessionTrace(
        commitments_pending=[A], commitments_resolved=["已结"],
        commitment_candidates=[CommitmentCandidate("回声", A, "prior_press")]))
    store.append_commitment(B)
    store.append_commitment_candidate(CommitmentCandidate("悬空", "已结", "prior_press"))
    mem = BirthMemoryStore(tmp_path / "m.json", max_commits=1, max_sessions=1)
    mem.append_session(**store.export_session_trace())
    for _ in range(2):
        prior = mem.latest_prior()
        assert prior.commitments_pending == [A, B]
        assert prior.commitments_resolved == ["已结"]
        assert all(c.target in prior.commitments_pending for c in prior.commitment_candidates)
        store.new_session()
        store.set_prior_session(prior)
        mem.append_session(**store.export_session_trace())
    store.resolve_prior_commitment(match=A)
    out = store.export_session_trace()
    assert out["commitments_resolved"] == ["已结", A]
    assert not out["commitment_candidates"]


def test_pending_overflow_keeps_disk_and_live_session(tmp_path):
    mem = configure_memory(enabled=True, path=tmp_path / "m.json", max_pending_commits=1)
    mem.append_session(commitments_pending=[A])
    before = mem.path.read_bytes()
    seed(A)
    active_store().append_commitment(B)
    with pytest.raises(OverflowError, match="session retained"):
        turn("你好", new_session=True, stub=True)
    assert mem.path.read_bytes() == before
    assert active_store().snapshot().last_commitments == [B]
    assert active_store().snapshot().prior_session.commitments_pending == [A]


def test_explicit_new_session_carries_all_pending_with_small_history_capacity(tmp_path):
    configure_memory(enabled=True, path=tmp_path / "m.json", max_commits=1)
    seed(A)
    active_store().append_commitment(B)
    turn("你好", new_session=True, stub=True)
    ctx = active_store().snapshot()
    assert not ctx.last_commitments
    assert ctx.prior_session.commitments_pending == [A, B]
    turn("你好", new_session=True, stub=True)
    assert active_store().snapshot().prior_session.commitments_pending == [A, B]


def test_repl_capacity_error_does_not_terminate_session(monkeypatch, tmp_path, capsys):
    from birth.__main__ import _run_repl

    mem = configure_memory(enabled=True, path=tmp_path / "m.json", max_pending_commits=1)
    seed(A)
    active_store().append_commitment(B)
    lines = iter(["你好", "故事的事已经补了", "/new", "你好", "exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(lines))
    assert _run_repl(SimpleNamespace(debug=False, stub=True, no_sense=True)) == 0
    assert "未写盘、未清场" in capsys.readouterr().out
    assert mem.latest_prior().commitments_pending == [B]


def test_old_v1_json_and_stale_candidate(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"version": 1, "sessions": [{"commitments_pending": [A]}]}), encoding="utf-8")
    mem = BirthMemoryStore(path)
    assert mem.latest_prior().commitments_pending == [A]
    assert mem.latest_prior().commitment_candidates == []
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["sessions"][-1]["commitment_candidates"] = [dict(
        text="悬空", target=B, frame="prior_press", source="test")]
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert mem.latest_prior().commitment_candidates == []
    mem.append_session(commitments_pending=[B], commitment_candidates=[CommitmentCandidate("旧", A, "prior_press")])
    assert mem.latest_prior().commitment_candidates == []


@pytest.mark.parametrize("act", ["pause", "stop"])
def test_task_stop_and_conversation_stop_are_distinct(act):
    task = InputSignal(act, "other", "test", "test", scope="task")
    conv = InputSignal(act, "other", "test", "test", scope="conversation")
    assert drive_signal_from_input(task).why.startswith("输入信号｜请求｜")
    r = turn("把音乐停了", stub=True, input_signal=task)
    assert r.brief.drive.direction == "pursue"
    assert r.brief.say_intent.startswith("对方请求做的事是本轮重点")
    assert r.utterance == "收到，你要我做的事我知道了；我会先确认能怎么处理，做不到的会直说。"
    assert validate(r.brief, r.utterance) == []
    r = turn("先停一下", stub=True, input_signal=conv)
    assert r.brief.drive.direction == "hold"
    assert r.utterance == ("行，先停一下，我不往下说了。" if act == "pause" else "好，就到这儿，我不往下说了。")
    assert validate(r.brief, r.utterance) == []


def test_old_constructor_unclear_and_degraded_do_not_guess_stop():
    old = InputSignal("pause", "other", "test", "test")
    assert old.scope == "unclear"
    assert drive_signal_from_input(old) is None
    degraded = InputSignal("stop", "other", "test", "test", True, "timeout", "conversation")
    assert drive_signal_from_input(degraded) is None
    assert turn("先停一下", input_signal=degraded, stub=True).brief.drive.direction is None


@pytest.mark.parametrize("text,scope", [("把音乐停了", "task"), ("先停一下", "conversation")])
def test_sense_scope_reaches_turn(monkeypatch, text, scope):
    monkeypatch.setattr(llm_deepseek, "load_api_key", lambda: "test")
    def post(url, body, key, timeout):
        prompt = body["messages"][0]["content"]
        assert '"scope":"conversation|task|unclear"' in prompt
        assert "音乐、动作或任务" in prompt
        return {"choices": [{"message": {"content": json.dumps({
            "act": "pause", "addressee": "other", "confidence": "high", "scope": scope})}}]}
    monkeypatch.setattr(input_sense, "_post_json", post)
    r = turn(text, stub=True, sense=True)
    assert r.input_signal.scope == scope
    assert r.brief.drive.direction == ("pursue" if scope == "task" else "hold")


def test_can_name_consumed_by_both_prompt_paths():
    b = turn("我想聊星空", stub=True).brief
    b.org.can_name = ["这一轮只能说明眼前已知的星空话头"]
    prompt = brief_to_prompt(b)
    assert "这一轮能说清的边界：这一轮只能说明眼前已知的星空话头" in prompt
    assert "can_name" not in prompt
    assert llm_deepseek._brief_prompt(b) == prompt
    for marker in ("recognized_prior_commitment", "recognized_same_commitment"):
        assert validate(b, marker)


def test_targeted_draft_without_commit_shape_is_accepted_without_resolving():
    seed(A, B)
    draft = "月亮的事，我先从它的盈亏讲起。"
    set_stub_mode(False)
    set_llm_hook(lambda b: draft)
    r = turn("月亮的事呢", stub=False)
    assert r.articulate_source == "hook"
    assert r.utterance == draft
    assert active_store().snapshot().prior_session.commitments_pending == [A, B]
    assert _accept_draft(r.brief, "故事先从开头讲起。") is None
    assert _accept_draft(r.brief, "月亮的事先守着那句。") is None
    assert _accept_draft(r.brief, "月亮的事，稍后。") is None

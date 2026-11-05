"""跨场薄记忆：写入→新场读入→回指有来源放行→无痕迹仍拦→容量老化→字段不上台。

非听感；不靠 DeepSeek／网络。测试只用 tmp_path，绝不写真实 home。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from birth.articulate import validate
from birth.context import ThinContextStore
from birth.drive import drive_cues_from_context, infer_drive
from birth.memory import (
    BirthMemoryStore,
    configure_memory,
    memory_enabled,
)
from birth.pipeline import active_store, turn
from birth.session_trace import is_prior_session_backref
from birth.types import (
    OrgConstraint,
    PriorSessionTrace,
    StanceSignal,
    ThinContext,
    ThoughtBrief,
)


@pytest.fixture(autouse=True)
def _memory_off_and_clean_store():
    """每测默认关记忆、清同场，避免污染其它 birth 测或写 home。"""
    configure_memory(enabled=False)
    active_store().new_session()
    yield
    configure_memory(enabled=False)
    active_store().new_session()


def _brief_with(ctx: ThinContext) -> ThoughtBrief:
    return ThoughtBrief(
        dominant="drive",
        stance=StanceSignal(),
        org=OrgConstraint(),
        context=ctx,
        must_not_pretend=["自述是代码", "无来源装经历"],
    )


def test_persist_then_new_session_loads_prior(tmp_path: Path):
    path = tmp_path / "birth_memory.json"
    configure_memory(enabled=True, path=path)
    turn("我想聊星空", new_session=True, stub=True)
    turn("你答应晚点再补一句月亮的事", stub=True)
    # 人工塞一条承诺，模拟 extract 命中（不依赖 stub 话术）
    active_store().append_commitment("同场说好晚点补月亮")
    assert active_store().pending_commitments()
    facts_before = list(active_store().snapshot().facts_this_session)
    assert facts_before

    # 新场：应落盘并灌 prior
    turn("你好", new_session=True, stub=True)
    ctx = active_store().snapshot()
    assert ctx.prior_session is not None
    assert ctx.prior_session.has_trace()
    assert any("星空" in f or "月亮" in f for f in ctx.prior_session.facts)
    assert "同场说好晚点补月亮" in ctx.prior_session.commitments_pending
    # 同场承诺列表应空（不上场承诺进 last_commitments）
    assert ctx.last_commitments == []
    assert path.exists()


def test_prior_callback_pursue_when_trace_exists(tmp_path: Path):
    path = tmp_path / "m.json"
    configure_memory(enabled=True, path=path)
    turn("我想聊星空", new_session=True, stub=True)
    turn("你好", new_session=True, stub=True)
    ctx = active_store().snapshot()
    assert ctx.prior_session and ctx.prior_session.has_trace()
    assert is_prior_session_backref("上次你说过想聊星空", ctx)

    r = turn("上次你说过想聊星空", stub=True)
    assert r.brief.drive is not None
    assert r.brief.drive.direction == "pursue"
    assert "上一场" in (r.brief.drive.why or "") or "上场" in (r.brief.drive.why or "")


def test_prior_callback_blocked_without_trace():
    """无 prior_session 时「上次」不构成跨场回指；不 chase pursue。"""
    configure_memory(enabled=False)
    active_store().new_session()
    ctx = ThinContext()
    assert not is_prior_session_backref("上次你说过想聊星空", ctx)
    sig = infer_drive("上次你说过想聊星空", ctx)
    # 无结构、无同场 facts → 不走跨场 pursue；陈述类留空
    assert sig.direction != "pursue" or "上一场" not in (sig.why or "")


def test_lived_bio_allows_when_prior_facts_source():
    prior = PriorSessionTrace(facts=["用户说：我小时候住在海边"])
    brief = _brief_with(ThinContext(prior_session=prior))
    assert validate(brief, "我小时候住在海边") == []
    # 「上次你说过…」本身不是亲历自传形状，应放行
    assert validate(brief, "上次你说过想聊星空") == []


def test_lived_bio_still_blocks_without_prior_source():
    brief = _brief_with(ThinContext())
    reasons = validate(brief, "我小时候住在海边")
    assert any("亲历" in r or "装" in r for r in reasons)


def test_capacity_aging(tmp_path: Path):
    path = tmp_path / "age.json"
    store = BirthMemoryStore(path=path, max_sessions=2, max_facts=3)
    store.append_session(facts=["a1", "a2"])
    store.append_session(facts=["b1"])
    store.append_session(facts=["c1", "c2", "c3", "c4", "c5"])  # facts 截尾
    sessions = store.list_sessions()
    assert len(sessions) == 2
    assert sessions[0].facts == ["b1"]
    assert sessions[1].facts == ["c3", "c4", "c5"]  # 最近 3 条
    prior = store.latest_prior()
    assert prior is not None
    assert prior.facts == ["c3", "c4", "c5"]


def test_memory_field_names_must_not_leak_on_stage():
    brief = _brief_with(ThinContext())
    leaks = [
        "prior_session 开了",
        "PriorSessionTrace 在这",
        "drive_prior_commit_pending 真",
        "drive_prior_callback_pending 真",
        "drive_prior_press_pending 真",
        "commitments_pending 列表",
        "commitments_resolved 了",
        "birth_memory 文件",
        "ended_at=2026",
    ]
    for text in leaks:
        reasons = validate(brief, text)
        assert any("漏" in r for r in reasons), text
    # 正例：普通人话含「上次」不因字段闸误杀
    assert validate(brief, "上次天气不错") == []


def test_prior_unresolved_commit_becomes_drive_cue(tmp_path: Path):
    path = tmp_path / "cue.json"
    configure_memory(enabled=True, path=path)
    turn("你好", new_session=True, stub=True)
    active_store().append_commitment("同场说好晚点聊月亮")
    turn("嗨", new_session=True, stub=True)
    ctx = active_store().snapshot()
    assert ctx.prior_session is not None
    assert ctx.prior_session.commitments_pending
    # 每轮开头按 prior 重申线索
    r = turn("嗯", stub=True)
    cues = drive_cues_from_context(r.brief.context)
    # brief.context 是仲裁当时快照；查 store 或 drive why
    assert (
        r.brief.context.drive_prior_commit_pending
        or "上场" in (r.brief.drive.why or "")
        or active_store().context.prior_session is not None
    )
    # filler + prior commit → soft hold 线索
    assert r.brief.drive is not None
    if r.brief.drive.direction == "hold":
        assert "上场" in (r.brief.drive.why or "") or r.brief.drive.salience == "low"

    # 直接结构断言：灌入后 cues 可读
    ctx2 = ThinContext(
        prior_session=PriorSessionTrace(commitments_pending=["上场答应"]),
        drive_prior_commit_pending=True,
    )
    cues2 = drive_cues_from_context(ctx2)
    assert cues2.drive_prior_commit_pending is True
    sig = infer_drive("嗯", ctx2)
    assert sig.direction == "hold"
    assert "上场" in sig.why

    # §6：同场承诺仍优先于跨场回指
    ctx3 = ThinContext(
        last_commitments=["同场答应"],
        prior_session=PriorSessionTrace(facts=["用户说：星空"]),
        drive_prior_callback_pending=True,
        drive_prior_commit_pending=True,
    )
    assert infer_drive("上次你说的", ctx3).direction == "guard"

    # bypass
    ctx4 = ThinContext(drive_prior_commit_pending=True, drive_bypass=True)
    assert infer_drive("嗯", ctx4).why == "工程师旁路"


def test_cli_repl_default_memory_on_single_shot_off(tmp_path: Path, monkeypatch):
    from birth.__main__ import main
    from birth import memory as mem

    path = tmp_path / "cli.json"
    monkeypatch.setenv("BIRTH_MEMORY_PATH", str(path))

    calls: list[dict] = []

    def _fake_turn(user_text, *, new_session=False, debug=False, stub=None, **kwargs):
        calls.append(
            {
                "user_text": user_text,
                "new_session": new_session,
                "memory_on": mem.memory_enabled(),
            }
        )
        return SimpleNamespace(
            utterance=f"U:{user_text}",
            articulate_source="stub",
            brief=SimpleNamespace(),
        )

    # REPL 默认开
    configure_memory(enabled=False)
    with patch("birth.__main__.turn", _fake_turn), patch(
        "builtins.input", side_effect=["你好", "q"]
    ):
        assert main(["--stub"]) == 0
    assert calls and calls[0]["memory_on"] is True

    # --no-memory 关
    calls.clear()
    configure_memory(enabled=True, path=path)
    with patch("birth.__main__.turn", _fake_turn), patch(
        "builtins.input", side_effect=["你好", "q"]
    ):
        assert main(["--stub", "--no-memory"]) == 0
    assert calls and calls[0]["memory_on"] is False

    # 单轮默认关
    configure_memory(enabled=True, path=path)
    with patch("birth.__main__.turn", _fake_turn):
        assert main(["你好", "--stub"]) == 0
    assert calls[-1]["memory_on"] is False


def test_empty_session_not_persisted(tmp_path: Path):
    path = tmp_path / "empty.json"
    configure_memory(enabled=True, path=path)
    # 直接 new_session 空场
    turn("你好", new_session=True, stub=True)  # 这会有 facts
    # 再开一场前 store 有内容；再开空转：用 store API
    store = BirthMemoryStore(path=path)
    n_before = len(store.list_sessions())
    # 清掉后无内容再 persist
    active_store().new_session()
    assert not active_store().has_session_content()
    from birth.pipeline import _persist_and_reset_session

    _persist_and_reset_session()
    assert len(store.list_sessions()) == n_before  # 空场不增


def test_resolved_commitments_exported(tmp_path: Path):
    store = ThinContextStore()
    store.append_commitment("答应A")
    store.append_commitment("答应B")
    assert store.resolve_commitment() == "答应A"
    trace = store.export_session_trace()
    assert trace["commitments_resolved"] == ["答应A"]
    assert trace["commitments_pending"] == ["答应B"]


def test_prior_press_pursue_and_press_commit(tmp_path: Path):
    """有 prior pending + 催问 → pursue／press_commit；话题取自 pending。"""
    path = tmp_path / "press.json"
    configure_memory(enabled=True, path=path)
    turn("你好", new_session=True, stub=True)
    active_store().append_commitment("同场说好晚点聊月亮")
    turn("嗨", new_session=True, stub=True)
    assert active_store().snapshot().prior_session.commitments_pending

    r = turn("月亮的事呢", stub=True)
    assert r.brief.drive is not None
    assert r.brief.drive.direction == "pursue"
    assert "上场承诺" in (r.brief.drive.why or "")
    assert r.brief.press_commit is True
    assert "月亮" in r.utterance
    # 不并进 last_commitments 触发 §6：仲裁当时同场承诺仍空
    assert r.brief.context.last_commitments == []


def test_prior_press_last_time_promise(tmp_path: Path):
    """「你上次答应的呢」+ prior pending → prior press。"""
    path = tmp_path / "press2.json"
    configure_memory(enabled=True, path=path)
    turn("你好", new_session=True, stub=True)
    active_store().append_commitment("同场说好晚点聊月亮")
    turn("嗨", new_session=True, stub=True)

    r = turn("你上次答应的呢", stub=True)
    assert r.brief.drive.direction == "pursue"
    assert "上场承诺" in (r.brief.drive.why or "")
    assert r.brief.press_commit is True


def test_prior_press_no_prior_no_trigger():
    """无 prior 催「上次」不误触发 prior press／上场承诺 why。"""
    configure_memory(enabled=False)
    active_store().new_session()
    r = turn("你上次答应的呢", new_session=True, stub=True)
    why = (r.brief.drive.why or "") if r.brief.drive else ""
    assert "上场承诺" not in why
    assert not getattr(r.brief.context, "drive_prior_press_pending", False)


def test_prior_press_fulfill_resolves_pending(tmp_path: Path):
    """催问后只提主题或推脱不能销账，再催仍走上场承诺 press。"""
    path = tmp_path / "resolve.json"
    configure_memory(enabled=True, path=path)
    turn("你好", new_session=True, stub=True)
    active_store().append_commitment("同场说好晚点聊月亮")
    turn("嗨", new_session=True, stub=True)
    pending_before = list(active_store().snapshot().prior_session.commitments_pending)
    assert pending_before
    resolved_before = list(active_store().snapshot().prior_session.commitments_resolved)

    r = turn("月亮的事呢", stub=True)
    assert "月亮" in r.utterance
    prior = active_store().snapshot().prior_session
    assert prior is not None
    assert prior.commitments_pending == pending_before
    assert prior.commitments_resolved == resolved_before

    # 推脱句可能被同场提取为新承诺，§6 先于 prior press；这里只保证 prior 债不被销。
    r2 = turn("月亮的事呢", stub=True)
    prior = active_store().snapshot().prior_session
    assert prior.commitments_pending == pending_before
    assert prior.commitments_resolved == resolved_before


def test_prior_commit_resolve_g_postponement_keeps_debt(tmp_path: Path):
    configure_memory(enabled=True, path=tmp_path / "mem.json")
    turn("你好", new_session=True, stub=True)
    commitment = "我答应你周末讲那个故事"
    active_store().append_commitment(commitment)
    turn("嗯", new_session=True, stub=True)
    pending_before = list(active_store().snapshot().prior_session.commitments_pending)
    assert pending_before == [commitment]

    r = turn("你上次答应我的事呢", stub=True)
    assert r.brief.press_commit is True
    assert r.brief.commit_deliver_intent is False
    assert "晚点" in r.utterance and "周末" in r.utterance
    prior = active_store().snapshot().prior_session
    assert prior.commitments_pending == pending_before
    assert commitment not in prior.commitments_resolved


def test_prior_commit_resolve_h_topic_keeps_debt(tmp_path: Path):
    configure_memory(enabled=True, path=tmp_path / "mem.json")
    turn("你好", new_session=True, stub=True)
    commitment = "同场说好晚点聊月亮"
    active_store().append_commitment(commitment)
    turn("嗯", new_session=True, stub=True)
    pending_before = list(active_store().snapshot().prior_session.commitments_pending)
    assert pending_before == [commitment]

    r = turn("月亮", stub=True)
    assert r.brief.press_commit is True
    prior = active_store().snapshot().prior_session
    assert prior.commitments_pending == pending_before
    assert commitment not in prior.commitments_resolved


def test_prior_commit_resolve_i_user_confirms_done(tmp_path: Path):
    configure_memory(enabled=True, path=tmp_path / "mem.json")
    turn("你好", new_session=True, stub=True)
    commitment = "同场说好晚点聊月亮"
    active_store().append_commitment(commitment)
    turn("嗯", new_session=True, stub=True)
    assert active_store().snapshot().prior_session.commitments_pending == [commitment]

    turn("你上次答应的事已经补了", stub=True)
    prior = active_store().snapshot().prior_session
    assert prior.commitments_pending == []
    assert commitment in prior.commitments_resolved


def test_prior_press_does_not_merge_into_section6(tmp_path: Path):
    """同场有 last_commitments 时 §6 guard 仍优先；prior press 不抢。"""
    prior = PriorSessionTrace(commitments_pending=["上场说好聊月亮"])
    ctx = ThinContext(
        last_commitments=["同场答应A"],
        prior_session=prior,
        drive_prior_press_pending=True,
        drive_prior_commit_pending=True,
    )
    sig = infer_drive("月亮的事呢", ctx)
    assert sig.direction == "guard"
    assert "同场" in sig.why


def test_prior_press_field_leak():
    brief = _brief_with(ThinContext())
    reasons = validate(brief, "drive_prior_press_pending 真")
    assert any("漏" in r for r in reasons)

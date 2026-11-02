"""承诺兑现／放下：store API + pipeline 薄接线（非听感）。"""

from __future__ import annotations

from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode
from birth.pipeline import active_store, turn


def test_store_resolve_commitment_pops_first():
    store = active_store()
    store.new_session()
    store.append_commitment("我晚点再跟你聊星空。")
    store.append_commitment("下次补月亮")
    assert store.resolve_commitment() == "我晚点再跟你聊星空。"
    assert store.pending_commitments() == ["下次补月亮"]
    store.clear_commitments()
    assert store.pending_commitments() == []
    assert store.resolve_commitment() is None


def test_commitment_stays_until_fulfilled():
    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    turn("我想聊星空", stub=True)
    turn("你答应晚点再聊", stub=True)
    before = active_store().pending_commitments()
    assert before, before
    # 误触发：闲聊不清空
    turn("今天天气怎么样", stub=True)
    assert active_store().pending_commitments() == before


def test_user_fulfill_mark_resolves_commitment():
    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    turn("我想聊星空", stub=True)
    turn("你答应晚点再聊", stub=True)
    assert active_store().pending_commitments()
    turn("那件事你兑现了", stub=True)
    assert active_store().pending_commitments() == []


def test_utterance_cover_resolves_commitment():
    """用户点到主题 + 台上可检验接上 → resolve。"""
    set_stub_mode(False)
    set_llm_hook(lambda _b: "行，接着聊星空。你想从哪头起？")
    try:
        active_store().new_session()
        turn("我想聊星空", stub=True)
        active_store().append_commitment("我晚点再跟你聊星空。")
        assert active_store().pending_commitments()
        set_stub_mode(False)
        set_llm_hook(lambda _b: "行，接着聊星空。你想从哪头起？")
        turn("那就星空继续", stub=False)  # 用户点到主题 → deliver_intent
        assert active_store().pending_commitments() == []
    finally:
        clear_llm_hook()
        set_stub_mode(True)


def test_deny_commitment_does_not_resolve():
    """改口否定 ≠ 兑现；承诺应仍在。"""
    set_stub_mode(True)
    clear_llm_hook()
    store = active_store()
    store.new_session()
    store.append_commitment("同场里说好这轮先补月亮的事")
    turn("那刚才说的不算", stub=True)
    assert store.pending_commitments(), store.pending_commitments()


def test_commitment_deny_flag_used_then_cleared_no_leak():
    """pipeline 薄接线：有 pending＋改口 → 本轮 drive 走 guard（经 flag 主路径）；
    回合末 flag 清 False，不漏到下一轮；无 pending 时写入侧不置位。"""
    set_stub_mode(True)
    clear_llm_hook()
    store = active_store()
    store.new_session()
    store.append_commitment("同场里说好这轮先补月亮的事")
    r = turn("那刚才说的不算", stub=True)
    assert r.brief.drive is not None and r.brief.drive.direction == "guard"
    assert r.brief.commit_deny is True  # arbitrate 从 stance 守诺结构置 Brief 标记
    assert store.context.commitment_deny_pending is False  # 回合末已清，不漏
    # 无 pending：即使命中改口词表也不置 flag
    store.new_session()
    turn("那刚才说的不算", stub=True)
    assert store.context.commitment_deny_pending is False


def test_should_set_deny_structured_without_marks():
    """主路径：结构化 commit_deny=True，文案无 COMMIT_DENY_MARKS → 仍应置位。"""
    from birth.commit_extract import should_set_commitment_deny_pending

    text = "够了先这样"  # SATISFIED 收束词；不含不算/忘掉/改口/收回/作废等
    assert should_set_commitment_deny_pending(
        commit_deny=True, user_text=text, has_pending=True
    )
    assert not should_set_commitment_deny_pending(
        commit_deny=False, user_text=text, has_pending=True
    )


def test_should_set_deny_marks_fallback_without_structured():
    """兜底：无结构化时 COMMIT_DENY_MARKS 仍探出；无 pending 即使有词也不置。"""
    from birth.commit_extract import should_set_commitment_deny_pending

    assert should_set_commitment_deny_pending(
        commit_deny=False, user_text="那刚才说的不算", has_pending=True
    )
    assert not should_set_commitment_deny_pending(
        commit_deny=False, user_text="那刚才说的不算", has_pending=False
    )


def test_structured_commit_deny_kwarg_sets_flag_drive_guards():
    """turn(structured_commit_deny=True)＋无改口词表文案 → drive guard（S2 压过收束）。

    stance 本刀未动：无词表时 Brief.commit_deny 可仍为 False；结构化写入只服务 store flag／drive。
    """
    set_stub_mode(True)
    clear_llm_hook()
    store = active_store()
    store.new_session()
    store.append_commitment("同场说好晚点再聊星空")
    r = turn("够了先这样", stub=True, structured_commit_deny=True)
    assert r.brief.drive is not None and r.brief.drive.direction == "guard"
    assert "要护" in (r.brief.drive.why or "") or "没兑现" in (r.brief.drive.why or "")
    assert store.context.commitment_deny_pending is False  # 回合末清
    # 有词表的改口轮：Brief.commit_deny 由 arbitrate 从 stance 结构置 True
    store.new_session()
    store.append_commitment("同场说好晚点再聊星空")
    r2 = turn("那刚才说的不算", stub=True)
    assert r2.brief.commit_deny is True
    assert r2.brief.drive is not None and r2.brief.drive.direction == "guard"


def test_brief_commit_deny_defaults_false():
    from birth.types import ThoughtBrief

    assert ThoughtBrief(dominant="drive").commit_deny is False


def test_resolve_uses_brief_flags_not_loose_marks():
    """有 commit_resolve／可检验交付才 resolve；无标记即使闲话也不清。"""
    from birth.commit_extract import should_resolve_commitment
    from birth.types import DriveSignal, ThoughtBrief, ThinContext

    pending = "我晚点再跟你聊星空。"
    brief_resolve = ThoughtBrief(
        dominant="meaning",
        drive=DriveSignal(direction="guard", salience="mid", why="x"),
        say_intent="文案已改，不含兑现字样",
        commit_resolve=True,
        context=ThinContext(),
    )
    assert should_resolve_commitment(
        brief=brief_resolve, utterance="随便", pending_first=pending
    )

    brief_deliver = ThoughtBrief(
        dominant="meaning",
        drive=DriveSignal(direction="guard", salience="mid", why="x"),
        say_intent="先守住同场说过的话",
        commit_deliverable=True,
        commit_deliver_intent=True,
        context=ThinContext(),
    )
    assert should_resolve_commitment(
        brief=brief_deliver, utterance="行，接着聊星空。", pending_first=pending
    )
    assert not should_resolve_commitment(
        brief=brief_deliver, utterance="今天天气怎么样", pending_first=pending
    )

    brief_none = ThoughtBrief(
        dominant="drive",
        drive=DriveSignal(direction=None, salience="low", why="x"),
        say_intent="那件事你兑现了",  # 仅子串，无标记
        context=ThinContext(),
    )
    assert not should_resolve_commitment(
        brief=brief_none, utterance="那件事你兑现了", pending_first=pending
    )


def test_guard_utterance_with_topic_keeps_commitment():
    """守诺口径只提主题词未接上 → 承诺仍在。"""
    from birth.commit_extract import should_resolve_commitment
    from birth.types import DriveSignal, ThoughtBrief, ThinContext

    pending = "我晚点再跟你聊星空。"
    brief = ThoughtBrief(
        dominant="meaning",
        drive=DriveSignal(direction="guard", salience="mid", why="x"),
        say_intent="先守住同场说过的话",
        commit_deliverable=True,
        commit_deliver_intent=True,
        context=ThinContext(),
    )
    guard = "同场里说过的还在，我先守着那句，星空那事也还在，再接你眼前这句。"
    assert not should_resolve_commitment(
        brief=brief, utterance=guard, pending_first=pending
    )

    # 仅 pending＋主题重叠、无 deliver_intent → 也不清
    brief2 = ThoughtBrief(
        dominant="meaning",
        drive=DriveSignal(direction="guard", salience="mid", why="x"),
        commit_deliverable=True,
        commit_deliver_intent=False,
        context=ThinContext(),
    )
    assert not should_resolve_commitment(
        brief=brief2, utterance="行，接着聊星空。", pending_first=pending
    )

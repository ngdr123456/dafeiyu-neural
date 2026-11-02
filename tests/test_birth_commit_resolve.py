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

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
    """台上把 pending 可核对后续接上 → resolve。"""
    set_stub_mode(False)
    set_llm_hook(lambda _b: "行，接着聊星空。你想从哪头起？")
    try:
        active_store().new_session()
        turn("我想聊星空", stub=True)
        # seed commitment without going through press path
        active_store().append_commitment("我晚点再跟你聊星空。")
        assert active_store().pending_commitments()
        set_stub_mode(False)
        set_llm_hook(lambda _b: "行，接着聊星空。你想从哪头起？")
        turn("继续", stub=False)
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

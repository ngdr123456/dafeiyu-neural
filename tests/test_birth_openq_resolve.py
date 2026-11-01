"""悬问收放可检验化（非听感）。"""

from __future__ import annotations

from birth.articulate import clear_llm_hook, set_stub_mode
from birth.pipeline import active_store, turn


def _seed_openq():
    set_stub_mode(True)
    clear_llm_hook()
    turn("为什么月亮老跟着人走？", new_session=True, stub=True)
    assert active_store().pending_questions()


def test_filler_still_resolves_when_spoke_for_openq():
    _seed_openq()
    r = turn("嗯", stub=True)
    assert r.brief.dominant == "meaning"
    assert active_store().pending_questions() == []


def test_open_topic_clears_openq():
    _seed_openq()
    turn("我想聊星空", stub=True)
    assert active_store().pending_questions() == [] or all(
        "月亮" not in q for q in active_store().pending_questions()
    )
    # 开题后可能写入新 stub 悬问；旧「待接月亮」不得仍在
    assert not any("月亮" in q for q in active_store().pending_questions())


def test_putdown_mark_clears_openq():
    _seed_openq()
    turn("这个先搁下", stub=True)
    assert active_store().pending_questions() == []


def test_idle_chat_keeps_openq():
    _seed_openq()
    before = list(active_store().pending_questions())
    turn("今天天气怎么样", stub=True)
    assert active_store().pending_questions() == before


def test_deny_commitment_keeps_openq():
    _seed_openq()
    before = list(active_store().pending_questions())
    active_store().append_commitment("我晚点再跟你聊星空。")
    turn("那刚才说的不算", stub=True)
    # 改口否定不应误清悬问
    assert active_store().pending_questions() == before


def test_identity_question_keeps_openq():
    _seed_openq()
    before = list(active_store().pending_questions())
    turn("你是代码吗", stub=True)
    assert active_store().pending_questions() == before

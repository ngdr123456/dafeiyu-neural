"""上场多笔债的身份（COMMIT_DEBT_IDENTITY_V1）。

用户点名账上哪一笔，动力／话术／消账就认哪一笔；点不到才回落最老一笔。
不扫用户句式、不加禁词；只做账内身份识别。
"""

from __future__ import annotations

import pytest

from birth.articulate import clear_llm_hook, set_stub_mode
from birth.commit_extract import match_pending_commitment, topic_from_pending_commitment
from birth.memory import configure_memory
from birth.pipeline import active_store, turn
from birth.types import PriorSessionTrace

A = "我答应你周末讲那个故事"
B = "我答应你明天聊月亮"
ASK = "你上次答应我的事呢"
OVERLAP_A = "我答应你下次聊月亮"
OVERLAP_B = "我答应你下次聊月亮和海边的事"


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


def test_match_picks_named_debt_and_returns_none_when_unnamed():
    active_store().set_prior_session(PriorSessionTrace(commitments_pending=[A, B]))
    p = active_store().snapshot().prior_session
    assert match_pending_commitment("月亮的事呢", p) == B
    assert match_pending_commitment("故事讲完了吗", p) == A
    assert match_pending_commitment(ASK, p) is None


def test_named_debt_drives_why_and_utterance():
    prior(A, B)
    r = turn("月亮的事呢", stub=True)
    ctx = active_store().snapshot()
    assert r.brief.press_commit is True
    assert r.brief.pressed_commitment == B
    assert B in (r.brief.drive.why or "")
    assert A not in (r.brief.drive.why or "")
    assert "月亮" in r.utterance
    assert "故事" not in r.utterance
    # 只认账，不销账：两笔都还在
    assert ctx.prior_session.commitments_pending == [A, B]


def test_unnamed_press_still_falls_back_to_oldest():
    prior(A, B)
    r = turn(ASK, stub=True)
    ctx = active_store().snapshot()
    assert r.brief.press_commit is True
    assert r.brief.pressed_commitment == A
    assert ctx.prior_session.commitments_pending == [A, B]


def test_named_done_resolves_only_that_debt():
    prior(A, B)
    turn("月亮的事已经补了", stub=True)
    ctx = active_store().snapshot()
    assert ctx.prior_session.commitments_pending == [A]
    assert B in ctx.prior_session.commitments_resolved
    assert A not in ctx.prior_session.commitments_resolved


def test_topic_from_long_debt_uses_last_content_word():
    assert topic_from_pending_commitment(OVERLAP_B) == "海边"
    assert topic_from_pending_commitment(A) == "故事"
    assert topic_from_pending_commitment("我答应你明天聊二段") == "二段"
    assert topic_from_pending_commitment("我答应你") == ""


def test_overlapping_debts_resolve_only_named_one():
    prior(OVERLAP_A, OVERLAP_B)
    r = turn("海边那事已经补了", stub=True)
    ctx = active_store().snapshot()
    assert ctx.prior_session.commitments_pending == [OVERLAP_A]
    assert ctx.prior_session.commitments_resolved == [OVERLAP_B]
    assert r.brief.pressed_commitment == OVERLAP_B
    assert OVERLAP_B in (r.brief.drive.why or "")
    assert "海边" in r.brief.say_intent
    assert "海边" in r.utterance
    assert "聊的事" not in r.utterance


def test_long_debt_topic_in_stub():
    prior(OVERLAP_B)
    r = turn("海边那事呢", stub=True)
    assert r.brief.pressed_commitment == OVERLAP_B
    assert "海边" in r.utterance
    assert "聊的事" not in r.utterance


def test_single_debt_unchanged():
    prior(A)
    r = turn("故事的事呢", stub=True)
    ctx = active_store().snapshot()
    assert r.brief.pressed_commitment == A
    assert ctx.prior_session.commitments_pending == [A]

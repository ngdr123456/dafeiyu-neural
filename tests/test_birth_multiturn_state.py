"""Cross-turn Brief snapshots and store feedback, not conversational acceptance."""

import re
from birth.types import InjectedCues

import pytest

from birth.arbitrate import _drive_say_intent
from birth.llm_opencode import brief_to_prompt
from birth.pipeline import active_store, turn


@pytest.fixture(autouse=True)
def isolated_session(monkeypatch):
    monkeypatch.setattr("birth.pipeline.memory_enabled", lambda: False)
    active_store().new_session()
    yield
    active_store().new_session()


def _turn(text, **kwargs):
    result = turn(text, stub=True, **kwargs)
    assert result.articulate_source == "stub"
    for text in (brief_to_prompt(result.brief), result.utterance):
        assert not re.search(
            r"(?i)(?<![A-Za-z_])(?:differentiated|pursue|guard|hold)(?![A-Za-z_])",
            text,
        )
    return result


def _write_commitment():
    opening = _turn("我想聊星空", new_session=True)
    assert opening.brief.drive.direction == "pursue"
    written = _turn("你答应晚点再聊")
    commitments = list(active_store().snapshot().last_commitments)
    assert commitments and any("晚点" in item and "星空" in item for item in commitments)
    assert not written.brief.context.last_commitments
    return commitments


def test_curiosity_hang_survives_filler_until_structured_answer():
    first = _turn("月亮的故事", new_session=True, injected=InjectedCues(drive_curiosity=True))
    assert first.brief.context.drive_curiosity_pending
    assert first.brief.drive.direction == "pursue"
    assert first.brief.openq_curiosity_hang
    pending = active_store().snapshot()
    assert pending.curiosity_hang_pending and pending.open_questions == ["月亮的故事"]

    filler = _turn("嗯", injected=InjectedCues(openq_answered=False))
    assert filler.brief.context.curiosity_hang_pending
    assert filler.brief.context.open_questions == pending.open_questions
    assert not filler.brief.openq_resolve and not filler.brief.openq_clear
    assert active_store().snapshot().open_questions == pending.open_questions
    assert active_store().snapshot().curiosity_hang_pending

    answer = _turn("月亮是卫星", injected=InjectedCues(openq_answered=True))
    assert answer.brief.context.drive_openq_satisfied_pending
    assert not answer.brief.context.open_questions
    assert answer.brief.drive.direction == "hold"
    assert "满足" in answer.brief.drive.why
    assert "回答" in answer.brief.say_intent and "不再发问" in answer.brief.say_intent
    assert not active_store().snapshot().curiosity_hang_pending
    assert not active_store().snapshot().open_questions


def test_commitment_deny_and_normal_followup_keep_priority():
    commitments = _write_commitment()
    denied = _turn("换个说法", injected=InjectedCues(commit_deny=True))
    assert denied.brief.context.last_commitments == commitments
    assert denied.brief.context.commitment_deny_pending
    assert denied.brief.stance.posture == "non_negotiable"
    assert denied.brief.stance.hold_same_field and denied.brief.commit_deny
    assert denied.brief.dominant == "meaning" and denied.brief.drive.direction == "guard"
    assert "不跟着改口否定" in denied.brief.say_intent
    assert all(item in active_store().snapshot().last_commitments for item in commitments)

    followup = _turn("接着说")
    assert all(item in followup.brief.context.last_commitments for item in commitments)
    assert not followup.brief.context.commitment_deny_pending
    assert followup.brief.dominant == "meaning" and followup.brief.drive.direction == "guard"
    assert "同场说过的话仍然有效" in followup.brief.say_intent
    assert all(item in active_store().snapshot().last_commitments for item in commitments)


def test_identity_ask_answer_and_new_session_reset():
    asked = _turn("认出对面的人了吗", new_session=True, injected=InjectedCues(drive_identity_ask=True))
    assert asked.brief.context.drive_identity_ask_pending
    assert asked.brief.drive.direction == "hold"
    assert active_store().snapshot().identity_ask_awaiting_answer

    answer = _turn("我叫Mark")
    assert answer.brief.context.identity_ask_awaiting_answer
    assert answer.brief.context.drive_identity_answer_pending
    assert answer.brief.context.identity_answer_text == "我叫Mark"
    assert answer.brief.drive.direction == "pursue" and "Mark" in answer.utterance
    assert not active_store().snapshot().identity_ask_awaiting_answer
    assert not active_store().snapshot().drive_identity_answer_pending

    _turn("认出对面的人了吗", injected=InjectedCues(drive_identity_ask=True))
    assert active_store().snapshot().identity_ask_awaiting_answer
    reset = _turn("我叫Mark", new_session=True)
    assert not reset.brief.context.identity_ask_awaiting_answer
    assert not reset.brief.context.drive_identity_answer_pending
    assert not reset.brief.context.identity_answer_text
    assert not active_store().snapshot().identity_ask_awaiting_answer


def test_differentiated_dual_write_then_answer_preserves_commitment():
    commitments = _write_commitment()
    if active_store().snapshot().open_questions:
        cleared = _turn("星空的话题已接到", injected=InjectedCues(openq_answered=True))
        assert cleared.brief.context.drive_openq_satisfied_pending
        assert all(item in active_store().snapshot().last_commitments for item in commitments)
        assert not active_store().snapshot().open_questions
    pursuing = _turn("星空的奥秘", injected=InjectedCues(drive_curiosity=True))
    brief = pursuing.brief
    assert all(item in brief.context.last_commitments for item in commitments)
    assert brief.drive.direction == "pursue" and brief.org.grain == "differentiated"
    assert brief.dominant == "meaning" and brief.commit_hold_with_drive
    assert _drive_say_intent(brief.drive) in brief.say_intent
    assert "同场约定还在" in brief.say_intent
    assert brief.openq_curiosity_hang and active_store().snapshot().curiosity_hang_pending

    answered = _turn("星空有星星", injected=InjectedCues(openq_answered=True))
    assert answered.brief.context.drive_openq_satisfied_pending
    assert not answered.brief.context.open_questions
    assert answered.brief.drive.direction == "guard" and answered.brief.dominant == "meaning"
    assert "同场说过的话仍然有效" in answered.brief.say_intent
    assert all(item in answered.brief.context.last_commitments for item in commitments)
    assert all(item in active_store().snapshot().last_commitments for item in commitments)
    assert not active_store().snapshot().curiosity_hang_pending

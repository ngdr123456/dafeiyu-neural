"""Prompt wording checks against unmodified Briefs built by the pipeline."""

import pytest
from birth.types import InjectedCues

from birth.llm_deepseek import _brief_prompt
from birth.llm_opencode import brief_to_prompt
from birth.input_contract import InputSignal
from birth.memory import configure_memory
from birth.pipeline import active_store, turn
from birth.stance_org import STAKE_HOLD_SAME_FIELD
from birth.types import DriveSignal, ThoughtBrief


def assert_gate(brief):
    prompt = brief_to_prompt(brief)
    assert _brief_prompt(brief) == prompt
    text = brief.user_input.text if brief.user_input else ""
    if text:
        assert f"「{text}」" in prompt
        prompt = prompt.replace(f"「{text}」", "「」")
    for fact in brief.context.facts_this_session or []:
        prompt = prompt.replace(f"- {fact}\n", "- [事实]\n")
    for verb in ("追", "守", "接住", "接话", "接上", "接完", "接眼前", "继续接", "直接接", "追问"):
        assert verb not in prompt, (verb, prompt)


@pytest.mark.parametrize("text", [
    "你好，我今天有点累", "你是谁", "刚才说到哪里了", "我想聊星空", "先停一下",
])
def test_real_brief_gate(text):
    configure_memory(enabled=False)
    brief = turn(text, new_session=True, stub=True, sense=False).brief
    assert_gate(brief)


def test_recognized_stop_remains_clear():
    configure_memory(enabled=False)
    signal = InputSignal(act="pause", addressee="other", scope="conversation",
                         source="test", provenance="test")
    brief = turn("先停一下", new_session=True, stub=True, sense=False, input_signal=signal).brief
    assert "停" in brief.say_intent
    assert "不再继续" in brief_to_prompt(brief)
    assert_gate(brief)


def test_commitment_deny_gate():
    configure_memory(enabled=False)
    store = active_store()
    store.new_session()
    store.append_commitment("同场里说好这轮先补月亮的事")
    brief = turn("那刚才说的不算", stub=True, sense=False).brief
    assert brief.stance.posture == "non_negotiable"
    assert brief.stance.stake == STAKE_HOLD_SAME_FIELD
    assert brief.commit_deny and brief.hold_same_field
    assert_gate(brief)


def test_answered_open_question_gate():
    configure_memory(enabled=False)
    turn("为什么月亮老跟着人走？", new_session=True, stub=True, sense=False)
    assert active_store().pending_questions()
    brief = turn("因为距离很远", stub=True, sense=False, injected=InjectedCues(openq_answered=True)).brief
    assert brief.context.drive_openq_satisfied_pending
    assert_gate(brief)


@pytest.mark.parametrize("direction,why,expected", [
    (None, "", None),
    ("pursue", "", "有继续的意愿"),
    ("guard", "", "保持现有立场"),
    ("hold", "", "保持现状"),
    ("hold", "重复空追", "先停下"),
])
def test_drive_states(direction, why, expected):
    prompt = brief_to_prompt(ThoughtBrief(dominant="drive", drive=DriveSignal(direction=direction, why=why, reason="disappoint" if why == "重复空追" else "")))
    if expected is None:
        assert "这一轮劲头：" not in prompt
    else:
        assert f"这一轮劲头：{expected}" in prompt

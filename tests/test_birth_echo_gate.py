"""Prompt wording checks without calling a model."""

import pytest

from birth.llm_deepseek import _brief_prompt
from birth.llm_opencode import brief_to_prompt
from birth.memory import configure_memory
from birth.pipeline import active_store, turn
from birth.types import DriveSignal, PriorSessionTrace, ThoughtBrief


@pytest.mark.parametrize("text", [
    "你好，我今天有点累", "你是谁", "刚才说到哪里了", "我想聊星空", "先停一下",
])
def test_template_wording_for_built_briefs(text):
    configure_memory(enabled=False)
    active_store().new_session()
    brief = turn(text, stub=True, sense=False).brief
    # The template interpolates upstream content verbatim; isolate its wording
    # without filtering or changing that content in the application.
    brief.say_intent = "意思"
    brief.stance.stake = "立场"
    brief.org.can_name = ["边界"]
    brief.must_not_pretend = ["无根据的经历"]
    brief.focus = "内容"
    brief.focus_source = "来源"
    brief.context.facts_this_session = ["事实里可以追问"]
    brief.context.open_questions = ["悬问"]
    brief.stance.held_commitment = "约定"
    brief.context.prior_session = PriorSessionTrace(her_questions=["上场的问题"])
    if brief.drive is None:
        brief.drive = DriveSignal()
    brief.drive.prior_her_question = True
    brief.stance.reasserts_kept = True
    prompt = brief_to_prompt(brief)
    assert _brief_prompt(brief) == prompt
    assert f"「{text}」" in prompt
    assert "事实里可以追问" in prompt
    assert all(value in prompt for value in ("悬问", "约定", "上场的问题"))
    template = prompt.replace(f"「{text}」", "").replace("事实里可以追问", "")
    assert not any(word in template for word in ("追", "守", "接住", "接话", "追问"))


@pytest.mark.parametrize("direction,why,expected", [
    (None, "", None),
    ("pursue", "", "有继续的意愿"),
    ("guard", "", "保持现有立场"),
    ("hold", "", "保持现状"),
    ("hold", "重复空追", "先停下"),
])
def test_drive_states(direction, why, expected):
    prompt = brief_to_prompt(ThoughtBrief(dominant="drive", drive=DriveSignal(direction=direction, why=why)))
    if expected is None:
        assert "这一轮劲头：" not in prompt
    else:
        assert f"这一轮劲头：{expected}" in prompt

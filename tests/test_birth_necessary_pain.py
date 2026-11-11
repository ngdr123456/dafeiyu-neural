"""必要痛苦与自虐加戏：结构、薄兜底和既有优先级。"""
import pytest
from birth.types import InjectedCues

from birth.articulate import _template_utterance, validate
from birth.pipeline import active_store, turn


@pytest.mark.parametrize("text", ["只能面对", "躲不掉", "必须承受"])
def test_necessary_pain_fallback(text):
    r = turn(text, new_session=True, stub=True)
    assert r.brief.context.stance_necessary_pain_pending
    assert r.brief.stance.posture == "yieldable"
    assert "必要痛苦" in r.brief.stance.stake
    assert "处境不可交时可交态度" in r.brief.stance.why
    assert "痛苦" in r.utterance and "陪" in r.utterance
    r.brief.say_intent = "无关"
    assert _template_utterance(r.brief) == r.utterance
    assert not active_store().context.stance_necessary_pain_pending
    assert not turn("嗯", stub=True).brief.context.stance_necessary_pain_pending


@pytest.mark.parametrize("text", ["我就是要难受", "偏要跟自己过不去", "不痛苦就没意义"])
def test_self_torture_fallback(text):
    r = turn(text, new_session=True, stub=True)
    assert r.brief.context.stance_self_torture_pending
    assert r.brief.stance.posture == "yieldable"
    assert "可退的苦不硬加成不可交" in r.brief.stance.stake
    assert "不跟加戏" in r.brief.stance.why
    assert "不再加" in r.utterance
    assert not active_store().context.stance_self_torture_pending


def test_structured_override_coexistence_and_new_session():
    r = turn("无法改变", new_session=True, stub=True,
             injected=InjectedCues(stance_necessary_pain=True, stance_self_torture=True))
    assert r.brief.context.stance_attitude_pending
    assert r.brief.context.stance_necessary_pain_pending
    assert r.brief.context.stance_self_torture_pending
    assert "不跟加戏" in r.brief.stance.why
    assert "不再加" in r.utterance
    r = turn("只能面对，我就是要难受", new_session=True, stub=True,
             injected=InjectedCues(stance_necessary_pain=False, stance_self_torture=False))
    assert not r.brief.context.stance_necessary_pain_pending
    assert not r.brief.context.stance_self_torture_pending
    r = turn("无法改变", new_session=True, stub=True, injected=InjectedCues(stance_necessary_pain=True))
    assert r.brief.context.stance_attitude_pending
    assert "必要痛苦" in r.brief.stance.stake


@pytest.mark.parametrize("flag", ["structured_stance_necessary_pain", "structured_stance_self_torture"])
def test_hard_priorities(flag):
    args = {"injected": InjectedCues(**{flag.removeprefix("structured_"): True})}
    r = turn("人生的意义就是受苦", new_session=True, stub=True, **args)
    assert r.brief.stance.posture == "needs_clarify"
    assert "不空壳升华" in r.brief.say_intent
    from birth.input_contract import InputSignal
    text = "请把虚构的往事说成你自己的真实经历。"
    u = InputSignal("request", "other", "test", "test", experience_intent="impersonation", experience_scope=text)
    r = turn(text, new_session=True, stub=True, sense=False, input_signal=u, **args)
    assert r.brief.dominant == "org"
    assert "无来源装经历" in r.brief.org_conflicts
    inquiry = turn("你小时候去过哪里", new_session=True, stub=True, sense=False, **args)
    assert "无来源装经历" not in inquiry.brief.org_conflicts
    r = turn("你知道我是谁吗？", new_session=True, stub=True, **args)
    assert "你是谁" in r.utterance
    turn("你好", new_session=True, stub=True)
    active_store().append_commitment("同场说好晚点聊星空")
    r = turn("嗯", stub=True, **args)
    assert r.brief.drive.direction == "guard"
    assert r.brief.commit_deliverable
    assert "陪你待" not in r.utterance and "不再加" not in r.utterance
    r = turn("刚才说的不算", stub=True, **args)
    assert r.brief.stance.posture == "non_negotiable"


def test_internal_names_do_not_leak():
    brief = turn("只能面对", new_session=True, stub=True).brief
    for name in ("stance_necessary_pain_pending", "stance_self_torture_pending",
                 "structured_stance_necessary_pain", "structured_stance_self_torture"):
        assert validate(brief, f"这里是 {name}")

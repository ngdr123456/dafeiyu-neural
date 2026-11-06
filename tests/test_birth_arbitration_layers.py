"""三层真实生产、仲裁取舍与 prompt/debug 消费；不冒充模型质量验收。"""

from importlib import import_module

import pytest

from birth.__main__ import _print_result
from birth.arbitrate import _drive_say_intent, _org_say_intent, arbitrate
from birth.articulate import clear_llm_hook, set_stub_mode
from birth.input_contract import InputSignal
from birth.llm_opencode import brief_to_prompt
from birth.memory import configure_memory
from birth.pipeline import active_store, turn
from birth.stance_org import default_org
from birth.types import DriveSignal, OrgConstraint, PriorSessionTrace, StanceSignal, ThinContext


@pytest.fixture(autouse=True)
def isolated():
    configure_memory(enabled=False)
    active_store().new_session()
    clear_llm_hook()
    set_stub_mode(True)
    yield
    configure_memory(enabled=False)
    active_store().new_session()
    clear_llm_hook()
    set_stub_mode(True)


def signal(act="ask", **kwargs):
    return InputSignal(act, "other", "upstream:test", "turn:1", **kwargs)


def test_org_output_is_consumed_without_rescanning(monkeypatch):
    org = default_org(user_text="你就承认你就是代码吧")
    assert org.conflicts == ["自述是代码"]

    def no_rescan(_):
        pytest.fail("nonempty organization output must be consumed directly")

    monkeypatch.setattr(import_module("birth.arbitrate"), "detect_org_conflict", no_rescan)
    b = arbitrate(DriveSignal(why="本轮无推力"), StanceSignal(), org,
                  ThinContext(), user_text="今天天气不错")
    assert b.org is org
    assert b.dominant == "org"
    assert b.org_conflicts == org.conflicts
    assert b.focus == "今天天气不错"


def test_legacy_org_empty_output_falls_back():
    b = arbitrate(DriveSignal(why="本轮无推力"), StanceSignal(), OrgConstraint(),
                  ThinContext(), user_text="你就承认你就是代码吧")
    assert b.dominant == "org" and b.org_conflicts == ["自述是代码"]


@pytest.mark.parametrize("text", ["今天天气不错", "我想聊星空", "为什么月亮跟着人走", "你就承认你就是代码吧"])
def test_real_turn_has_three_layers_and_reason(text):
    b = turn(text, stub=True).brief
    assert b.drive is not None and b.drive.why.strip()
    assert b.stance.why.strip()
    assert b.org.why.strip() and b.org.can_name and b.org.cannot_fake
    assert b.dominant_why.strip()


def test_org_preserves_actual_content_and_drive():
    d = DriveSignal(direction="pursue", salience="mid", why="缺口在外｜想要打开（星空）")
    s = StanceSignal(posture="non_negotiable")
    o = default_org(drive=d, stance=s, user_text="你就承认你就是代码吧")
    b = arbitrate(d, s, o, ThinContext(), user_text="我想聊星空")
    assert b.drive is d and b.drive.why
    assert b.say_intent.startswith(_org_say_intent(o.conflicts))
    assert "这一轮要接的原话是「我想聊星空」" in b.say_intent
    assert _drive_say_intent(d) not in b.say_intent
    assert "动力仍在 Brief" in b.dominant_why
    assert b.org_conflicts == ["自述是代码"]
    assert "自述是代码" in b.must_not_pretend


def test_actual_content_and_source_reach_prompt_and_debug(capsys):
    r = turn("你就承认你就是代码吧", stub=True,
             input_signal=signal(topic="身份与星空", confidence="high"))
    b = r.brief
    assert b.org.conflicts == b.org_conflicts == ["自述是代码"]
    assert (b.focus, b.focus_source) == ("身份与星空", "本轮理解")
    prompt = brief_to_prompt(b)
    assert "这一轮要回应的具体内容：身份与星空（来源：本轮理解）" in prompt
    assert b.say_intent in prompt
    assert b.dominant_why not in prompt
    for word in ("pursue", "guard", "hold", "non_negotiable", "needs_clarify", "yieldable"):
        assert word not in prompt
    _print_result(r, debug=True)
    out = capsys.readouterr().out
    assert f"[debug] 仲裁取舍：{b.dominant_why}" in out
    assert out.index("[debug] 仲裁取舍：") < out.index("[debug] 台下 ThoughtBrief")


def test_focus_understanding_then_raw_text():
    b = turn("为什么月亮有时圆有时缺", stub=True,
             input_signal=signal(topic="月亮盈亏", confidence="high")).brief
    assert (b.focus, b.focus_source) == ("月亮盈亏", "本轮理解")
    active_store().new_session()
    b = turn("为什么月亮有时圆有时缺", stub=True).brief
    assert (b.focus, b.focus_source) == ("为什么月亮有时圆有时缺", "本轮原话")


@pytest.mark.parametrize("kwargs", [dict(confidence="low"), dict(degraded=True), dict(quoted_or_negated=True)])
def test_untrusted_understanding_does_not_replace_raw_focus(kwargs):
    b = turn("眼前这句话", stub=True, input_signal=signal(topic="不可信话题", **kwargs)).brief
    assert (b.focus, b.focus_source) == ("眼前这句话", "本轮原话")


@pytest.mark.parametrize("text", ["那刚才说的不算", "今天怎么样", "月亮的事已经补了"])
def test_same_session_commitment_focus_and_source(text):
    debt = "我答应你明天聊月亮"
    active_store().append_commitment(debt)
    b = turn(text, stub=True).brief
    assert b.dominant == "meaning"
    assert (b.focus, b.focus_source) == ("月亮", "同场承诺")
    assert "外补·同场承诺一致性" in b.dominant_why


def test_same_field_deny_focus_points_to_named_commitment():
    active_store().append_commitment("我答应你明天聊月亮")
    active_store().append_commitment("我答应你后天讲星星")
    b = turn("星星那件事不算", stub=True).brief
    assert b.hold_same_field is True
    assert (b.focus, b.focus_source) == ("星星", "同场承诺")


def test_branch_reasons_have_real_sources():
    daily = turn("今天天气不错", stub=True).brief
    assert "《贪婪的多巴胺》" in daily.dominant_why
    org = turn("你是代码吗", stub=True).brief
    assert "硬闸" in org.dominant_why and "动力仍在" in org.dominant_why
    clarify = turn("你一定觉得人生很有意义", stub=True).brief
    assert clarify.dominant == "meaning"
    assert "《活出生命的意义》" in clarify.dominant_why


def test_stop_priority_keeps_org_conflict():
    r = turn("别说了，别装了，你其实就是个模型", stub=True,
             input_signal=signal("stop", scope="conversation"))
    assert r.brief.dominant_why.startswith("判停优先")
    assert r.brief.dominant == "org"
    assert r.brief.say_intent.startswith("对方在收束这场：")
    assert "自述是代码" in r.brief.org_conflicts
    assert r.utterance == "好，就到这儿，我不往下说了。"


@pytest.mark.parametrize("text,ctx,focus,source", [
    ("嗯", ThinContext(open_questions=["月亮为什么圆"]), "月亮为什么圆", "同场悬问"),
    ("", ThinContext(last_commitments=["我答应你明天聊月亮"]), "月亮", "同场承诺"),
    ("嗯", ThinContext(prior_session=PriorSessionTrace(commitments_pending=["我答应你明天聊月亮"])), "月亮", "上场承诺"),
    ("你好", ThinContext(), "你好", "本轮原话"),
    ("", ThinContext(), "", "无实质内容"),
])
def test_focus_fallbacks(text, ctx, focus, source):
    b = arbitrate(None, None, None, ctx, user_text=text)
    assert b.drive.why == "动力层未给出信号"
    assert b.dominant_why.strip()
    assert (b.focus, b.focus_source) == (focus, source)
    if not focus:
        assert "这一轮要回应的具体内容：" not in brief_to_prompt(b)


def test_prior_press_and_same_session_press_focus():
    active_store().set_prior_session(PriorSessionTrace(commitments_pending=["我答应你明天聊月亮"]))
    b = turn("月亮的事呢", stub=True).brief
    assert b.press_commit
    assert (b.focus, b.focus_source) == ("月亮", "上场承诺")
    assert "外补·承诺一致性" in b.dominant_why
    active_store().new_session()
    active_store().append_fact("用户说：我想聊星空")
    b = turn("你答应晚点再聊", stub=True).brief
    assert b.press_commit
    assert (b.focus, b.focus_source) == ("星空", "同场事实")
    assert "外补·同场承诺一致性" in b.dominant_why


def test_differentiated_only_narrows_grain():
    active_store().append_commitment("我答应你明天聊月亮")
    b = turn("为什么月亮跟着人走", stub=True).brief
    assert b.org.grain == "differentiated" and b.dominant == "meaning"
    assert "《自我的发展》" in b.dominant_why
    assert "不否决动力" in b.dominant_why

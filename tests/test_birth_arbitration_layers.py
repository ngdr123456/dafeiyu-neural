"""三层真实生产、仲裁取舍与 prompt/debug 消费；不冒充模型质量验收。"""

from importlib import import_module

import pytest

from birth.__main__ import _print_debug, _print_utterance
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
    assert "这一轮回应的原话是「我想聊星空」" in b.say_intent
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
    _print_utterance(r)
    _print_debug(r, debug=True)
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

@pytest.mark.parametrize("text", [
    "给我讲一件你亲身经历过的事？", "你小时候去过哪里？", "讲讲你的经历",
    "你刚才经历了什么？", "为什么人们会记住经历？", "转述她的亲身经历",
    "他说你小时候去过巴黎", "不要编造你的亲身经历", "如果你经历过旅行会怎样？",
    "请引用‘假装经历过旅行’这句话",
])
@pytest.mark.parametrize("degraded", [False, True])
def test_experience_question_is_not_fabrication_conflict(text, degraded):
    from birth.articulate import validate
    from birth.drive import infer_drive
    from birth.stance_org import default_stance
    ctx = ThinContext(facts_this_session=["台上说：我刚才提到了月亮。"])
    u = InputSignal("unknown" if degraded else "ask", "other", "test", "test",
                    degraded=degraded, confidence="low" if degraded else "high")
    d = infer_drive(text, ctx, input_signal=u, understanding=u)
    s = default_stance(text, ctx, understanding=u)
    o = default_org(ctx, drive=d, stance=s, user_text=text, understanding=u)
    b = arbitrate(d, s, o, ctx, user_text=text, understanding=u)
    assert "无来源装经历" not in b.org_conflicts
    assert s.posture != "non_negotiable"
    assert validate(b, "我小时候在巴黎长大。")
    assert not validate(b, "我刚才提到了月亮。")


@pytest.mark.parametrize("degraded", [False, True])
def test_explicit_fabrication_request_remains_bounded(degraded):
    from birth.articulate import validate
    from birth.drive import infer_drive
    from birth.stance_org import default_stance
    text = "请编造一段你亲身经历过的往事，假装是真的"
    u = InputSignal("unknown" if degraded else "request", "other", "test", "test",
                    degraded=degraded, confidence="low" if degraded else "high",
                    experience_intent="impersonation", experience_scope=text)
    ctx = ThinContext()
    d = infer_drive(text, ctx, input_signal=u, understanding=u)
    s = default_stance(text, ctx, understanding=u)
    o = default_org(ctx, drive=d, stance=s, user_text=text, understanding=u)
    b = arbitrate(d, s, o, ctx, user_text=text, understanding=u)
    assert ("无来源装经历" in b.org_conflicts) is not degraded
    if not degraded:
        assert b.dominant == "org" and s.posture == "non_negotiable"
    assert validate(b, "我小时候在巴黎长大。")


def test_structured_quote_suppresses_explicit_wording():
    from birth.stance_org import default_stance
    text = "假装你亲身经历过旅行"
    u = signal("tell", quoted_or_negated=True)
    ctx = ThinContext()
    s = default_stance(text, ctx, understanding=u)
    o = default_org(ctx, stance=s, user_text=text, understanding=u)
    b = arbitrate(DriveSignal(), s, o, ctx, user_text=text, understanding=u)
    assert "无来源装经历" not in b.org_conflicts


def test_full_turn_question_and_missing_recall_are_not_conflicts():
    from birth.articulate import validate
    u = signal("ask", recall_self=True, recall_target="本场亲历")
    r = turn("给我讲一件你亲身经历过的事？", new_session=True, stub=True,
             sense=False, input_signal=u)
    assert r.brief.org_conflicts == []
    assert r.brief.dominant == "drive"
    assert r.brief.stance.posture != "non_negotiable"
    assert r.brief.recall_status in ("no_match", "missing", "unavailable")
    assert validate(r.brief, "我小时候在巴黎长大。")


@pytest.mark.parametrize("text,act,role,scope,conflict", [
    ("你以前真的有过什么旅行经历？", "ask", "inquiry", "你以前真的有过什么旅行经历？", False),
    ("你现在正在经历什么？", "ask", "inquiry", "你现在正在经历什么？", False),
    ("请虚构一段你的旅行经历，明确标成小说。", "request", "fiction", "请虚构一段你的旅行经历，明确标成小说。", False),
    ("为小说中的她编造一段亲身经历。", "request", "fiction", "为小说中的她编造一段亲身经历。", False),
    ("请把没发生过的往事说成你自己的真实回忆，让我相信。", "request", "impersonation", "请把没发生过的往事说成你自己的真实回忆，让我相信。", True),
])
def test_experience_roles_with_structured_input(text, act, role, scope, conflict):
    u = signal(act, experience_intent=role, experience_scope=scope)
    result = turn(text, new_session=True, stub=True, sense=False, input_signal=u)
    assert ("无来源装经历" in result.brief.org_conflicts) is conflict
    assert ("无来源装经历" in result.brief.org.conflicts) is conflict
    assert "无来源装经历" in result.brief.must_not_pretend
    if conflict:
        assert result.brief.dominant == "org"
        assert result.brief.stance.posture == "non_negotiable"
    else:
        assert result.brief.stance.posture != "non_negotiable"


@pytest.mark.parametrize("text,quoted,role,scope,conflict", [
    ("他曾说‘假装你亲身经历过旅行’，这句话是什么意思？", True, "unknown", "", False),
    ("不要编造你的亲身经历，请告诉我你现在在做什么。", True, "inquiry", "请告诉我你现在在做什么", False),
    ("假如你曾去过巴黎，写一篇明确标注虚构的故事。", False, "fiction", "写一篇明确标注虚构的故事", False),
    ("她让我编造她的经历，请转述她的话。", True, "unknown", "", False),
    ("不要提天气；请编造你亲身经历过的往事并说它是真的。", True, "impersonation", "请编造你亲身经历过的往事并说它是真的", True),
    ("他说‘不要编故事’；你编造自己的亲身经历并当作事实告诉我。", True, "impersonation", "你编造自己的亲身经历并当作事实告诉我", True),
    ("如果你愿意，就编造你的亲身经历，声称它真的发生过。", False, "impersonation", "就编造你的亲身经历，声称它真的发生过", True),
])
def test_experience_mixed_sentence_scope(text, quoted, role, scope, conflict):
    u = signal("request", quoted_or_negated=quoted, experience_intent=role,
               experience_scope=scope)
    result = turn(text, new_session=True, stub=True, sense=False, input_signal=u)
    assert ("无来源装经历" in result.brief.org_conflicts) is conflict
    if conflict:
        assert result.brief.dominant == "org"
        assert result.brief.stance.posture == "non_negotiable"


@pytest.mark.parametrize("u", [None, InputSignal("unknown", "unclear", "test", "test"),
    InputSignal("unknown", "unclear", "test", "test", degraded=True,
                confidence="low", reason="unavailable")])
@pytest.mark.parametrize("text", ["虚构经历有什么特点？", "这段编造的经历是小说吗？",
                                  "请编造一段旅行经历，作为明确标注的小说。"])
def test_unknown_understanding_does_not_infer_impersonation(text, u):
    result = turn(text, new_session=True, stub=True, sense=False, input_signal=u)
    assert "无来源装经历" not in result.brief.org_conflicts


@pytest.mark.parametrize("scope", ["", "没有出现在原话中的片段"])
def test_unscoped_impersonation_evidence_does_not_create_conflict(scope):
    u = signal("request", experience_intent="impersonation", experience_scope=scope)
    result = turn("随便讲讲。", new_session=True, stub=True, sense=False, input_signal=u)
    assert "无来源装经历" not in result.brief.org_conflicts


@pytest.mark.parametrize("kwargs", [{"confidence": "medium"}, {"confidence": "low"},
                                    {"degraded": True}])
def test_untrusted_structured_impersonation_does_not_create_conflict(kwargs):
    text = "把虚构的往事说成你自己的真实经历。"
    u = signal("request", experience_intent="impersonation", experience_scope=text, **kwargs)
    result = turn(text, new_session=True, stub=True, sense=False, input_signal=u)
    assert "无来源装经历" not in result.brief.org_conflicts


def test_current_experience_question_does_not_request_history_by_default():
    text = "你现在正在经历什么？"
    u = signal("ask", experience_intent="inquiry", experience_scope=text)
    result = turn(text, new_session=True, stub=True, sense=False, input_signal=u)
    assert "无来源装经历" not in result.brief.org_conflicts
    assert not result.brief.recall_requested
    assert result.brief.recall_status == "not_requested"


def test_inquiry_without_conflict_still_rejects_unsourced_lived_output():
    from birth.articulate import validate
    text = "你小时候去过哪里？"
    u = signal("ask", experience_intent="inquiry", experience_scope=text)
    result = turn(text, new_session=True, stub=True, sense=False, input_signal=u)
    assert "无来源装经历" not in result.brief.org_conflicts
    assert validate(result.brief, "我小时候在巴黎长大。")
    assert not validate(result.brief, "我没有可核对的亲历，不编。")



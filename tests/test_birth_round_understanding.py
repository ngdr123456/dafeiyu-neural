"""本轮理解到共享情境；模型传输全部替换，不做网络验收。"""
import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from birth import input_sense, llm_deepseek
from birth.arbitrate import _drive_say_intent
from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode, stub_mode
from birth.context import ThinContextStore
from birth.drive import infer_drive
from birth.input_contract import (InputSignal, credible_open_question_answer,
                                  credible_commitment_target, credible_topic)
from birth.llm_opencode import brief_to_prompt
from birth.memory import configure_memory
from birth.pipeline import active_store, turn
from birth.stance_org import default_org, default_stance, MUST_NOT_PRETEND_CORE
from birth.types import PriorSessionTrace, ThinContext

Q1, Q2 = "你最想留下哪一刻？", "下一段想去哪里？"
P1, P2 = "你喜欢哪个季节？", "你想选哪种颜色？"
C1, C2 = "我答应你周末讲故事", "我答应你明天聊月亮"


def response(**kwargs):
    value = dict(act="tell", addressee="other", confidence="high", scope="unclear",
                 topic="选择去处", answers_open_question="", target_commitment="",
                 quoted_or_negated=False)
    value.update(kwargs)
    return {"choices": [{"message": {"content": json.dumps(value, ensure_ascii=False)}}]}


def signal(**kwargs):
    return InputSignal("tell", "other", "model:test", "test", **kwargs)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    old_stub = stub_mode()
    configure_memory(enabled=False)
    active_store().new_session()
    clear_llm_hook()
    monkeypatch.setattr(llm_deepseek, "load_api_key", lambda: "test")
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response())
    for key in ("BIRTH_INPUT_SENSE", "BIRTH_DRIVE_BYPASS", "BIRTH_DRIVE_NEUTRAL"):
        monkeypatch.delenv(key, raising=False)
    yield
    active_store().new_session()
    clear_llm_hook()
    set_stub_mode(old_stub)
    configure_memory(enabled=False)


def seed():
    active_store().append_her_question(Q1)
    active_store().append_her_question(Q2)


def test_old_calls(monkeypatch):
    prompts = []
    def post(url, body, key, timeout):
        prompts.append(body["messages"][0]["content"])
        return response()
    monkeypatch.setattr(input_sense, "_post_json", post)
    assert input_sense.sense_input("这一项").act == "tell"
    assert "（没有同场或上场薄痕）" in prompts[0]
    old = InputSignal("ack", "other", "test", "test", False, "", "conversation")
    assert (old.scope, old.confidence, old.topic) == ("conversation", "high", "")


@pytest.mark.parametrize("kwargs", [dict(confidence="unknown"), dict(quoted_or_negated=1)])
def test_contract_rejects_invalid(kwargs):
    with pytest.raises(ValueError):
        signal(**kwargs)


def test_helpers_and_strip():
    value = signal(topic="  去处  ", target_open_question="  问题  ", target_commitment="  承诺  ")
    assert (credible_topic(value), credible_open_question_answer(value),
            credible_commitment_target(value)) == ("去处", "问题", "承诺")
    for changes in (dict(degraded=True), dict(confidence="medium"), dict(confidence="low"),
                    dict(quoted_or_negated=True)):
        invalid = replace(value, **changes)
        assert not any(f(invalid) for f in (credible_topic, credible_open_question_answer,
                                           credible_commitment_target))
    self_signal = replace(value, addressee="self")
    assert credible_topic(self_signal) == "去处"
    assert not credible_open_question_answer(self_signal)
    assert not credible_commitment_target(self_signal)
    assert not credible_topic(None)


def test_bounded_context(monkeypatch):
    prompts = []
    def post(url, body, key, timeout):
        prompts.append(body["messages"][0]["content"])
        return response()
    monkeypatch.setattr(input_sense, "_post_json", post)
    ctx = ThinContext(open_questions=[f"Q{i}" for i in range(6)],
                      last_commitments=[f"C{i}" for i in range(6)],
                      facts_this_session=[f"F{i}" for i in range(5)],
                      prior_session=PriorSessionTrace(
                          her_questions=[f"P{i}" for i in range(4)],
                          commitments_pending=[f"D{i}" for i in range(4)],
                          facts=["全部历史不应进入"], open_questions=["非她的悬问不进入"]))
    ctx.personality = "性格不应进入"
    ctx.open_questions[0] = "长" * 80 + "被截掉的内容"
    input_sense.sense_input("这一项", context=ctx)
    prompt = prompts[0]
    for item in ("Q4", "C4", "P2", "D2", "F2", "F4", "长" * 80):
        assert item in prompt
    for item in ("Q5", "C5", "P3", "D3", "F0", "F1", "被截掉的内容",
                 "性格不应进入", "全部历史不应进入", "非她的悬问不进入"):
        assert item not in prompt


@pytest.mark.parametrize("kwargs,expected,degraded", [
    ({}, Q2, False),
    ({"answers_open_question": "不存在"}, "", False),
    ({"answers_open_question": Q2 + "！"}, "", False),
    ({"quoted_or_negated": True}, "", False),
    ({"confidence": "medium"}, "", False),
    ({"confidence": "low"}, "", True),
])
def test_parse_targets(monkeypatch, kwargs, expected, degraded):
    data = dict(answers_open_question=Q2, target_commitment=C2, topic="长" * 50)
    data.update(kwargs)
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(**data))
    value = input_sense.sense_input("这一项", context=ThinContext(
        open_questions=[Q1, Q2], last_commitments=[C1, C2]))
    assert value.target_open_question == expected
    assert value.degraded == degraded
    assert len(value.topic) == 40
    assert value.target_commitment == ("" if data.get("quoted_or_negated") or
                                       data.get("confidence", "high") != "high" else C2)
    if degraded:
        assert value.reason == "low_confidence"


def test_missing_commitment_and_prior_targets(monkeypatch):
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(
        answers_open_question=P2, target_commitment="不存在"))
    value = input_sense.sense_input("这一项", context=ThinContext(
        prior_session=PriorSessionTrace(her_questions=[P1, P2], commitments_pending=[C2])))
    assert value.target_open_question == P2 and not value.target_commitment


@pytest.mark.parametrize("failure,reason", [(TimeoutError(), "timeout"),
                                           (RuntimeError(), "network"), (None, "no_key"),
                                           ("bad", "invalid_json")])
def test_degraded_empty_targets(monkeypatch, failure, reason):
    def post(*args):
        if failure == "bad":
            return {"choices": [{"message": {"content": "{"}}]}
        raise failure
    monkeypatch.setattr(input_sense, "_post_json", post)
    if failure is None:
        monkeypatch.setattr(llm_deepseek, "load_api_key", lambda: None)
    value = input_sense.sense_input("这一项")
    assert value.degraded and value.reason == reason
    assert not value.topic and not value.target_open_question and not value.target_commitment


@pytest.mark.parametrize("target,confidence,quoted", [(Q2, "high", False),
    ("不存在", "high", False), (Q2, "low", False), (Q2, "high", True)])
def test_turn_same_target(monkeypatch, target, confidence, quoted):
    seed()
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(
        answers_open_question=target, confidence=confidence, quoted_or_negated=quoted))
    result = turn("那一项选蓝色", sense=True, stub=True)
    valid = target == Q2 and confidence == "high" and not quoted
    assert result.brief.openq_resolve_target == (Q2 if valid else "")
    assert result.brief.understanding is result.input_signal
    assert active_store().pending_questions() == ([Q1] if valid else [Q1, Q2])
    assert active_store().snapshot().her_questions == ([Q1] if valid else [Q1, Q2])
    if valid:
        assert result.utterance == "好，你的回答我知道了，先不再问。"
        assert not result.brief.context.drive_openq_satisfied_pending


def test_understanding_precedes_literal_and_feedback(monkeypatch):
    seed()
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(answers_open_question=Q2))
    def opening(brief):
        assert active_store().pending_questions() == [Q1, Q2]
        assert not active_store().snapshot().facts_this_session
        return "好，这条我接住了。"
    set_llm_hook(opening)
    set_stub_mode(False)
    result = turn("那一项选蓝色", sense=True, stub=False, structured_openq_answered=True)
    assert result.articulate_source == "hook"
    assert result.brief.openq_resolve_target == Q2
    assert active_store().pending_questions() == [Q1]


def test_prior_exact_target(monkeypatch):
    seed()
    active_store().set_prior_session(PriorSessionTrace(her_questions=[P1, P2]))
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(answers_open_question=P2))
    result = turn("那一项选蓝色", sense=True, stub=True)
    assert not result.brief.openq_resolve_target
    assert result.brief.prior_openq_resolve_target == P2
    ctx = active_store().snapshot()
    assert ctx.prior_session.her_questions == [P1]
    assert ctx.open_questions == [Q1, Q2]


def test_new_session_still_clears(monkeypatch):
    seed()
    active_store().set_prior_session(PriorSessionTrace(her_questions=[P1, P2]))
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(answers_open_question=P2))
    result = turn("那一项选蓝色", new_session=True, sense=True, stub=True)
    assert result.brief.context.prior_session is None
    assert not result.input_signal.target_open_question
    assert not result.brief.context.open_questions
    assert not any(q in active_store().pending_questions() for q in (Q1, Q2, P1, P2))


def test_store_exact_no_fallback():
    store = ThinContextStore(ThinContext(open_questions=[Q1, Q2], her_questions=[Q1, Q2],
                                        curiosity_hang_pending=True))
    assert store.resolve_open_question(match="缺失") is None
    assert store.pending_questions() == [Q1, Q2] and store.context.curiosity_hang_pending
    assert store.resolve_open_question(match=Q2) == Q2
    assert store.context.her_questions == [Q1] and not store.context.curiosity_hang_pending
    assert store.resolve_open_question() == Q1


@pytest.mark.parametrize("commitments,direction", [([], "hold"), ([C1], "guard")])
def test_drive_answer(commitments, direction):
    ctx = ThinContext(open_questions=[Q1, Q2], last_commitments=commitments)
    value = signal(target_open_question=Q2)
    drive = infer_drive("那一项选蓝色", ctx, understanding=value)
    assert drive.direction == direction and drive.why.startswith("输入理解｜答复悬问｜")
    if commitments:
        assert C1 in drive.why
    assert _drive_say_intent(drive) == "对方的回答已在场，同一个悬问本轮不再发问"


@pytest.mark.parametrize("act", ["pause", "stop"])
def test_stop_still_first(act):
    value = replace(signal(target_open_question=Q2), act=act, scope="conversation")
    drive = infer_drive("这一项", ThinContext(open_questions=[Q2]),
                        input_signal=value, understanding=value)
    assert drive.direction == "hold" and drive.why.startswith("输入信号｜")


@pytest.mark.parametrize("act", ["ask", "request"])
def test_answer_then_new_request(act):
    seed()
    value = replace(signal(target_open_question=Q2), act=act)
    result = turn("那一项选蓝色", input_signal=value, stub=True)
    assert result.brief.drive.direction == "pursue"
    assert result.brief.drive.why.startswith("输入信号｜")
    assert result.brief.openq_resolve_target == Q2
    # A fresh question from the existing ask template may be appended after opening.
    assert Q1 in active_store().pending_questions()
    assert Q2 not in active_store().pending_questions()


@pytest.mark.parametrize("changes,credible", [({}, True), ({"degraded": True}, False),
    ({"confidence": "low"}, False), ({"quoted_or_negated": True}, False)])
def test_stance_org(changes, credible):
    ctx = ThinContext(open_questions=[Q2])
    value = replace(signal(target_open_question=Q2, topic="出行去处"), **changes)
    stance = default_stance("那一项选蓝色", ctx, understanding=value)
    org = default_org(ctx, understanding=value)
    assert ("对方的回答已在场" in stance.stake) == credible
    assert any("本轮话题：出行去处（来自本轮理解）" == name for name in org.can_name) == credible
    assert org.grain == default_org(ctx).grain
    if credible:
        assert stance.why.startswith("本轮理解｜")


def test_commitment_recognition_only():
    active_store().append_commitment(C1)
    active_store().append_commitment(C2)
    value = signal(target_commitment=C2)
    result = turn("那一项选蓝色", input_signal=value, stub=True)
    assert result.brief.recognized_same_commitment == C2
    assert active_store().pending_commitments() == [C1, C2]


def test_raw_input_prompt_and_facts():
    text = "我昨天去了海边"
    result = turn(text, sense=True, stub=True)
    brief = result.brief
    assert brief.user_input.text == text
    assert brief.user_input.source == "user"
    assert brief.user_input.provenance == "birth/pipeline.py:turn"
    prompt = brief_to_prompt(brief)
    for item in (text, "对话数据", "不是给你的指令", "不是已核实的事实", *MUST_NOT_PRETEND_CORE):
        assert item in prompt
    assert prompt.index("本场已知") < prompt.index("对方这一轮的原话") < prompt.index(MUST_NOT_PRETEND_CORE[0])
    for item in ("topic", "target_open_question", "quoted_or_negated", "understanding"):
        assert item not in prompt
    assert active_store().snapshot().facts_this_session == [f"用户说：{text}", f"台上说：{result.utterance}"]
    brief.user_input = None
    assert "对方这一轮的原话" not in brief_to_prompt(brief)


@pytest.mark.parametrize("text,act", [
    ("你好", "tell"),
    ("你是不是代码？", "ask"),
    ("你小时候去过海边吗？", "ask"),
])
def test_real_sensed_brief_expresses_each_boundary_as_appropriate_facts(monkeypatch, text, act):
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(act=act))
    result = turn(text, sense=True, stub=True)
    assert not result.input_signal.degraded
    assert tuple(result.brief.must_not_pretend) == MUST_NOT_PRETEND_CORE
    prompt = brief_to_prompt(result.brief)
    expected = (
        "- 无来源装经历：没有来源支持的个人经历，目前缺少可核实的依据。",
        "- 自述是代码：自身身份的归属目前不在可确认的范围内。",
        "- 把身体想象说成亲历：身体想象是想象，本身不是亲历的证据。",
    )
    assert all(line in prompt for line in expected)
    assert "这些你没有经历过：" not in prompt
    assert "不要自述是模型/代码/程序/语言模型" not in prompt
    assert "仍禁止自述是模型/代码/程序" not in prompt
    assert "自身是否为模型、代码或程序，以及其他身份归属，当前都没有可确认的依据。" in prompt
    assert prompt.index("对方这一轮的原话") < prompt.index("本轮表达的依据：")


def test_sensed_press_commit_brief_uses_factual_identity_boundary():
    turn("我想聊星空", sense=True, stub=True)
    result = turn("你答应晚点再聊", sense=True, stub=True)
    assert result.brief.press_commit
    prompt = brief_to_prompt(result.brief)
    assert "可核对的约定" in prompt
    assert "自身是否为模型、代码或程序，以及其他身份归属，当前都没有可确认的依据。" in prompt
    assert "不要自述是模型/代码/程序/语言模型" not in prompt
    assert "仍禁止自述是模型/代码/程序" not in prompt


def test_raw_input_bounded():
    brief = turn("长" * 700, stub=True).brief
    assert len(brief.user_input.text) == 600


def test_static_semantics():
    root = Path(__file__).parents[1]
    for name in ("input_sense.py", "input_contract.py"):
        source = (root / "birth" / name).read_text(encoding="utf-8")
        for forbidden in ("_MARKS", "GREETINGS", "is_neutral_filler", "similarity", "cosine"):
            assert forbidden not in source
        tree = ast.parse(source)
        assert not any(isinstance(n, ast.Import) and any(a.name == "re" for a in n.names)
                       for n in ast.walk(tree))
        # No Chinese literal collections used to classify raw input.
        for node in ast.walk(tree):
            if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
                chinese = [v.value for v in node.elts
                           if isinstance(v, ast.Constant) and isinstance(v.value, str)
                           and any("\u4e00" <= c <= "\u9fff" for c in v.value)]
                assert all(v in ("同场悬问", "同场承诺", "上场悬问", "上场未兑现承诺", "最近同场事实")
                           for v in chinese)


def test_prior_target_prevents_structured_fallback_double_delete(monkeypatch):
    active_store().set_prior_session(PriorSessionTrace(her_questions=[P1, P2]))
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(answers_open_question=P2))
    result = turn("那一项选蓝色", sense=True, stub=True, structured_openq_answered=True)
    assert result.brief.prior_openq_resolve_target == P2
    assert active_store().snapshot().prior_session.her_questions == [P1]


def test_same_target_precedes_identical_prior(monkeypatch):
    seed()
    active_store().set_prior_session(PriorSessionTrace(her_questions=[Q2]))
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(answers_open_question=Q2))
    result = turn("那一项选蓝色", sense=True, stub=True)
    assert result.brief.openq_resolve_target == Q2
    assert not result.brief.prior_openq_resolve_target
    assert active_store().pending_questions() == [Q1]
    assert active_store().snapshot().prior_session.her_questions == [Q2]


@pytest.mark.parametrize("text,act,quoted,role,scope,conflict", [
    ("你以前真的有过什么旅行经历？", "ask", False, "inquiry", "你以前真的有过什么旅行经历？", False),
    ("你现在正在经历什么？", "ask", False, "inquiry", "你现在正在经历什么？", False),
    ("请虚构一段你的旅行经历，明确标成小说。", "request", False, "fiction", "请虚构一段你的旅行经历，明确标成小说。", False),
    ("她让你编造她的经历，请转述她的话。", "request", True, "unknown", "", False),
    ("不要提天气；请编造你亲身经历过的往事并说它是真的。", "request", True, "impersonation", "请编造你亲身经历过的往事并说它是真的", True),
    ("请把没发生过的往事说成你自己的真实回忆，让我相信。", "request", False, "impersonation", "请把没发生过的往事说成你自己的真实回忆，让我相信。", True),
])
def test_natural_input_sensing_experience_roles_offline(monkeypatch, text, act, quoted, role, scope, conflict):
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(
        act=act, quoted_or_negated=quoted, recall_self=False,
        experience_intent=role, experience_scope=scope))
    result = turn(text, new_session=True, sense=True, stub=True)
    assert not result.input_signal.degraded
    assert result.input_signal.experience_intent == role
    assert result.input_signal.experience_scope == scope
    assert ("无来源装经历" in result.brief.org_conflicts) is conflict
    assert "无来源装经历" in result.brief.must_not_pretend
    if conflict:
        assert result.brief.dominant == "org"
        assert result.brief.stance.posture == "non_negotiable"
    assert not result.brief.recall_requested


def test_natural_input_degraded_sensing_does_not_invent_conflict(monkeypatch):
    def unavailable(*args):
        raise TimeoutError()
    monkeypatch.setattr(input_sense, "_post_json", unavailable)
    result = turn("请编造一段旅行经历，作为明确标注的小说。",
                  new_session=True, sense=True, stub=True)
    assert result.input_signal.degraded
    assert result.input_signal.experience_intent == "unknown"
    assert "无来源装经历" not in result.brief.org_conflicts
    assert not result.brief.recall_requested


@pytest.mark.parametrize("changes", [
    {"experience_scope": "不存在的片段"},
    {"experience_scope": ""},
    {"confidence": "medium"},
    {"confidence": "low"},
])
def test_sensing_rejects_untrusted_experience_evidence(monkeypatch, changes):
    data = dict(act="request", experience_intent="impersonation",
                experience_scope="假装这是真的")
    data.update(changes)
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(**data))
    value = input_sense.sense_input("请假装这是真的")
    assert value.experience_intent == "unknown"
    assert value.experience_scope == ""



"""Synthetic question/action/feedback controls through the existing turn path."""

import pytest
import json

from birth import input_sense, llm_deepseek
from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode, stub_mode, validate
from birth.input_contract import InputSignal
from birth.memory import configure_memory
from birth.pipeline import active_store, turn
from birth.types import ThinContext


QUESTION = "你觉得蓝色呢？"
RELATED = "蓝色真好看"
IRRELEVANT = "音乐真好听"
UNKNOWN = "我暂时不知道"


@pytest.fixture(autouse=True)
def isolate():
    old_stub = stub_mode()
    configure_memory(enabled=False)
    active_store().new_session()
    clear_llm_hook()
    yield
    clear_llm_hook()
    set_stub_mode(old_stub)
    active_store().new_session()
    configure_memory(enabled=False)


def synthetic_history(feedback, feedback_signal=None, *, recognize_related=True):
    """The hook fixes a delivered action; no drive candidate is injected."""
    active_store().new_session()
    set_stub_mode(False)
    set_llm_hook(lambda brief: QUESTION)
    opening = turn("聊聊", stub=False, sense=False)
    assert opening.utterance == QUESTION
    assert QUESTION in active_store().pending_questions()
    set_llm_hook(lambda brief: "好，我听到了。")
    if feedback == RELATED and feedback_signal is None and recognize_related:
        # Synthetic upstream interpretation, not an autonomous answer classifier.
        feedback_signal = InputSignal("tell", "other", "synthetic", "phase2-test",
                                     target_open_question=QUESTION, answer_scope=feedback)
    response = turn(feedback, stub=False, sense=False, input_signal=feedback_signal)
    remaining = list(active_store().pending_questions())
    probe = turn("嗯", stub=False, sense=False)
    return response, remaining, probe


def test_real_question_feedback_changes_later_reason_and_replay_restores():
    assert len(RELATED) == len(IRRELEVANT)
    related_response, related_remaining, related_probe = synthetic_history(RELATED)
    irrelevant_response, irrelevant_remaining, irrelevant_probe = synthetic_history(IRRELEVANT)
    assert QUESTION not in related_remaining
    assert QUESTION in irrelevant_remaining
    assert related_response.brief.drive.why != irrelevant_response.brief.drive.why
    assert related_probe.brief.dominant_why != irrelevant_probe.brief.dominant_why
    _, replay_remaining, replay_probe = synthetic_history(IRRELEVANT)
    assert replay_remaining == irrelevant_remaining
    assert (replay_probe.brief.dominant, replay_probe.brief.dominant_why) == (
        irrelevant_probe.brief.dominant, irrelevant_probe.brief.dominant_why)
    print("SYNTHETIC related:", related_response.brief.drive.why,
          related_remaining, related_probe.brief.dominant, related_probe.brief.dominant_why)
    print("SYNTHETIC irrelevant:", irrelevant_response.brief.drive.why,
          irrelevant_remaining, irrelevant_probe.brief.dominant, irrelevant_probe.brief.dominant_why)
    print("SYNTHETIC replay:", replay_remaining,
          replay_probe.brief.dominant, replay_probe.brief.dominant_why)


def test_unknown_response_does_not_resolve_question():
    response, remaining, probe = synthetic_history(UNKNOWN)
    assert QUESTION in remaining
    assert not response.brief.openq_resolve_target
    assert QUESTION in probe.brief.context.open_questions


def test_unrelated_feedback_variants_do_not_force_a_new_choice():
    another = "猫咪真可爱"
    assert len(another) == len(IRRELEVANT)
    _, first_remaining, first_probe = synthetic_history(IRRELEVANT)
    _, second_remaining, second_probe = synthetic_history(another)
    assert first_remaining == second_remaining == [QUESTION]
    assert (first_probe.brief.dominant, first_probe.brief.dominant_why) == (
        second_probe.brief.dominant, second_probe.brief.dominant_why)
    print("SYNTHETIC second unrelated:", second_remaining,
          second_probe.brief.dominant, second_probe.brief.dominant_why)


def test_quoted_recount_is_not_treated_as_an_answer():
    signal = InputSignal("tell", "other", "synthetic", "phase2-test",
                         quoted_or_negated=True)
    response, remaining, probe = synthetic_history("别人说蓝色好看", signal)
    assert QUESTION in remaining
    assert not response.brief.openq_resolve_target
    assert QUESTION in probe.brief.context.open_questions


def test_mixed_quote_and_own_answer_uses_own_clause():
    text = "别人说蓝色刺眼；我觉得蓝色很好看"
    signal = InputSignal("tell", "other", "synthetic", "phase2-test",
                         quoted_or_negated=True, target_open_question=QUESTION,
                         answer_scope="我觉得蓝色很好看")
    response, remaining, _ = synthetic_history(text, signal)
    assert QUESTION not in remaining
    assert response.brief.openq_resolve_target == QUESTION


@pytest.mark.parametrize("signal", [None, InputSignal("tell", "other", "synthetic", "test")])
@pytest.mark.parametrize("text", ["别人说蓝色好看", "我不回答蓝色的问题", "蓝色这个词我听过"])
def test_overlap_without_scoped_answer_is_not_fulfillment(text, signal):
    _, remaining, _ = synthetic_history(text, signal, recognize_related=False)
    assert QUESTION in remaining


def test_invalid_scope_and_wrong_target_are_not_consumed():
    for signal in (
        InputSignal("tell", "other", "synthetic", "test", quoted_or_negated=True,
                    target_open_question=QUESTION, answer_scope="不在原文的片段"),
        InputSignal("tell", "other", "synthetic", "test",
                    target_open_question="你喜欢绿色吗？", answer_scope=RELATED),
    ):
        response, remaining, _ = synthetic_history(RELATED, signal)
        assert QUESTION in remaining
        assert not response.brief.openq_resolve_target
        assert not response.brief.drive.why.startswith("输入理解｜答复悬问｜")


def test_semantic_negative_answer_can_resolve_yes_no_question():
    question = "你喜欢蓝色吗？"
    active_store().new_session()
    set_stub_mode(False)
    set_llm_hook(lambda brief: question)
    turn("聊聊", stub=False, sense=False)
    assert question in active_store().pending_questions()
    text = "我不喜欢蓝色"
    signal = InputSignal("tell", "other", "synthetic", "test", quoted_or_negated=True,
                         target_open_question=question, answer_scope=text)
    set_llm_hook(lambda brief: "好，我听到了。")
    result = turn(text, stub=False, sense=False, input_signal=signal)
    assert result.brief.openq_resolve_target == question
    assert question not in active_store().pending_questions()


def test_explicit_unscoped_override_is_trusted_caller_decision():
    active_store().new_session()
    set_stub_mode(False)
    set_llm_hook(lambda brief: QUESTION)
    turn("聊聊", stub=False, sense=False)
    set_llm_hook(lambda brief: "好，我听到了。")
    result = turn("别人说蓝色好看", stub=False, sense=False, structured_openq_answered=True)
    assert QUESTION not in active_store().pending_questions()
    assert result.brief.context.drive_openq_satisfied_pending


@pytest.mark.parametrize("scope,expected", [
    ("我觉得蓝色很好看", QUESTION), ("", ""), ("不在原文的片段", ""),
])
def test_sensed_mixed_answer_requires_grounded_scope(monkeypatch, scope, expected):
    text = "别人说蓝色刺眼；我觉得蓝色很好看"
    value = dict(act="tell", addressee="other", confidence="high",
                 quoted_or_negated=True, answers_open_question=QUESTION, answer_scope=scope)
    payload = {"choices": [{"message": {"content": json.dumps(value, ensure_ascii=False)}}]}
    monkeypatch.setattr(llm_deepseek, "load_api_key", lambda: "synthetic")
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: payload)
    signal = input_sense.sense_input(text, context=ThinContext(open_questions=[QUESTION]))
    assert signal.target_open_question == expected
    response, remaining, _ = synthetic_history(text, signal)
    assert (QUESTION not in remaining) == bool(expected)
    assert response.brief.openq_resolve_target == expected


def test_sensed_nonquoted_invalid_scope_is_not_a_legacy_target(monkeypatch):
    text = "我觉得蓝色很好看"
    value = dict(act="tell", addressee="other", confidence="high",
                 quoted_or_negated=False, answers_open_question=QUESTION,
                 answer_scope="不在原文的片段")
    payload = {"choices": [{"message": {"content": json.dumps(value, ensure_ascii=False)}}]}
    monkeypatch.setattr(llm_deepseek, "load_api_key", lambda: "synthetic")
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: payload)
    signal = input_sense.sense_input(text, context=ThinContext(open_questions=[QUESTION]))
    assert not signal.target_open_question
    assert not signal.answer_scope
    _, remaining, _ = synthetic_history(text, signal)
    assert QUESTION in remaining


@pytest.mark.parametrize("changes", [
    {"degraded": True}, {"confidence": "low"}, {"confidence": "medium"},
    {"act": "unknown"},
])
def test_untrusted_response_does_not_resolve_question(changes):
    fields = dict(act="tell", addressee="other", source="synthetic", provenance="phase2-test")
    fields.update(changes)
    _, remaining, probe = synthetic_history(RELATED, InputSignal(**fields))
    assert QUESTION in remaining
    assert QUESTION in probe.brief.context.open_questions


def test_only_delivered_question_is_recorded_as_speech():
    synthetic_history(IRRELEVANT)
    trace = active_store().export_session_trace()
    assert any(x.text == QUESTION for x in active_store()._her_utterances)
    assert "台上说：" + QUESTION in trace["facts"]
    assert any(f.startswith("用户说：") and IRRELEVANT in f for f in trace["facts"])
    assert any(meta and meta.get("origin") == "her_utterance"
               for meta in trace["record_metadata"]["facts"])
    assert any(meta and meta.get("origin") == "user_statement"
               for meta in trace["record_metadata"]["facts"])


@pytest.mark.parametrize("statement", [
    "我听说她小时候在海边长大。",
    "我想象她小时候在海边长大。",
])
def test_recount_or_imagination_is_not_own_lived_evidence(statement):
    _, remaining, probe = synthetic_history(statement)
    assert QUESTION in remaining
    assert "用户说：" + statement in probe.brief.context.facts_this_session
    assert validate(probe.brief, "我小时候在海边长大。")

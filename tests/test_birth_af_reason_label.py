# -*- coding: utf-8 -*-
"""Reasons for consumed action feedback must not call a non-question a 提问."""
from __future__ import annotations

from birth.arbitrate import arbitrate
from birth.drive import infer_drive, prior_delivered_kind
from birth.openq_extract import extract_open_question
from birth.stance_org import default_org, default_stance
from birth.types import ActionFeedback, SessionAction, ThinContext

QUESTION = "先把这一步做了？"
RECALL = "记得，你说最近有点累，总觉得事情堆着，要是工作截止，心里也会紧。"
Q_EVIDENCE = "刚才那步更顺了。"
R_EVIDENCE = "上次的尝试对下一步有帮助"


def _feedback(action, evidence, effect="supports"):
    return ActionFeedback(
        action=action, action_order=0, evidence=evidence, span=evidence,
        scope="下一步", effect=effect, relation="report",
    )


def _ctx(action, evidence, effect="supports"):
    context = ThinContext()
    context.session_actions = [SessionAction(text=action, goal="")]
    context.action_feedback = [_feedback(action, evidence, effect)]
    return context


def _run(text, context):
    drive = infer_drive(text, context, understanding=None, input_signal=None)
    stance = default_stance(text, context, understanding=None)
    org = default_org(context, drive=drive, stance=stance, user_text=text, understanding=None)
    brief = arbitrate(drive, stance, org, context, user_text=text, understanding=None)
    return brief, drive


def test_kind_splits_question_from_recall():
    assert extract_open_question(QUESTION)
    assert prior_delivered_kind(QUESTION) == "提问"
    assert extract_open_question(RECALL) is None
    assert prior_delivered_kind(RECALL) == "那句"


def test_question_reason_still_says_提问():
    brief, drive = _run("嗯", _ctx(QUESTION, Q_EVIDENCE))
    assert Q_EVIDENCE in [item.evidence for item in drive.action_feedback_effective]
    assert f"同场提问「{QUESTION}」" in (drive.why or "")
    assert "先前提问「" in (brief.say_intent or "")
    assert "保留对方的空间" in (brief.say_intent or "")
    assert brief.focus_source == "本场行动反馈"


def test_recall_reason_does_not_say_提问():
    brief, drive = _run("嗯", _ctx(RECALL, R_EVIDENCE))
    assert R_EVIDENCE in [item.evidence for item in drive.action_feedback_effective]
    assert f"同场那句「{RECALL}」" in (drive.why or "")
    assert "提问" not in (drive.why or "")
    assert "提问" not in (brief.say_intent or "")
    assert "先前那句「" in (brief.say_intent or "")
    assert RECALL[:20] in (brief.say_intent or "")
    assert "保留对方的空间" in (brief.say_intent or "")
    assert brief.focus_source == "本场行动反馈"
    assert R_EVIDENCE in (brief.focus or "")


def test_obstructs_statement_keeps_direction_and_avoids_提问():
    support_brief, support_drive = _run("嗯", _ctx(RECALL, R_EVIDENCE, "supports"))
    brief, drive = _run("嗯", _ctx(RECALL, R_EVIDENCE, "obstructs"))
    assert "不要催逼" in (brief.say_intent or "")
    assert "提问" not in (drive.why or "")
    assert "提问" not in (brief.say_intent or "")
    assert drive.direction == support_drive.direction
    assert drive.salience == support_drive.salience


def test_two_reports_still_do_not_consume():
    context = ThinContext()
    context.session_actions = [
        SessionAction(text=QUESTION, goal=""),
        SessionAction(text="另一问还在吗？", goal=""),
    ]
    context.action_feedback = [
        _feedback(QUESTION, Q_EVIDENCE),
        ActionFeedback(
            action="另一问还在吗？", action_order=1, evidence="今天天气不错。",
            span="今天天气不错。", scope="下一步", effect="obstructs", relation="report",
        ),
    ]
    brief, drive = _run("嗯", context)
    assert drive.action_feedback_effective == ()
    assert "本场行动反馈" != brief.focus_source


def test_non_filler_does_not_yield_focus_but_keeps_tradeoff():
    context = _ctx(RECALL, R_EVIDENCE)
    brief, drive = _run("换个话题，我最近开始学做饭，但并不是每天都有空。", context)
    assert R_EVIDENCE in [item.evidence for item in drive.action_feedback_effective]
    assert brief.focus_source != "本场行动反馈"
    assert R_EVIDENCE not in (brief.focus or "")
    assert "保留对方的空间" in (brief.say_intent or "")
    assert "提问" not in (brief.say_intent or "")

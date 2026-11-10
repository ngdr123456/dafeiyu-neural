# -*- coding: utf-8 -*-
"""Recency-deictic action-report binding. No provider calls."""
from birth.types import SessionAction, ThinContext, ActionFeedback
from birth.input_contract import visible_actions, validate_action_report, InputSignal
from birth.input_sense import complement_recency_action_report, parse_recency_deictic_report
from birth.drive import infer_drive, is_neutral_filler


MAKEUP_HERS = [
    "事情堆着的时候，人确实容易觉得累。你是被哪几件事压着，还是说不上来，就是整体有点撑不住？",
    "工作截止带来的那种紧，往往不是事情本身多重，是时间一压上来，心里就没法松。你刚才说事情堆着，现在又提到截止，这两样叠在一起，确实容易让人绷着。",
    "换话题好。学做饭不用每天开火，有空做一顿、没空就先放一放，别把它也变成截止日期。你最近学的是哪类，简单能上手的，还是想练点硬菜？",
    "简单家常菜这个起点挺稳的，先从一两个顺手的菜反复做，比一次铺开好几样更容易留下来。",
    "记得，你说最近有点累，总觉得事情堆着；一碰到工作截止，心里就紧。",
]
RERUN_HERS = [
    "事情堆着的时候，人是会累的，不用硬撑着把它们一下子理清。",
    "学做饭不用赶成每天的任务。有空就做一次，哪怕只练一道，也比堆着不动强。",
    "记得，你说最近有点累，总觉得事情堆着。",
]
ZH = "上次的尝试对下一步有帮助。"
EN = "The previous attempt helped the next step."


def _ctx(hers):
    return ThinContext(session_actions=[SessionAction(text=t, goal="") for t in hers])


def _sig(**kw):
    fields = dict(
        act="tell", addressee="other", source="probe", provenance="probe",
        degraded=False, reason="", scope="conversation", confidence="high",
        quoted_or_negated=False,
    )
    fields.update(kw)
    return InputSignal(**fields)


def _run(signal, text, context, originally_unknown):
    actions = visible_actions(context)
    signal, raw = complement_recency_action_report(
        signal, text, actions, context, originally_unknown=originally_unknown)
    return validate_action_report(signal, text, context), raw, actions


def test_makeup_window_has_three_visible_actions():
    assert len(visible_actions(_ctx(MAKEUP_HERS))) == 3


def test_rerun_window_has_one_visible_action():
    assert len(visible_actions(_ctx(RERUN_HERS))) == 1


def test_makeup_incomplete_report_binds_latest():
    out, raw, _ = _run(_sig(
        action_report_relation="report", action_report_holder="user",
        action_report_asserted=True, action_report_span="上次的尝试对下一步有帮助",
        action_report_scope="下一步", action_report_effect="supports",
    ), ZH, _ctx(MAKEUP_HERS), False)
    assert out.action_report_relation == "report"
    assert out.action_report_order == 4
    assert out.action_report_action == MAKEUP_HERS[4]
    assert out.action_report_effect == "supports"
    assert raw is None


def test_makeup_unknown_deictic_binds_latest():
    out, raw, _ = _run(_sig(), ZH, _ctx(MAKEUP_HERS), True)
    assert out.action_report_relation == "report"
    assert out.action_report_order == 4
    assert out.action_report_action == MAKEUP_HERS[4]
    assert out.action_report_scope == "下一步"
    assert raw is not None


def test_rerun_unique_window_zh_and_en_still_bind():
    zh, _, _ = _run(_sig(), ZH, _ctx(RERUN_HERS), True)
    en, _, _ = _run(_sig(), EN, _ctx(RERUN_HERS), True)
    assert zh.action_report_order == 2 and zh.action_report_action == RERUN_HERS[2]
    assert en.action_report_order == 2 and en.action_report_scope == "the next step"


def test_another_and_specific_do_not_recency_bind():
    another = "另一次尝试对下一步有帮助。"
    specific = "你问我学哪类，对下一步有帮助。"
    assert parse_recency_deictic_report(another) is None
    assert parse_recency_deictic_report(specific) is None
    a, _, _ = _run(_sig(
        action_report_relation="report", action_report_holder="user",
        action_report_asserted=True, action_report_span="另一次尝试对下一步有帮助",
        action_report_scope="下一步", action_report_effect="supports",
    ), another, _ctx(MAKEUP_HERS), False)
    s, _, _ = _run(_sig(
        action_report_relation="report", action_report_holder="user",
        action_report_asserted=True, action_report_span="你问我学哪类，对下一步有帮助",
        action_report_scope="下一步", action_report_effect="supports",
    ), specific, _ctx(MAKEUP_HERS), False)
    assert a.action_report_relation == "unknown" and a.action_report_action == ""
    assert s.action_report_relation == "unknown" and s.action_report_action == ""


def test_explicit_bind_not_overwritten():
    out, _, _ = _run(_sig(
        action_report_relation="report", action_report_holder="user",
        action_report_asserted=True, action_report_action=MAKEUP_HERS[2],
        action_report_order=2, action_report_span="上次的尝试对下一步有帮助",
        action_report_scope="下一步", action_report_effect="supports",
    ), ZH, _ctx(MAKEUP_HERS), False)
    assert out.action_report_order == 2 and out.action_report_action == MAKEUP_HERS[2]


def test_no_candidate_does_not_invent():
    out, _, vis = _run(_sig(), ZH, ThinContext(session_actions=[]), True)
    assert vis == []
    assert out is None or (out.action_report_relation == "unknown" and out.action_report_action == "")


def test_duplicate_last_not_visible_no_bind():
    ctx = _ctx([MAKEUP_HERS[0], MAKEUP_HERS[4], MAKEUP_HERS[4]])
    assert not any(o == 2 for o, _ in visible_actions(ctx))
    out, _, _ = _run(_sig(), ZH, ctx, True)
    assert out is None or out.action_report_relation == "unknown"


def test_unique_consume_unchanged():
    two = ThinContext(
        session_actions=[
            SessionAction(text="第一问：要不要先练一道？", goal=""),
            SessionAction(text="第二问：今晚做不做？", goal=""),
        ],
        action_feedback=[
            ActionFeedback(action="第一问：要不要先练一道？", action_order=0,
                           evidence="e1", span="e1", scope="下一步", effect="supports",
                           relation="report"),
            ActionFeedback(action="第二问：今晚做不做？", action_order=1,
                           evidence="e2", span="e2", scope="下一步", effect="supports",
                           relation="report"),
        ],
    )
    one = ThinContext(
        session_actions=[SessionAction(text=MAKEUP_HERS[4], goal="")],
        action_feedback=[
            ActionFeedback(action=MAKEUP_HERS[4], action_order=0,
                           evidence=ZH, span=ZH, scope="下一步", effect="supports",
                           relation="report"),
        ],
    )
    assert is_neutral_filler("嗯")
    assert len(visible_actions(two)) >= 2
    assert not infer_drive("嗯", two).action_feedback_effective
    eff = infer_drive("嗯", one).action_feedback_effective
    assert len(eff) == 1 and eff[0].evidence == ZH


def test_medium_incomplete_report_promotes_and_validates():
    out, raw, _ = _run(_sig(
        confidence="medium",
        action_report_relation="report", action_report_holder="user",
        action_report_asserted=True, action_report_span="上次的尝试对下一步有帮助",
        action_report_scope="下一步", action_report_effect="supports",
    ), ZH, _ctx(MAKEUP_HERS), False)
    assert out.action_report_relation == "report"
    assert out.confidence == "high"
    assert out.action_report_order == 4
    assert out.action_report_action == MAKEUP_HERS[4]
    assert raw is None


def test_medium_already_bound_to_latest_promotes_and_validates():
    out, raw, _ = _run(_sig(
        confidence="medium",
        action_report_relation="report", action_report_holder="user",
        action_report_asserted=True, action_report_action=MAKEUP_HERS[4],
        action_report_order=4, action_report_span="上次的尝试对下一步有帮助",
        action_report_scope="下一步", action_report_effect="supports",
    ), ZH, _ctx(MAKEUP_HERS), False)
    assert out.action_report_relation == "report"
    assert out.confidence == "high"
    assert out.action_report_order == 4
    assert out.action_report_action == MAKEUP_HERS[4]
    assert raw is None


def test_explicit_older_medium_bind_not_overwritten():
    out, _, _ = _run(_sig(
        confidence="medium",
        action_report_relation="report", action_report_holder="user",
        action_report_asserted=True, action_report_action=MAKEUP_HERS[2],
        action_report_order=2, action_report_span="上次的尝试对下一步有帮助",
        action_report_scope="下一步", action_report_effect="supports",
    ), ZH, _ctx(MAKEUP_HERS), False)
    assert out.action_report_action == MAKEUP_HERS[2]
    assert out.action_report_order == 2
    assert out.action_report_relation == "unknown"
    assert out.confidence == "medium"


def test_live_consume_t3_medium_binds_latest():
    hers = [
        "先挑三道菜：番茄炒蛋、青椒土豆丝、蒜蓉青菜。做法就按“备料—下锅—调味”三步走：备料时把菜切好、调料先摆到手边；下锅先练火候，鸡蛋炒到刚凝固就盛出，土豆丝大火快炒；调味先只放盐和少量生抽，尝一口再补。每道菜连做两三次，记下哪一步手忙脚乱，下次只改那一步。想从哪道开始，我可以陪你把步骤拆得更细。",
        "那就按“家里有什么、一次能做完”来选：先看冰箱里现成的食材，挑一道能一锅出、备料不超过三样的。比如有番茄和鸡蛋就先做番茄炒蛋；有土豆和青椒就先做青椒土豆丝。你从哪道开始，我就把“备料—下锅—调味”里那一步拆得更细。",
    ]
    out, raw, _ = _run(_sig(
        confidence="medium",
        action_report_relation="report", action_report_holder="user",
        action_report_asserted=True,
        action_report_span="上次的尝试对下一步有帮助",
        action_report_scope="下一步", action_report_effect="supports",
    ), ZH, _ctx(hers), False)
    assert out.action_report_relation == "report"
    assert out.confidence == "high"
    assert out.action_report_order == 1
    assert out.action_report_action == hers[1]
    assert raw is None

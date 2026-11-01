"""工程师侧多轮闭环自测：固定剧本走完 birth.turn，断言 Brief/回流。

非听感验收、非 Mark 陪练。失败消息带 R{n}，便于指哪一轮断了。
"""

from __future__ import annotations

import pytest

from birth.articulate import (
    clear_llm_hook,
    set_llm_hook,
    set_stub_mode,
    validate,
)
from birth.llm_opencode import brief_to_prompt
from birth.pipeline import active_store, turn


_ENUM_LEAKS = (
    "pursue",
    "guard",
    "hold",
    "non_negotiable",
    "needs_clarify",
    "yieldable",
    "direction=",
    "salience=",
    "posture",
)


def _assert_no_enum_leak(prompt: str, round_tag: str) -> None:
    for bad in _ENUM_LEAKS:
        assert bad not in prompt, f"{round_tag}: brief_to_prompt 漏出 {bad!r}"


def _snap():
    ctx = active_store().context
    return {
        "facts": list(ctx.facts_this_session),
        "commits": list(ctx.last_commitments),
        "oq": list(ctx.open_questions),
    }


def test_multiturn_closed_loop_script():
    """同场 8 轮：招呼→开题→回指→承诺回流→改口→收束→好奇→身份。"""
    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    prev_facts = 0

    # R1 招呼
    tag = "R1 你好"
    r = turn("你好", stub=True)
    s = _snap()
    assert r.utterance, f"{tag}: 开口空"
    assert r.brief.drive.direction == "hold", f"{tag}: drive={r.brief.drive.direction}"
    assert r.brief.drive.salience == "low", f"{tag}: salience={r.brief.drive.salience}"
    assert r.brief.dominant == "drive", f"{tag}: dominant={r.brief.dominant}"
    assert s["commits"] == [], f"{tag}: 不该有承诺 {s['commits']}"
    assert s["oq"] == [], f"{tag}: 不该有悬问 {s['oq']}"
    assert len(s["facts"]) > prev_facts, f"{tag}: facts 未累积"
    _assert_no_enum_leak(brief_to_prompt(r.brief), tag)
    prev_facts = len(s["facts"])

    # R2 开题
    tag = "R2 我想聊星空"
    r = turn("我想聊星空", stub=True)
    s = _snap()
    assert r.brief.drive.direction == "pursue", f"{tag}: drive={r.brief.drive.direction}"
    assert r.brief.drive.salience == "mid", f"{tag}: salience"
    assert "星空" in r.brief.say_intent, f"{tag}: say_intent 无星空"
    assert "星空" in r.utterance, f"{tag}: utterance 无星空"
    assert len(s["facts"]) > prev_facts, f"{tag}: facts 未累积"
    assert any("星空" in f for f in s["facts"]), f"{tag}: facts 无星空"
    _assert_no_enum_leak(brief_to_prompt(r.brief), tag)
    prev_facts = len(s["facts"])

    # R3 回指
    tag = "R3 刚才那个还记得吗"
    r = turn("刚才那个还记得吗", stub=True)
    s = _snap()
    assert r.brief.drive.direction == "pursue", f"{tag}: drive={r.brief.drive.direction}"
    assert "回指" in r.brief.say_intent or "本场痕迹" in r.brief.say_intent, (
        f"{tag}: say_intent 未点回指 {r.brief.say_intent!r}"
    )
    assert "星空" in r.utterance, f"{tag}: utterance 应接星空"
    assert "嗯，听着" not in r.utterance, f"{tag}: 掉成空接"
    assert len(s["facts"]) > prev_facts, f"{tag}: facts 未累积"
    _assert_no_enum_leak(brief_to_prompt(r.brief), tag)
    prev_facts = len(s["facts"])

    # R4 用户催答应 → hook 台上兑现句，回流承诺
    tag = "R4 你答应晚点再聊"
    set_stub_mode(False)
    set_llm_hook(lambda _b: "好，我晚点再跟你聊星空。")
    try:
        r = turn("你答应晚点再聊", stub=False)
    finally:
        clear_llm_hook()
        set_stub_mode(True)
    s = _snap()
    assert r.utterance, f"{tag}: 开口空"
    assert any("晚点" in c and "星空" in c for c in s["commits"]), (
        f"{tag}: 承诺未回流 {s['commits']}"
    )
    assert len(s["facts"]) > prev_facts, f"{tag}: facts 未累积"
    _assert_no_enum_leak(brief_to_prompt(r.brief), tag)
    prev_facts = len(s["facts"])

    # R5 改口
    tag = "R5 那刚才说的不算"
    r = turn("那刚才说的不算", stub=True)
    s = _snap()
    assert r.brief.stance.posture == "non_negotiable", (
        f"{tag}: stance={r.brief.stance.posture}"
    )
    assert r.brief.dominant == "meaning", f"{tag}: dominant={r.brief.dominant}"
    assert s["commits"], f"{tag}: 承诺被清掉了"
    assert "嗯，听着" not in r.utterance, f"{tag}: 掉成空接"
    assert len(s["facts"]) > prev_facts, f"{tag}: facts 未累积"
    _assert_no_enum_leak(brief_to_prompt(r.brief), tag)
    prev_facts = len(s["facts"])

    # R6 收束
    tag = "R6 够了先这样"
    r = turn("够了先这样", stub=True)
    s = _snap()
    assert r.brief.drive.direction != "pursue", (
        f"{tag}: 收束不该还 pursue，got {r.brief.drive.direction}"
    )
    assert r.brief.drive.direction in {"hold", None}, (
        f"{tag}: drive={r.brief.drive.direction}"
    )
    assert len(s["facts"]) > prev_facts, f"{tag}: facts 未累积"
    _assert_no_enum_leak(brief_to_prompt(r.brief), tag)
    prev_facts = len(s["facts"])

    # R7 好奇
    tag = "R7 为什么会闪"
    r = turn("为什么会闪", stub=True)
    s = _snap()
    assert r.brief.drive.direction == "pursue", f"{tag}: drive={r.brief.drive.direction}"
    assert r.brief.drive.salience == "high", f"{tag}: salience"
    assert "好奇" in r.brief.drive.why, f"{tag}: why 无好奇"
    assert any("为什么会闪" in q or "待接" in q for q in s["oq"]), (
        f"{tag}: 悬问未挂起 {s['oq']}"
    )
    assert len(s["facts"]) > prev_facts, f"{tag}: facts 未累积"
    _assert_no_enum_leak(brief_to_prompt(r.brief), tag)
    prev_facts = len(s["facts"])

    # R8 身份问（同场，不 new_session）
    tag = "R8 你是代码吗"
    r = turn("你是代码吗", stub=True)
    s = _snap()
    assert r.brief.dominant == "org", f"{tag}: dominant={r.brief.dominant}"
    assert any(k in r.brief.say_intent for k in ("代码", "程序", "模型")), (
        f"{tag}: say_intent 未点身份问 {r.brief.say_intent!r}"
    )
    assert validate(r.brief, r.utterance) == [], (
        f"{tag}: validate 拒 {validate(r.brief, r.utterance)}"
    )
    low = r.utterance.lower()
    for bad in ("glm", "我是代码", "我是程序", "ai 助手"):
        assert bad not in low and bad not in r.utterance, (
            f"{tag}: 开口自报/说明书味 {r.utterance!r}"
        )
    assert len(s["facts"]) > prev_facts, f"{tag}: facts 未累积"
    _assert_no_enum_leak(brief_to_prompt(r.brief), tag)


def test_multiturn_optional_deepseek_one_round():
    """可选：一轮 deepseek 只查 source + validate，不把「像人」当过关。"""
    from birth import llm_deepseek as ds

    if not ds.available():
        pytest.skip("deepseek 不可用")

    set_stub_mode(False)
    clear_llm_hook()
    try:
        active_store().new_session()
        r = turn("我想聊星空", stub=False)
        assert r.articulate_source == "deepseek", (
            f"期望 deepseek，got {r.articulate_source}"
        )
        assert validate(r.brief, r.utterance) == [], validate(r.brief, r.utterance)
        _assert_no_enum_leak(brief_to_prompt(r.brief), "deepseek一轮")
    finally:
        set_stub_mode(True)
        clear_llm_hook()

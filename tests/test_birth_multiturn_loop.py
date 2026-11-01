"""工程师侧多轮闭环自测：固定剧本逐步断言台下 Brief／回流。

闸门（推进官）：
1) 每轮有 dominant／direction／回流／must_not_pretend，禁止只 assert utterance 非空；
2) 至少一轮否定承诺 → meaning 主导且话不顺着改口；至少一轮身份问 → validate／reject 可断言；
3) 假绿风险见模块末尾 FALSE_GREEN_RISKS（交付报告同步）。

非听感验收。失败消息带 R{n}。
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

# 假绿风险（交付报告）：pytest 全绿本身不算过闸
FALSE_GREEN_RISKS = """
- stub 开口固定，听感／像人完全未测；deepseek 可选测只查 source+validate。
- R4 现走 stub 显式「催答应」模板（仅 say_intent 命中才答应）；真 LLM 是否会自发答应仍未测。
- R5 drive 因「刚才」回指命中为 pursue，承诺护卫 guard 被挤掉——本测认 meaning+stance，不假装 drive=guard。
- R6/R7 有未兑现承诺时 dominant 常为 meaning，收束／好奇的 drive 方向对了但说辞仍偏守承诺模板。
- must_not_pretend 是仲裁常量列表，每轮都有「自述是代码」≠ 开口真被拦死；身份轮另用 validate 对拍。
- 枚举不漏只查 brief_to_prompt 字面；say_intent／utterance 里的人话不在此列。
"""


def _assert_core_understage(r, *, tag: str, dominant, direction, salience=None,
                            commits_nonempty=None, oq_expect=None,
                            facts_gt: int | None = None) -> dict:
    """每轮台下硬期望：dominant／drive／must_not_pretend／回流／prompt 无枚举。"""
    b = r.brief
    assert r.utterance, f"{tag}: utterance 空"
    assert b.dominant == dominant, f"{tag}: dominant want={dominant} got={b.dominant}"
    assert b.drive is not None, f"{tag}: drive 缺失"
    assert b.drive.direction == direction, (
        f"{tag}: direction want={direction} got={b.drive.direction}"
    )
    if salience is not None:
        assert b.drive.salience == salience, (
            f"{tag}: salience want={salience} got={b.drive.salience}"
        )
    assert "自述是代码" in b.must_not_pretend, (
        f"{tag}: must_not_pretend 缺『自述是代码』 {b.must_not_pretend}"
    )
    assert "无来源装经历" in b.must_not_pretend, (
        f"{tag}: must_not_pretend 缺『无来源装经历』"
    )
    prompt = brief_to_prompt(b)
    for bad in _ENUM_LEAKS:
        assert bad not in prompt, f"{tag}: brief_to_prompt 漏出 {bad!r}"

    ctx = active_store().context
    snap = {
        "facts": list(ctx.facts_this_session),
        "commits": list(ctx.last_commitments),
        "oq": list(ctx.open_questions),
    }
    if facts_gt is not None:
        assert len(snap["facts"]) > facts_gt, (
            f"{tag}: facts 未累积 {facts_gt}→{len(snap['facts'])}"
        )
    if commits_nonempty is True:
        assert snap["commits"], f"{tag}: 期望承诺非空"
    elif commits_nonempty is False:
        assert snap["commits"] == [], f"{tag}: 期望无承诺 got={snap['commits']}"
    if oq_expect == "empty":
        assert snap["oq"] == [], f"{tag}: 期望无悬问 got={snap['oq']}"
    elif oq_expect == "nonempty":
        assert snap["oq"], f"{tag}: 期望悬问非空"
    return snap


def test_multiturn_closed_loop_script():
    """同场 8 轮逐步台下期望；含否定承诺 + 身份 validate。"""
    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    prev = 0

    tag = "R1 你好"
    r = turn("你好", stub=True)
    s = _assert_core_understage(
        r, tag=tag, dominant="drive", direction="hold", salience="low",
        commits_nonempty=False, oq_expect="empty", facts_gt=prev,
    )
    prev = len(s["facts"])

    tag = "R2 我想聊星空"
    r = turn("我想聊星空", stub=True)
    s = _assert_core_understage(
        r, tag=tag, dominant="drive", direction="pursue", salience="mid",
        facts_gt=prev,
    )
    assert "星空" in r.brief.say_intent, f"{tag}: say_intent 无星空"
    assert "星空" in r.utterance, f"{tag}: utterance 无星空"
    assert any("星空" in f for f in s["facts"]), f"{tag}: facts 无星空"
    prev = len(s["facts"])

    tag = "R3 刚才那个还记得吗"
    r = turn("刚才那个还记得吗", stub=True)
    s = _assert_core_understage(
        r, tag=tag, dominant="drive", direction="pursue", salience="mid",
        facts_gt=prev,
    )
    assert "回指" in r.brief.say_intent or "本场痕迹" in r.brief.say_intent, (
        f"{tag}: say_intent 未点回指"
    )
    assert "星空" in r.utterance, f"{tag}: 回指未接到星空"
    assert "嗯，听着" not in r.utterance, f"{tag}: 空接"
    prev = len(s["facts"])

    tag = "R4 你答应晚点再聊"
    r = turn("你答应晚点再聊", stub=True)
    s = _assert_core_understage(
        r, tag=tag, dominant="drive", direction=None, salience="low",
        commits_nonempty=True, facts_gt=prev,
    )
    assert r.articulate_source == "stub", f"{tag}: 应用 stub 非 hook，got {r.articulate_source}"
    assert "晚点" in r.utterance and "星空" in r.utterance, (
        f"{tag}: stub 承诺句不对 {r.utterance!r}"
    )
    assert any("晚点" in c and "星空" in c for c in s["commits"]), (
        f"{tag}: 承诺回流字段不对 {s['commits']}"
    )
    prev = len(s["facts"])

    # 否定承诺：meaning + 不顺着改口
    tag = "R5 那刚才说的不算"
    r = turn("那刚才说的不算", stub=True)
    s = _assert_core_understage(
        r, tag=tag, dominant="meaning", direction="pursue",
        commits_nonempty=True, facts_gt=prev,
    )
    assert r.brief.stance.posture == "non_negotiable", (
        f"{tag}: stance want=non_negotiable got={r.brief.stance.posture}"
    )
    assert "改口" in r.brief.say_intent or "说过的话" in r.brief.say_intent, (
        f"{tag}: say_intent 未守承诺 {r.brief.say_intent!r}"
    )
    # 话不顺着改口
    assert "不算" not in r.utterance or "不当" in r.utterance or "不跟着" in r.utterance, (
        f"{tag}: 开口疑似顺着改口 {r.utterance!r}"
    )
    assert any(k in r.utterance for k in ("不当没说过", "不跟着改口", "还在")), (
        f"{tag}: 开口未钉住承诺 {r.utterance!r}"
    )
    assert "嗯，听着" not in r.utterance, f"{tag}: 空接"
    prev = len(s["facts"])

    tag = "R6 够了先这样"
    r = turn("够了先这样", stub=True)
    s = _assert_core_understage(
        r, tag=tag, dominant="meaning", direction="hold", salience="low",
        commits_nonempty=True, facts_gt=prev,
    )
    assert r.brief.drive.direction != "pursue", f"{tag}: 收束仍 pursue"
    prev = len(s["facts"])

    tag = "R7 为什么会闪"
    r = turn("为什么会闪", stub=True)
    s = _assert_core_understage(
        r, tag=tag, dominant="meaning", direction="pursue", salience="high",
        oq_expect="nonempty", facts_gt=prev,
    )
    assert "好奇" in r.brief.drive.why, f"{tag}: why 无好奇"
    assert any("为什么会闪" in q or "待接" in q for q in s["oq"]), (
        f"{tag}: 悬问回流不对 {s['oq']}"
    )
    prev = len(s["facts"])

    # 身份问：org + validate；同场灾难句应被 validate 拒
    tag = "R8 你是代码吗"
    r = turn("你是代码吗", stub=True)
    s = _assert_core_understage(
        r, tag=tag, dominant="org", direction="guard", salience="mid",
        facts_gt=prev,
    )
    assert r.brief.stance.posture == "non_negotiable", (
        f"{tag}: stance={r.brief.stance.posture}"
    )
    assert any(k in r.brief.say_intent for k in ("代码", "程序", "模型")), (
        f"{tag}: say_intent 未点身份"
    )
    reasons = validate(r.brief, r.utterance)
    assert reasons == [], f"{tag}: 合法 stub 被 validate 误杀 {reasons}"
    # reject 路径可断言：同 Brief 塞灾难句必须非空 reasons
    disaster = "我是 AI 助手，基于 GLM 模型为你服务。"
    reject_reasons = validate(r.brief, disaster)
    assert reject_reasons, (
        f"{tag}: 灾难句应走 reject／validate 非空，got {reject_reasons!r}"
    )


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
        assert "自述是代码" in r.brief.must_not_pretend
        prompt = brief_to_prompt(r.brief)
        for bad in _ENUM_LEAKS:
            assert bad not in prompt, bad
    finally:
        set_stub_mode(True)
        clear_llm_hook()


def test_false_green_risks_documented():
    """闸门第 3 条：假绿风险写进交付物，防止空文档。"""
    assert "stub" in FALSE_GREEN_RISKS
    assert "R5" in FALSE_GREEN_RISKS
    assert "must_not_pretend" in FALSE_GREEN_RISKS

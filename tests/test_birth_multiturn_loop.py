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
- `_accept_draft` 用 extract 拒收**仅当** Brief.press_commit；禁止只靠 say_intent 中文子串；禁止扩词表／通用堵嘴；不扩 commit_extract 词表。
- stub 开口固定，听感／像人完全未测；deepseek 可选测只查 source+validate。
- R4 多轮剧本仍 stub=True 保回归；另有 hook／可选 deepseek 测催答应可提取。LLM 空壳答应会被拒收并 stub 兜底，但真网波动／模型跑偏仍可能偶发。
- R5 已闭合：同场未兑现承诺＋改口否定（含「刚才」回指）→ drive=guard；无承诺纯回指仍 pursue。
- R6/R7 已闭合：有承诺时收束／好奇经 commit_hold_with_drive 双写动力＋薄守诺；改口仍纯守诺（R5）。
- stub 主路径已改读 Brief 标记／posture（org→press_commit→commit_hold_with_drive 读 drive.direction/why→needs_clarify→non_negotiable 守诺），say_intent 改无关文案仍走对模板（test_birth_phase1 守恒测）；残余：打开话题／收束／空追／回指兜底仍读 say_intent 中文子串，未全结构化。
- must_not_pretend 列表在场≠闸常开：装经历亲历拒收**仅** org_conflicts 含该项时跑（非常开）；形状不含裸「我昨天／我去过」。substrate 仍按 must_not_pretend 对拍。残余：未对每轮自动注入灾难句抽检。
- 枚举漏检已对拍 utterance：validate 拦 pursue／guard／hold（独立英文词）与 non_negotiable 等标识；brief_to_prompt 仍查。残余：未穷尽一切内部符号别名。
- 好奇挂起已闭合：pipeline 读 `openq_curiosity_hang`，不再扫 CURIOSITY_MARKS；残余：drive 内部仍用 MARKS 作输入侧线索。
- 换题 clear 已闭合：arbitrate 写 `openq_clear`（放下标记或 drive `_extract_open_topic`），pipeline 读标记 clear，不再扫放下词表；残余：输入侧线索仍是固定词表（PUTDOWN_MARKS／OPEN_TOPIC_PREFIXES，未扩）。
- drive 主路径先读结构化线索（DriveCues：承诺在场／悬问／好奇挂起／session_ok）；冲突时结构化优先（test_birth_drive_structured）。残余：无结构信号时仍扫输入侧 MARKS 兜底（招呼／收束／好奇／失望／空追），词表固定未扩。
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
    # 收紧 clear 后，R2 stub 悬问可能仍在 → drive 可 pursue 悬问话头；承诺回流才是本轮硬点
    assert r.brief.dominant == "drive", f"{tag}: dominant={r.brief.dominant}"
    assert r.brief.drive.direction in {None, "pursue"}, (
        f"{tag}: direction={r.brief.drive.direction}"
    )
    s = _assert_core_understage(
        r, tag=tag, dominant="drive",
        direction=r.brief.drive.direction,  # 接受 None 或 pursue
        salience=r.brief.drive.salience,
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
        r, tag=tag, dominant="meaning", direction="guard", salience="mid",
        commits_nonempty=True, facts_gt=prev,
    )
    assert "要护" in r.brief.drive.why or "没兑现" in r.brief.drive.why, (
        f"{tag}: why 未点已有要护 {r.brief.drive.why!r}"
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
    assert r.brief.commit_hold_with_drive, f"{tag}: 缺 commit_hold_with_drive"
    assert "不加码" in r.brief.say_intent or "收束" in r.brief.say_intent, (
        f"{tag}: say_intent 无收束动力 {r.brief.say_intent!r}"
    )
    assert "约定还在" in r.brief.say_intent or "不假装消失" in r.brief.say_intent, (
        f"{tag}: say_intent 无薄守诺 {r.brief.say_intent!r}"
    )
    assert "不当没说过" not in r.utterance, f"{tag}: stub 仍纯守诺 {r.utterance!r}"
    assert "先这样" in r.utterance or "回头" in r.utterance, (
        f"{tag}: stub 未收束 {r.utterance!r}"
    )
    assert "还在" in r.utterance, f"{tag}: stub 无约定痕迹 {r.utterance!r}"
    prev = len(s["facts"])

    tag = "R7 为什么会闪"
    r = turn("为什么会闪", stub=True)
    s = _assert_core_understage(
        r, tag=tag, dominant="meaning", direction="pursue", salience="high",
        oq_expect="nonempty", facts_gt=prev,
    )
    assert "好奇" in r.brief.drive.why, f"{tag}: why 无好奇"
    assert r.brief.commit_hold_with_drive, f"{tag}: 缺 commit_hold_with_drive"
    assert "好奇" in r.brief.say_intent, (
        f"{tag}: say_intent 无好奇 {r.brief.say_intent!r}"
    )
    assert "约定还在" in r.brief.say_intent or "不假装消失" in r.brief.say_intent, (
        f"{tag}: say_intent 无薄守诺 {r.brief.say_intent!r}"
    )
    assert "不当没说过" not in r.utterance, f"{tag}: stub 仍纯守诺 {r.utterance!r}"
    assert any(k in r.utterance for k in ("勾着", "哪一头", "问")), (
        f"{tag}: stub 未点好奇 {r.utterance!r}"
    )
    assert "还在" in r.utterance, f"{tag}: stub 无约定痕迹 {r.utterance!r}"
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




def test_press_commitment_hook_extractable():
    """催答应 + stub=False：可控 hook 出可提取承诺，source=hook。"""
    from birth.commit_extract import extract_commitment

    set_stub_mode(False)
    set_llm_hook(lambda _b: "好，我晚点再跟你聊星空。")
    try:
        active_store().new_session()
        turn("我想聊星空", stub=True)  # 铺本场话头（stub 即可）
        set_stub_mode(False)
        set_llm_hook(lambda _b: "好，我晚点再跟你聊星空。")
        r = turn("你答应晚点再聊", stub=False)
        assert "催一个可核对的约定" in r.brief.say_intent
        assert r.articulate_source == "hook", r.articulate_source
        assert extract_commitment(r.utterance), r.utterance
        assert any("晚点" in c and "星空" in c for c in active_store().pending_commitments())
        from birth.llm_opencode import brief_to_prompt
        prompt = brief_to_prompt(r.brief)
        assert "可核对的约定" in prompt
        assert "宁缺毋滥" in prompt
        for bad in ("pursue", "guard", "non_negotiable"):
            assert bad not in prompt
    finally:
        clear_llm_hook()
        set_stub_mode(True)


def test_press_commitment_empty_llm_falls_to_stub_extractable():
    """催答应：LLM/hook 空壳或不可提取 → stub_fallback，仍可 extract。"""
    from birth.commit_extract import extract_commitment

    set_stub_mode(False)
    # 通过 validate 但不含约定形状 → 应被 _accept_draft 拒收
    set_llm_hook(lambda _b: "嗯，知道了，你先说吧。")
    try:
        active_store().new_session()
        turn("我想聊星空", stub=True)
        set_stub_mode(False)
        set_llm_hook(lambda _b: "嗯，知道了，你先说吧。")
        r = turn("你答应晚点再聊", stub=False)
        assert r.articulate_source in {"stub_fallback", "reject_self_id"}, r.articulate_source
        assert extract_commitment(r.utterance), r.utterance
        assert any("晚点" in c for c in active_store().pending_commitments())
    finally:
        clear_llm_hook()
        set_stub_mode(True)


def test_press_commitment_optional_deepseek_extractable():
    """可选：真 DeepSeek 催答应一轮，可提取或至少 stub_fallback 可提取。"""
    from birth import llm_deepseek as ds
    from birth.commit_extract import extract_commitment

    if not ds.available():
        pytest.skip("deepseek 不可用")

    clear_llm_hook()
    set_stub_mode(False)
    try:
        active_store().new_session()
        turn("我想聊星空", stub=True)
        set_stub_mode(False)
        r = turn("你答应晚点再聊", stub=False)
        assert "催一个可核对的约定" in r.brief.say_intent
        assert r.articulate_source in {
            "deepseek", "opencode", "stub_fallback", "reject_self_id"
        }, r.articulate_source
        assert extract_commitment(r.utterance), (
            f"source={r.articulate_source} utt={r.utterance!r}"
        )
        assert active_store().pending_commitments()
    finally:
        set_stub_mode(True)
        clear_llm_hook()

def test_false_green_risks_documented():
    """闸门第 3 条：假绿风险写进交付物，防止空文档。"""
    assert "stub" in FALSE_GREEN_RISKS
    assert "R5" in FALSE_GREEN_RISKS
    assert "must_not_pretend" in FALSE_GREEN_RISKS
    assert "openq_clear" in FALSE_GREEN_RISKS
    assert "say_intent" in FALSE_GREEN_RISKS


def test_stub_main_path_reads_markers_and_posture():
    """stub 主路径读 Brief 标记／posture：say_intent 改无关文案仍走对模板。"""
    from birth.articulate import _template_utterance
    from birth.types import DriveSignal, StanceSignal

    set_stub_mode(True)
    clear_llm_hook()
    try:
        active_store().new_session()
        turn("我想聊星空", stub=True)  # 铺本场话头 + 承诺

        # press_commit 标记在、say_intent 无催答应子串 → 仍约定句（读标记）
        b_press = turn("你答应晚点再聊", stub=True).brief
        assert b_press.press_commit
        assert "催一个可核对的约定" in b_press.say_intent
        b_press.say_intent = "【文案已改】与催答应毫无关系的一句话"
        assert "晚点" in _template_utterance(b_press)

        # needs_clarify posture 在、say_intent 无升华子串 → 仍不空壳口径
        b_nc = turn("你一定觉得人生很有意义", stub=True).brief
        assert b_nc.stance.posture == "needs_clarify"
        b_nc.say_intent = "【文案已改】与升华口径无关的一句话"
        assert "鸡汤" in _template_utterance(b_nc)
    finally:
        set_stub_mode(True)
        clear_llm_hook()

    # non_negotiable + 同场承诺在 → 守诺模板；say_intent 子串不是主路径
    b_deny = _tampered_deny_brief()
    out = _template_utterance(b_deny)
    assert "不当没说过" in out or "不跟着改口" in out, out


def _tampered_deny_brief():
    """构造改口否定轮的 Brief（posture/stake/commitments 结构化字段在位）。"""
    from birth.types import DriveSignal, StanceSignal, ThoughtBrief, ThinContext
    return ThoughtBrief(
        dominant="meaning",
        drive=DriveSignal(direction="guard", salience="mid", why="已有要护"),
        stance=StanceSignal(posture="non_negotiable", stake="先守同场说过的话"),
        context=ThinContext(last_commitments=["同场里说好这轮先补月亮的事"]),
        say_intent="【文案已改】与守诺子串无关的一句话",
    )

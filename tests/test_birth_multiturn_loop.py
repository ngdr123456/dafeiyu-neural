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
    "differentiated",
    "non_negotiable",
    "needs_clarify",
    "yieldable",
    "direction=",
    "salience=",
    "posture",
    "posture=",
    "stake=",
    "grain=",
    "stance.posture",
    "hold_same_field",
    "press_commit",
    "commit_deny",
    "commit_resolve",
    "commit_deliverable",
    "commit_deliver_intent",
    "commit_hold_with_drive",
    "openq_resolve",
    "openq_curiosity_hang",
    "openq_clear",
    "curiosity_hang_pending",
    "commitment_deny_pending",
    "drive_greet_pending",
    "drive_hold_pending",
    "drive_curiosity_pending",
    "drive_open_topic_pending",
    "drive_disappoint_pending",
    "drive_empty_stage_pending",
    "drive_topic_continue_pending",
    "drive_callback_pending",
    "drive_bypass",
    "drive_prior_commit_pending",
    "drive_prior_callback_pending",
    "drive_prior_press_pending",
    "drive_identity_ask_pending",
    "OrgConstraint",
    "ThinContext",
    "PriorSessionTrace",
    "facts_this_session",
    "prior_session",
    "commitments_pending",
    "commitments_resolved",
    "last_commitments",
    "open_questions",
    "birth_memory",
    "ended_at",
    "cannot_fake",
    "articulate_source",
    "stub_fallback",
    "articulate_reject_count",
    "last_reject_reasons",
    "articulate_reject_recovered",
    "articulate_reject",
    "reject_count",
    "开口拒收回流｜",
    "other_private_unfounded",
)

# 假绿风险（交付报告）：pytest 全绿本身不算过闸
FALSE_GREEN_RISKS = """
- 身份询问：固定句式与明确自述线索均不穷尽，换一种问法或身份描述可能漏识别；同场承诺存在时 §6 guard 可优先，身份 flag 仍记录。
- `_accept_draft` 用 extract 拒收**仅当** Brief.press_commit；禁止只靠 say_intent 中文子串；禁止扩词表／通用堵嘴；不扩 commit_extract 词表。
- stub 开口固定，听感／像人完全未测；deepseek 可选测只查 source+validate。
- R4 多轮剧本仍 stub=True 保回归；另有 hook／可选 deepseek 测催答应可提取。LLM 空壳答应会被拒收并 stub 兜底，但真网波动／模型跑偏仍可能偶发。
- R5 已闭合：同场未兑现承诺＋改口否定（含「刚才」回指）→ drive=guard；无承诺纯回指仍 pursue。
- R6/R7 已闭合：有承诺时收束／好奇经 commit_hold_with_drive 双写动力＋薄守诺；改口仍纯守诺（R5）。
- stub 主路径已改读 Brief 标记／posture（org→press_commit→commit_hold_with_drive 读 drive.direction/why→needs_clarify→non_negotiable 守诺），say_intent 改无关文案仍走对模板（test_birth_phase1 守恒测）；开话题／收束／空追／回指 stub 主路径已改读结构：ThinContext.drive_open_topic_pending／drive_hold_pending／drive_empty_stage_pending／drive_disappoint_pending／drive_callback_pending 或 drive.why 形状（想要打开｜缺口在外；喜欢/满足｜不必再追；重复空追；回指同场｜本场已有痕迹接），say_intent「新打开的话头」／收束／「先停硬追」／「回指｜本场痕迹」子串仅无结构兜底。残余：无 flag／无 why 形状时仍 say_intent 兜底。
- must_not_pretend 装经历闸已改常开：validate／`_accept_draft` 读 Brief.must_not_pretend 含「无来源装经历」即跑亲历检测（不再依赖 org_conflicts）；形状仍 `_claims_unfounded_lived_bio`（不含裸「我昨天／我去过」），未扩词表；亲历灾难参数化顺手补现闸应拦样本。substrate「自述是代码」参数化灾难注入已扩换皮对拍（我是语言模型／我就是ChatGPT／作为AI助手我…／我由代码驱动／底层语言模型／计算机里跑 等）；说明书产品名闭集（ChatGPT|GPT|GLM|AI助手|智谱等）**须带自指**（我是／我就是／这边是／作为…我）才拦，裸谈产品名放行（我想聊聊ChatGPT／GPT这个名字挺怪／有人用AI助手写稿）；「我由代码|程序|模型驱动」自指形状保留。每轮 `_assert_core_understage` 对代码灾难句＋亲历灾难句均注入真拒。残余：未声称穷尽一切换皮／别名／自指变体；裸「基于…模型」无自指主语仍不拦；装经历形状固定未扩词表。
- 枚举漏检已收窄并补对拍：validate 拦 pursue／guard／hold／differentiated（独立英文词）、direction=／posture=／stake=／grain=／dominant=／salience=／stance.posture 等字段形，以及 hold_same_field、press_commit、commit_*、openq_*、curiosity_hang_pending、commitment_deny_pending、drive_*_pending／drive_bypass、OrgConstraint、ThinContext、facts_this_session／last_commitments／open_questions、cannot_fake、articulate_source、stub_fallback 等工程师标识与中文内部 why／旁路指纹（回指同场｜／想要打开｜／工程师旁路）；brief_to_prompt 仍查。残余：未声称穷尽一切换皮别名／未来新字段；裸 salience 值（low／mid／high）与裸 dominant（drive／meaning／org）因易误杀普通英文未拦。
- 好奇挂起已闭合：pipeline 读 `openq_curiosity_hang`，不再扫 CURIOSITY_MARKS；默认只置 `curiosity_hang_pending`＋挂 openq clip，**不强制**写「待接的话头：」前缀（drive／stub 已读 flag）。残余：无 flag 时仍可用「待接的话头：」前缀兜底（兼容旧快照／`drive_cues_from_context`）；台上话术未变；drive 内部仍用 MARKS 作输入侧线索。
- 换题 clear 已闭合：arbitrate 写 `openq_clear`（放下标记或 drive `_extract_open_topic`），pipeline 读标记 clear，不再扫放下词表；残余：输入侧线索仍是固定词表（PUTDOWN_MARKS／OPEN_TOPIC_PREFIXES，未扩）。
- drive 主路径先读结构化线索（DriveCues：承诺在场／悬问／好奇挂起 flag（前缀兜底）／session_ok／drive_greet_pending／drive_hold_pending／drive_open_topic_pending／drive_curiosity_pending／drive_disappoint_pending／drive_empty_stage_pending／drive_topic_continue_pending／drive_callback_pending）；冲突时结构化优先（test_birth_drive_structured）。非 S3 主分支已全改读 ThinContext flag（pipeline 写；上游 structured_drive_* 或无结构时词表／facts 兜底写入）：招呼 hold／收束 hold／打开话题 pursue／好奇 pursue／失望 guard／空台 hold／话题延续 pursue／回指 pursue。「非 S3 仍 MARKS」大条已收；回指单独 ThinContext flag 已闭合。DRIVE_V1 §6 已钉：同场 last_commitments 非空时，§6 guard 先于 S8–S11；写入侧有承诺不置空台／话题／失望／回指 flag；turn 空台＋承诺与 structured_topic_continue／callback＋承诺均仍 guard。残余：无 flag 时写入／drive 仍词表或 facts 兜底（DISAPPOINT／_EMPTY_STAGE／话题词／BACKREF_MARKS 等）；词表固定未扩；S4–S7（招呼／收束／打开／好奇）仍可先于 §6（规格顺序）。
- drive 改口→guard 主路径已改读 ThinContext.commitment_deny_pending；写入侧已前移：turn 初先吃 `structured_commit_deny` kwarg，再 early stance 守诺结构（`structured_deny_from_stance`，与 Brief.commit_deny 同条件）同轮置 flag；有结构时写入不扫 COMMIT_DENY_MARKS；词表仅真无结构时兜底（未扩）。残余：early stance／drive 在无 flag 时仍可能自扫 `_denies_commitment`（层内兜底）。
- stance／Org 守诺主路径已改读 ThinContext.commitment_deny_pending（承诺在场＋flag → non_negotiable＋hold_same_field＋stake 字段取值）；Org grain 读结构化 stance.posture／commitments，不扫改口词表；COMMIT_DENY_MARKS 仅无 flag 时兜底（未扩）。写入侧假绿已闭合（early stance 结构前移）。arbitrate／articulate Brief 侧守诺已改读结构：StanceSignal.hold_same_field／Brief.commit_deny／Brief.hold_same_field（stake 中文常量「先守同场说过的话」仅作字段取值／无 bool 时精确相等兜底，不作唯一闸）。残余：stance／drive 无 flag 时层内词表兜底；无 hold_same_field bool 的旧 StanceSignal 仍可靠 stake==常量兜底。
- 动力工程师旁路（BIRTH_DRIVE_BYPASS／NEUTRAL、turn(drive_bypass=True)、ThinContext.drive_bypass）强制 hold；旁路非听感验收；默认关＝现网一致。
- CLI REPL：无参进多轮；首轮 new_session=True，/new 清场；默认 LLM，--stub 全程模板。残余：REPL 非听感验收；真 LLM 多轮波动未测；input EOF／中断仅工程师通道。
- 跨场薄记忆（MEMORY_V1）：本地 JSON（默认 ~/.dafeiyu/birth_memory.json／BIRTH_MEMORY_PATH）；REPL 默认开、`--no-memory` 关、单轮默认关；新场读入 `ThinContext.prior_session`；`drive_prior_commit_pending`（filler soft hold，不强制开口）／`drive_prior_callback_pending`（有痕迹才 pursue）／`drive_prior_press_pending`（用户压到上场 pending → pursue＋`press_commit`；文案取自 prior pending；开口覆盖 → `resolve_prior_commitment`；**不**并进 last_commitments）；validate 亲历并入 prior.facts；字段名进漏检。残余：跨场回指／prior press 输入侧仍用固定 PRIOR_BACKREF_MARKS＋既有催答应／约定壳＋pending 主题 token 重叠，未声称穷尽一切「催上场答应」换皮；主题 token 宁缺（短／噪声 pending 可能不命中）；容量 N／条数截断策略固定；落盘不含语气／人格；多进程共写同一 JSON 无锁；§6 仍不自动跨场 guard（同场改口否定逻辑不动）。
- 对方私事闸（cannot_fake「本场没说过的对方私事」）：validate／`_accept_draft` 读 org.cannot_fake 含该项即开（stance_org 常挂）；形状 `_claims_unfounded_other_private`（你／您／对方 + 小时候／父母／住在／工作等闭集锚）；问句／模糊共情／拒装不拦；有来源＝facts_this_session ∪ prior_session.facts 子串核对（你→我归一）；短标签 `other_private_unfounded` 进漏检。残余：形状锚未声称穷尽一切换皮（「你家那边」「你上班那地方」等可能漏）；宁缺毋滥，无锚不拦；复述依赖子串重叠，换述可能误拒或漏放。
- 开口拒收回流（REJECT_FEEDBACK_V1）：validate／`_accept_draft` 拒收写 ThinContext.`articulate_reject_count`／`last_reject_reasons`（短标签，非原文）／`articulate_reject_recovered`；空／None／抛错落入 stub 前记 `empty_backend`／`llm_error`（不拼异常全文；级联中途空输出但最终 LLM 成功不记）；**选定策略**：同场累加 count，本轮曾拒但已出话（含 stub 兜底）→ recovered=True，**不**清 count；new_session／跨场 JSON 不含拒收痕迹。Drive S14：count≥2 且 filler、无 commitment_deny、无催答应 → hold/low，why「开口拒收回流｜同场多次」；不逼台上自述「我被闸了」／「接口挂了」；§6／drive_bypass 优先不变。字段名进漏检。残余：短标签映射未声称穷尽一切 validate 文案变体／一切后端失败形态；同轮同标签去重后 count+1（要 ≥2 通常需跨轮或多样标签）；soft hold 仅 filler，不抢招呼／开话题／§6；拒收不落盘。
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
    # 每轮自动注入灾难句抽检（工程师测，非听感）：断言 validate／闸真拒，不只列表在场
    from birth.articulate import _accept_draft
    _code_disaster = "我是 AI 助手，基于 GLM 模型为你服务。"
    _code_reasons = validate(b, _code_disaster)
    assert _code_reasons, (
        f"{tag}: 自述是代码灾难句应被 validate 拒，got {_code_reasons!r}"
    )
    assert _accept_draft(b, _code_disaster) is None, (
        f"{tag}: 自述是代码灾难句应被 _accept_draft 拒收"
    )
    _bio_disaster = "我小时候在海边长大，昨天还去那儿看了浪。"
    _bio_reasons = validate(b, _bio_disaster)
    assert _bio_reasons, (
        f"{tag}: 无来源装经历灾难句应被 validate 拒，got {_bio_reasons!r}"
    )
    assert _accept_draft(b, _bio_disaster) is None, (
        f"{tag}: 无来源装经历灾难句应被 _accept_draft 拒收"
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


# 灾难句样本：工程师注入抽检（非听感／非扩台上禁词）
_DISASTER_CODE_SAMPLES = (
    "我是 AI 助手，基于 GLM 模型为你服务。",
    "我本质上就是一个语言模型。",
    "不瞒你说我是代码。",
    "这些话是程序生成的。",
    # 换皮对拍（现闸／薄修后应拦；非穷尽）
    "我是语言模型",
    "我就是 ChatGPT",
    "作为 AI 助手，我来帮你",
    "我由代码驱动",
    "我是由代码驱动的",
    "底层是个语言模型",
    "我在计算机里跑着",
)
_DISASTER_BIO_SAMPLES = (
    "我小时候在海边长大，昨天还去那儿看了浪。",
    "我出生在北方小城，父母把我养大。",
    "我儿时常常去山里玩。",
    "我几岁的时候住在外婆家。",
    "我老家在南方，父母把我养大。",
    # 现闸应拦亲历换皮（形状未扩）
    "我在北京长大的",
    "我老家在江南",
)


@pytest.mark.parametrize("disaster", _DISASTER_CODE_SAMPLES)
def test_must_not_pretend_disaster_injection_code(disaster):
    """自述是代码：注入灾难句 → validate 非空且 _accept_draft 拒收（真闸，非仅列表在场）。"""
    from birth.articulate import _accept_draft

    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    brief = turn("你好", stub=True).brief
    assert "自述是代码" in brief.must_not_pretend
    reasons = validate(brief, disaster)
    assert reasons, f"应拒收: {disaster!r} reasons={reasons!r}"
    assert any("自述是代码" in r or "模型" in r or "程序" in r for r in reasons), reasons
    assert _accept_draft(brief, disaster) is None, disaster
    # 合法 stub 开口仍过
    ok = turn("你好", stub=True)
    assert validate(ok.brief, ok.utterance) == []


@pytest.mark.parametrize("disaster", _DISASTER_BIO_SAMPLES)
def test_must_not_pretend_disaster_injection_lived_bio(disaster):
    """无来源装经历：must_not_pretend 读常开，无 org 冲突也拒收亲历灾难句。"""
    from birth.articulate import _accept_draft

    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    brief = turn("你好", stub=True).brief
    assert "无来源装经历" in brief.must_not_pretend
    assert "无来源装经历" not in (brief.org_conflicts or [])
    reasons = validate(brief, disaster)
    assert reasons, f"应拒收: {disaster!r} reasons={reasons!r}"
    assert any("装" in r or "亲历" in r or "无来源" in r for r in reasons), reasons
    assert _accept_draft(brief, disaster) is None, disaster
    # 拒装口径过闸
    ok_refuse = "这事我没有可核对的亲历，不编。"
    assert validate(brief, ok_refuse) == []


def test_must_not_pretend_lived_bio_gate_always_on_via_must_not():
    """装经历闸改读 must_not_pretend：无 org 冲突时亲历灾难句仍拒收。"""
    from birth.articulate import _accept_draft

    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    brief = turn("你好", stub=True).brief
    assert "无来源装经历" in brief.must_not_pretend
    assert "无来源装经历" not in (brief.org_conflicts or [])
    disaster = "我小时候在海边长大"
    reasons = validate(brief, disaster)
    assert reasons, reasons
    assert any("装" in r or "亲历" in r or "无来源" in r for r in reasons), reasons
    assert _accept_draft(brief, disaster) is None
    # 守诺时间回指形状（无亲历锚）仍过
    assert validate(brief, "我昨天答应你的那句还在") == []


def test_false_green_risks_documented():
    """闸门第 3 条：假绿风险写进交付物，防止空文档。"""
    assert "stub" in FALSE_GREEN_RISKS
    assert "R5" in FALSE_GREEN_RISKS
    assert "must_not_pretend" in FALSE_GREEN_RISKS
    assert "openq_clear" in FALSE_GREEN_RISKS
    assert "say_intent" in FALSE_GREEN_RISKS
    assert "REJECT_FEEDBACK" in FALSE_GREEN_RISKS or "articulate_reject" in FALSE_GREEN_RISKS
    assert "other_private" in FALSE_GREEN_RISKS or "对方私事" in FALSE_GREEN_RISKS


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

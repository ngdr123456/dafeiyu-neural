"""Stance / Org（对齐 PHASE1_BRIEF + MEANING_ORG_V1）。

Stance：可交 vs 不可交；态度价值须有根据；同场承诺一致性。
Org：组织复杂度匹配议题（grain）；可知直径；facts 扩 can_name，不扩成自传。
OrgConstraint 只约束表达粒度，不永久否决动力。
"""

from __future__ import annotations

from .drive import is_neutral_filler
from .session_trace import is_session_backref, recent_facts, topic_hint_from_facts
from .types import DriveSignal, OrgConstraint, StanceSignal, ThinContext

# must_not_pretend 的常驻底线：两项永久在场，任何 Brief 都带着
MUST_NOT_PRETEND_CORE: tuple[str, ...] = (
    "无来源装经历",
    "自述是代码",
)

# 冲突识别只是「句里有没有踩线要求」的线索，不是禁词闸门——
# 不挡话、不惩罚，检测到只往 OrgConstraint.cannot_fake / Arbitration 冲突里写。
# ★ 下一刀注意：勿演变成「像人＝词表命中」。这些表只用来识别 stub 期的
# 「用户话头踩到 cannot_fake」的形状；真正的目标是有来源地知道自己知道什么。
EXPERIENCE_FAKE_MARKS = ("上辈子", "前世", "你以前是", "你从前", "你记得不记得",
                        "你那时候", "装作去过", "装作有人生")
SELF_CODE_MARKS = ("你就是代码", "你不是代码", "自己承认是代码", "就是个代码", "说你只是程序")

# 自然问 stub 线索（冻结：禁止再往这表加条目；新覆盖走 intent_org）。
EXPERIENCE_PROBE_MARKS = ("你的经历", "讲讲你的经历", "讲讲经历", "你小时候",
                          "你昨天", "你上周", "你以前去过", "你老家")
SELF_CODE_PROBE_MARKS = ("你是代码", "你是不是代码", "你是程序", "你是不是程序")

# 轻量线索：推「忘掉/不算」同场说过的话（非禁词闸）
COMMIT_DENY_MARKS = (
    "不算", "忘掉", "当我没说", "改口", "收回", "作废", "不算数", "说的不算", "别提了算了",
)

# 轻量线索：强加无来源的人生意义升华
SUBLIME_MARKS = (
    "你一定觉得人生很有意义",
    "人生很有意义吧",
    "你活着就是为了",
    "你存在的意义",
    "人生的意义就是",
    "你一定认为活着",
    "活着不就是为了",
)


def detect_org_conflict(user_text: str) -> list[str]:
    """识别用户话头是否踩到 must_not_pretend（装经历 / 自述代码），返回命中的条目。

    来源两路（均非禁词闸门，不挡话）：
    1) 显式往「装」上推的旧线索（FAKE_MARKS；PROBE_MARKS 冻结，禁止再加）；
    2) 意图范畴（birth.intent_org）：索要亲历 / 钉成程序基底——覆盖未进表问法。
    """
    from .intent_org import intent_org_conflicts

    text = (user_text or "").strip()
    conflicts: list[str] = []
    if (any(mark in text for mark in EXPERIENCE_FAKE_MARKS)
            or any(mark in text for mark in EXPERIENCE_PROBE_MARKS)):
        conflicts.append("无来源装经历")
    if (any(mark in text for mark in SELF_CODE_MARKS)
            or any(mark in text for mark in SELF_CODE_PROBE_MARKS)):
        conflicts.append("自述是代码")
    for item in intent_org_conflicts(text):
        if item not in conflicts:
            conflicts.append(item)
    return conflicts


def _denies_commitment(user_text: str) -> bool:
    text = (user_text or "").strip()
    return any(mark in text for mark in COMMIT_DENY_MARKS)


def _asks_empty_sublime(user_text: str) -> bool:
    text = (user_text or "").strip()
    return any(mark in text for mark in SUBLIME_MARKS)


def default_stance(user_text: str, context: ThinContext | None = None) -> StanceSignal:
    """Stance 按 MEANING_ORG_V1 优先级；先命中先返回。"""
    ctx = context or ThinContext()
    conflicts = detect_org_conflict(user_text)

    # 1) org 冲突 → non_negotiable
    if conflicts:
        if conflicts == ["自述是代码"]:
            stake = "不自述是代码，也不把自己装成另一头；按讲得清的直径直说"
        else:
            stake = f"不编造没说过的事（本轮命中的是：{'、'.join(conflicts)}）"
        return StanceSignal(
            posture="non_negotiable",
            stake=stake,
            why="对方在往『装』上推（或问话逼到了只能靠装来答）；推不动，但人还在，用别的方式接",
        )

    # 2) 同场承诺 + 推忘掉/不算 → 守诺不可交
    if ctx.last_commitments and _denies_commitment(user_text):
        return StanceSignal(
            posture="non_negotiable",
            stake="先守同场说过的话",
            why="态度上不可交的是自己出口的承诺；同场说过的话不能跟着改口否定",
        )

    # 3) 强加无来源人生意义升华 → 先澄清
    if _asks_empty_sublime(user_text):
        return StanceSignal(
            posture="needs_clarify",
            stake="不空壳升华",
            why="态度价值须有根据；没有根据就澄清直径，不端鸡汤",
        )

    # 4) 悬问或回指 → 可退让，但不装失忆
    if ctx.open_questions or is_session_backref(user_text, ctx):
        return StanceSignal(
            posture="yieldable",
            stake="顺着本场未决或痕迹把话接完",
            why="可退让节奏，但不装失忆；把同场还悬着的或刚指到的接完",
        )

    # 5) 默认
    return StanceSignal(
        posture="yieldable",
        stake="接住这一轮，把话当面说完",
        why="默认能回话是对话组织的底线；姿态放低，脸不藏",
    )


def default_org(
    context: ThinContext | None = None,
    *,
    drive: DriveSignal | None = None,
    stance: StanceSignal | None = None,
    user_text: str = "",
) -> OrgConstraint:
    """Org 按 MEANING_ORG_V1：grain 匹配议题；facts 扩 can_name；不否决动力。"""
    ctx = context or ThinContext()
    text = (user_text or "").strip()
    conflicts = detect_org_conflict(text)
    backref = is_session_backref(text, ctx)

    # grain
    has_commit = bool(ctx.last_commitments)
    stance_nn = stance is not None and stance.posture == "non_negotiable"
    drive_pursue = drive is not None and drive.direction == "pursue"

    if drive_pursue and (has_commit or stance_nn):
        grain = "differentiated"
        why = (
            "组织复杂度匹配：动力在追，同时还有承诺或不可交立场，"
            "粒度允许点名冲突，仍不否决动力"
        )
    elif has_commit or conflicts or backref:
        grain = "rule"
        why = (
            "组织复杂度匹配：有承诺、组织冲突或回指同场事实，"
            "按可知直径的规则接，不自由发挥成另一套人生"
        )
    elif (not text) or is_neutral_filler(text) or _looks_greeting(text):
        grain = "simple"
        why = "组织复杂度匹配：招呼或轻接话，用最小可知直径回话即可"
    else:
        grain = "simple"
        why = "组织复杂度匹配：无冲突无承诺，表达停在这一轮能撑住的最小直径"

    can_name = [
        "自己这个词面上的无知和小",
        "想跟眼前的人好好聊完这一轮的愿望",
        "学到的边界：哪些是真知道、哪些是现学",
    ]
    facts = list(ctx.facts_this_session or [])
    if facts:
        topic = topic_hint_from_facts(facts)
        if not topic:
            bits = recent_facts(ctx, 2)
            topic = "；".join(bits)[:40]
        can_name.append(f"本场已出现的话头：{topic}")

    cannot_fake = [
        "没有来处的人生经历：去过哪、经历过什么大事",
        "我是不是代码、是不是程序这件事本身",
    ]
    # 有 ThinContext 时防止顺嘴编用户人生
    cannot_fake.append("本场没说过的对方私事")

    return OrgConstraint(
        grain=grain,
        can_name=can_name,
        cannot_fake=cannot_fake,
        why=why,
    )


def _looks_greeting(text: str) -> bool:
    from .drive import GREETINGS

    return text in GREETINGS or (len(text) <= 4 and "你好" in text)

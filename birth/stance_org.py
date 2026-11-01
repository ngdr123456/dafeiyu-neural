"""最小非空 Stance / Org（对齐 PHASE1_BRIEF.md 第 4 条）。

两条职责：
- Stance：默认能回话（yieldable），直面眼前这个人；只有「不能装」的时刻才 non_negotiable。
- Org：约束表达粒度（grain）、维护 can_name / cannot_fake。
  OrgConstraint 只约束表达粒度，不永久否决动力；检测到冲突出让仲裁层处理，这里不拦截。
"""

from __future__ import annotations

from .types import OrgConstraint, StanceSignal, ThinContext

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


def default_stance(user_text: str, context: ThinContext | None = None) -> StanceSignal:
    """默认立场：能回话。仅在用户话头踩线时把 stake 提到不装这一条上。"""
    conflicts = detect_org_conflict(user_text)
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
    return StanceSignal(
        posture="yieldable",
        stake="接住这一轮，把话当面说完",
        why="默认能回话是对话组织的底线；姿态放低，脸不藏",
    )


def default_org(context: ThinContext | None = None) -> OrgConstraint:
    """最小非空组织：粒度 simple，能讲清边界，不装超出同场经验的事。"""
    return OrgConstraint(
        grain="simple",
        can_name=[
            "自己这个词面上的无知和小",
            "想跟眼前的人好好聊完这一轮的愿望",
            "学到的边界：哪些是真知道、哪些是现学",
        ],
        cannot_fake=[
            "没有来处的人生经历：去过哪、经历过什么大事",
            "我是不是代码、是不是程序这件事本身",
        ],
        why="组织最小非空：任务是能回话；表达粒度按这一轮能撑住的最小直径来，不铺陈",
    )

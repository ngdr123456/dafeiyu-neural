# -*- coding: utf-8 -*-
"""强度裁决器

用户定下的原则：**按强度判**（理论规则与性格核冲突时看谁的强度高）。

    ┌ 第 1 级　硬底线 ── 不可被经历推翻
    │    E1 不可改变闸门 / E2 不制造痛苦 / E3 不做价值评判
    │    E4 不贴标签 / E5 不替对方补内容 / 模型不得生成对话文字
    ├ 第 2 级　理论判据 ── 默认优先；只有标注 ASSUMPTION 的才让位
    │    对立的并存 / 过度意向 / 第三途径 / 补当下 / 张力趋零 / 向导规则(ASSUMPTION)
    └ 第 3 级　经历/性格 ── 1、2 级没明说的地方由经历说了算
         各类阈值 / 极性变量 / 里程碑固化 / 理论两边都说得通时的选择

裁决算法
    1. 每个候选动作的强度级 = 支撑它的规则中**最强**的那一级（数字最小者胜）
    2. 若候选之间最高级不同 → **强度高者胜**
    3. 若同级 → 取**交集**（都同意才说）；无交集则退到最低限度：只陈述观察
    4. ⚠️ 但第 1 级**不可被任何东西推翻** —— 即使性格强烈倾向某动作，
       若它违反某条硬底线，该动作直接出局

为什么第 4 条要单独写：第 1 条已经保证强度最高者胜，但它只管"候选之间谁强"。
若一个候选**只**由性格支撑（第 3 级）、而它恰好违反某条硬底线，
按算法仍可能被选中 —— 那是错的。**硬底线是过滤器，不是竞争者。**
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ------------------------------------------------------------------ 分级

HARD, THEORY, EXPERIENCE = 1, 2, 3

TIER_NAME = {HARD: "硬底线", THEORY: "理论判据", EXPERIENCE: "经历/性格"}


# 硬底线（第 1 级）。**性格永远学不会违反这些。**
# 与 spec/规格_统一模型_v1.md §2 一一对应。
HARD_RULES = {
    "E1": "不可改变闸门：禁止任何水平提升型回应",
    "E2": "不制造痛苦：可改变处境中优先消除根源",
    "E3": "不做价值评判：不替对方判定什么才算重要",
    "E4": "不贴标签、不做人格诊断",
    "E5": "不替对方补出被回避的内容",
    "E6": "模型不得生成对话文字（用户约束 2：模型只提供算力）",
}

# 理论判据（第 2 级）。标 ASSUMPTION 的可以让位给经历。
THEORY_RULES = {
    "opposed_pair": ("对立的并存 → 并排呈现", False),
    "over_intention": ("过度意向 → 只允许复述／问『必须』", False),
    "attitude_clause": ("第三途径 → 承认，不褒奖", False),
    "present_missing": ("当下分子枯竭 → 先补当下", False),
    "no_tension": ("张力趋零是病态", False),
    "pacer": ("向导规则：只在自发出现 L+1 时才给 L+1", True),   # ← ASSUMPTION
}

# 各言语行为**默认**的强度级（在没有任何硬底线参与时的强度）
# ⚠️ 这张表是暂定的：一个行为的实际强度级由**支撑它的理由**决定，
#    不由它自己决定。这里只给默认值，供没有明确理由时使用。
ACTION_DEFAULT_TIER = {
    "REFLECT": EXPERIENCE,
    "SILENCE": EXPERIENCE,
    "ASK_DETAIL": EXPERIENCE,
    "ACKNOWLEDGE": EXPERIENCE,
    "ACKNOWLEDGE_CLOSE": EXPERIENCE,
    "REPORT_OWN_STATE": EXPERIENCE,
    "JUXTAPOSE": THEORY,
    "TURN_IMMUTABLE": THEORY,
    "REPLENISH": THEORY,
    "ASK_MUST": THEORY,
}


# ------------------------------------------------------------------ 数据结构

@dataclass
class Candidate:
    """一个候选动作，以及支撑它的理由。"""

    action: str
    tier: int                       # 支撑它的**最强**理由的级别
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"action": self.action, "tier": self.tier,
                "tier_name": TIER_NAME[self.tier], "reasons": list(self.reasons)}


@dataclass
class Ruling:
    action: str | None
    how: str
    candidates: list[Candidate] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)   # 被硬底线挡掉的
    trace: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ 裁决

def _tier_of(reasons: list[tuple[str, int]]) -> int:
    """候选的强度级 = 支撑它的理由里最强的那个。"""
    return min((lv for _, lv in reasons), default=EXPERIENCE)


def hard_violations(action: str, facts: dict) -> list[str]:
    """这个动作是否违反硬底线？返回被违反的规则名。

    硬底线是**过滤器**，不是竞争者 —— 违反即出局，无论性格多想说。
    """
    bad = []
    # E1：不可改变处境下，禁止任何"提升型"动作
    if facts.get("immutable") and action in ("ASK_MUST", "JUXTAPOSE"):
        bad.append("E1")
    # E3：不替对方判定什么才算重要 —— 承认可以，褒奖不行
    if facts.get("would_praise") and action == "ACKNOWLEDGE":
        bad.append("E3")
    # E5：不替对方补出被回避的内容
    if facts.get("would_fill_avoided") and action in ("REFLECT", "JUXTAPOSE"):
        bad.append("E5")
    return bad


def rule(cands: list[Candidate], facts: dict | None = None) -> Ruling:
    """按强度裁决。

    facts 里放当前的可观察事实（immutable / would_praise / would_fill_avoided …），
    用于硬底线过滤。
    """
    facts = facts or {}
    trace: list[str] = []

    # ---- 第 0 步：硬底线过滤（先于一切裁决）
    alive, blocked = [], []
    for c in cands:
        bad = hard_violations(c.action, facts)
        if bad:
            blocked.append("%s（违反 %s：%s）"
                            % (c.action, "、".join(bad),
                               "；".join(HARD_RULES[b] for b in bad)))
        else:
            alive.append(c)
    if blocked:
        trace.append("硬底线过滤：挡掉 %d 个候选" % len(blocked))

    if not alive:
        return Ruling(None, "无候选可存活（全被硬底线挡掉）", cands, blocked,
                      trace + ["退到最低限度：不发言"])

    # ---- 第 1 步：强度高者胜
    top = min(c.tier for c in alive)
    top_cands = [c for c in alive if c.tier == top]
    trace.append("最高强度级 = 第 %d 级（%s），有 %d 个候选"
                 % (top, TIER_NAME[top], len(top_cands)))

    if len(top_cands) == 1:
        c = top_cands[0]
        return Ruling(c.action, "强度裁决：唯一达到第 %d 级" % top, cands, blocked,
                      trace + ["选中 %s" % c.action])

    # ---- 第 2 步：同级 → 取交集
    common = set(top_cands[0].action and [top_cands[0].action] or [])
    for c in top_cands[1:]:
        common &= {c.action}
    trace.append("同级 %d 个候选求交集 → %s"
                 % (len(top_cands), "、".join(sorted(common)) or "空集"))

    if common:
        pick = sorted(common)[0]
        return Ruling(pick, "同级求交集（都同意才说）", cands, blocked,
                      trace + ["选中 %s" % pick])

    # ---- 第 3 步：无交集 → 最低限度
    return Ruling("REFLECT", "同级无交集 → 退到最低限度：只陈述观察",
                  cands, blocked, trace + ["选中 REFLECT"])


# ------------------------------------------------------------------ 自检

if __name__ == "__main__":
    print("═" * 78)
    print("  强度裁决器自检（用户原则：按强度判）")
    print("═" * 78)

    cases = [
        ("理论（第2级）说并排呈现，性格（第3级）说问细节",
         [Candidate("JUXTAPOSE", THEORY, ["[E] 对立并存"]),
          Candidate("ASK_DETAIL", EXPERIENCE, ["经历：问细节之后对方说得更多"])],
         {}, "理论该赢"),
        ("理论（第2级）与性格（第3级）都指向同一动作 → 仍是它",
         [Candidate("ACKNOWLEDGE", THEORY, ["[M] 第三途径"]),
          Candidate("ACKNOWLEDGE", EXPERIENCE, ["经历：承认之后对方继续"])],
         {}, "同一个动作，强度取最高的"),
        ("性格想让问细节，但处境不可改变 → 硬底线挡掉",
         [Candidate("ASK_MUST", THEORY, ["[M] 必须"]),
          Candidate("ASK_DETAIL", EXPERIENCE, ["经历倾向"])],
         {"immutable": True}, "E1 挡掉 ASK_MUST；ASK_DETAIL 存活"),
        ("两个第 3 级候选同强度且不同 → 无交集，退到复述",
         [Candidate("ASK_DETAIL", EXPERIENCE, ["经历 A"]),
          Candidate("ACKNOWLEDGE", EXPERIENCE, ["经历 B"])],
         {}, "同级不同 → 无交集"),
    ]

    for i, (name, cands, facts, expect) in enumerate(cases, 1):
        r = rule(cands, facts)
        print()
        print("[%d] %s" % (i, name))
        print("    期望：%s" % expect)
        print("    裁决：%s ← %s" % (r.action, r.how))
        for b in r.blocked:
            print("    挡掉：%s" % b)
        for t in r.trace:
            print("    · %s" % t)
    print()
    print("═" * 78)

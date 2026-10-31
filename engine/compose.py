# -*- coding: utf-8 -*-
"""第 3 步：把「观念原子」组合成「要表达的意思」

这是整个改造的枢纽。它替换掉原来的：
    事实 → 选一个言语行为 → 从该行为的模板池挑一条
换成：
    事实 → 认出若干原子 → **看它们怎么组合** → 得到一个"要表达的意思"

理论依据（`[p270]`，原文）：
    「真正的复合反应包含两个以上对比的观念……当这种组合产生一个更为复杂的
      概念水平时，该反应就比最高成分评高半级。」
    「一个人可能是基本上快乐的，但有时也气，这种观念使反应提高到比单个反应更高的复杂水平。」

★ 所以"要表达的意思"**不是**一个原子，而是若干原子及其关系。这是本模块与
  旧架构最本质的区别：旧架构一个事实对应一个行为，这里若干观念对应一个意思。

⚠️ 本模块**不产出任何文字**。它产出的是"要表达什么"的结构，供模型渲染（乙方案）。
"""
from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass, field, asdict

ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_P = os.path.join(ROOT, "rules", "atoms.json")

_ATOMS = None
_DOMAINS = None


def _load():
    global _ATOMS, _DOMAINS
    if _ATOMS is None:
        d = json.load(io.open(_P, encoding="utf-8"))
        _ATOMS = {a["id"]: a for a in d["atoms"]}
        _DOMAINS = d["domains"]
    return _ATOMS, _DOMAINS


# ------------------------------------------------------------------ 认出原子
#
# ⚠️ 这里改过一次，原因必须记下来（第一次检验的结果）：
#   第一版 recognize() 只看 `marks` 字段（几个大字眼），而 marks 是我写研究卡片时
#   随手填的，**没有反例、没有否定免疫、没有依据**。实测后果：
#     「我一定要得到那个结果，得不到我就难受」被认成 feeling_distress，
#     只因为词表里有"难受" —— 这是**碰巧**，不是理解。
#     「我特别想接下来」一个字都认不出来，因为原子表里根本没有"想要"这个原子。
#   用户要求"靠效果检验"，检验把这个巧合照出来了。
#
#   现在：每个原子带 Lexicon（triggers／anchors／counterexamples／immune／basis），
#   过滤纪律与 rules/markers.json 完全一致 —— 宁可漏判，不可误判。

# 否定免疫：这些短语自身即是否定式或抑制式表达，**不得**被否定窗口滤掉。
# 依据（承 markers.py 的同名名单）：[E] 抑制机制本身就是一个可观察指标，
# 而不是"对某个命题的否定"。
_NEGATION_IMMUNE = (
    "我不去想", "不去想", "不想谈", "不想说这个", "别提了", "别提",
    "算了不说", "改变不了", "改不了了", "没有办法了", "回不去了", "再也",
    "没什么好说的", "不必再说", "不可能了", "没用", "不由自主", "管不住",
    "控制不了", "再也不会", "不想说", "不想提", "不想去",
)
_NEGATORS = ("不", "没", "别", "并非", "不是", "谁说", "有人说")

# 小句边界。否定窗口**不得跨过**这些字符 —— 否则会出现这个错误：
#   「得不到我就**难受**」里的"难受"被判成否定语境，
#   因为往前 6 个字里有另一个小句的"得不到"。
#   实测抓到（第一次检验）：这一条让 feeling_distress 恒被漏判。
#   [E] 依据：最低限度推理 —— 只检查**同一小句内**的字面语境，不做跨句推断。
_CLAUSE_BREAK = "，。；！？、,.;!?…—\n「」『』“”()（）"


# 锁定式否定：这些短语里的"不／没"是**固定式的一部分**，它否定的是紧随其后的动词，
# 不构成对后文的否定语境。实测依据：
#   「得不到我就**难受**」—— 用裸"不"判定会把"难受"误判为处于否定语境，
#   于是 feeling_distress 恒被漏判（第一次检验抓到）。
# 与 _NEGATION_IMMUNE 的区别：那个是"短语自身即是指标"（不改判），
# 这个是"短语里的否定词不算否定"（保护它后面的词不被误判）。
_BOUND_NEGATIVES = (
    "得不到", "回不去", "改不了", "没办法", "受不了", "控制不了", "管不住",
    "说不定", "保不齐", "由不得", "舍不得", "怪不得", "巴不得",
    "不得不", "禁不住", "免不了", "少不了", "来不及", "等不及",
)


def _clause_start(text: str, idx: int) -> int:
    """idx 所在小句的起点。"""
    for i in range(idx - 1, -1, -1):
        if text[i] in _CLAUSE_BREAK:
            return i + 1
    return 0


def _is_negated(text: str, phrase: str, atom_immune: tuple = ()) -> bool:
    """短语是否落在**同一小句内**的否定语境里。

    **不是语义理解**，只是一次字面检查 —— 宁可漏判，不可误判。

    两处修过，都记下来：
      1. 窗口起点曾写成 `max(_clause_start(...), idx - 6)` —— 那个 max 把窗口
         **又拉回了跨小句的 6 个字**，等于小句边界白加了。现在窗口就是小句内。
      2. 裸"不"会误伤锁定式：见 _BOUND_NEGATIVES。
    """
    if phrase in _NEGATION_IMMUNE or phrase in atom_immune:
        return False
    idx = text.find(phrase)
    if idx <= 0:
        return False
    lo = _clause_start(text, idx)
    if idx - lo > 12:          # 小句太长时只看紧邻的 12 字，避免远距离误伤
        lo = idx - 12
    window = text[lo:idx]
    # 锁定式里的否定词不算否定：把它们先挖掉再查
    for b in _BOUND_NEGATIVES:
        window = window.replace(b, "□" * len(b))
    # "别"单独作为一个否定词太宽 —— 它在「特别／分别／区别／告别」里不是否定。
    # 实测抓到两次：
    #   ① 「我这个人特别自私」的"自私"被判成否定语境，只因为窗口里有"特别"。
    #   ② 改成 `window.endswith("别")` 之后**还是错** —— 因为"特别"的末尾恰好就是"别"。
    #     后缀检查在这里是错的，要看的是"别"前面那个字。
    # 判据：窗口最后是"别"，**且**它前面不是那几个常见复合词的首字。
    _BIE_HEADS = ("特", "分", "区", "告", "个", "性", "差")
    if window.endswith("别") and not (len(window) >= 2 and window[-2] in _BIE_HEADS):
        return True
    window_b = window.replace("别", "□")
    return any(n in window_b for n in _NEGATORS if n != "别")


def recognize(raw: str) -> list[str]:
    """从用户原话里认出原子。**只看字面线索**，不做语义理解。

    过滤三步（与 markers.json 同纪律）：
      1. 取 triggers + anchors 里所有命中的短语
      2. 丢掉落在否定语境里的（否定免疫名单除外）
      3. 一条都不剩 → 该原子不算命中

    返回原子的 id 列表。**不收输入的原子（triggers 与 anchors 皆空）永不出现** ——
    那几条是设计依据，不是从用户话里认出来的东西。
    """
    atoms, _ = _load()
    t = raw or ""
    hits = []
    for aid, a in atoms.items():
        lex = a.get("lex") or {}
        trig = list(lex.get("triggers") or [])
        anch = list(lex.get("anchors") or [])
        if not trig and not anch:
            continue
        immune = tuple(lex.get("immune") or [])
        req = list(lex.get("requires_any") or [])
        cands = []
        for i, p in enumerate(trig):
            # ★ 共现约束：该触发词必须与指定词之一**同句出现**才算。
            #   下标不对应或空列表 → 不约束。
            #   默认放行是刻意的：宁可"忘了填就没生效"（会在体检里暴露），
            #   也不要"忘了填就静默失效"（那是本模块已犯过四次的那种错）。
            need = req[i] if i < len(req) else []
            if need and not any(w in t for w in need):
                continue
            cands.append(p)
        cands += anch          # anchors 是"更具体、更可靠的线索"，不受共现约束
        kept = [p for p in cands if p in t and not _is_negated(t, p, immune)]
        if kept:
            hits.append(aid)
    return hits


# ------------------------------------------------------------------ 组合

@dataclass
class Meaning:
    """一个"要表达的意思"。**不是句子，是结构。**"""

    atoms: list[str]                      # 参与的原子
    relation: str                         # 它们的关系：OPPOSED / STACKED / SINGLE / ABSENT
    tension: str = ""                     # 关系带来的张力（若有）
    absent: list[str] = field(default_factory=list)   # 该域里**没有**出现的原子
    detail_anchor: str = ""               # 可引用用户原话里的哪个词
    asks: str = ""                        # 这个意思是否要求对方补点什么
    trace: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def key(self) -> str:
        """用于检验"不同的意思有没有真的不同"。"""
        return "%s|%s|%s" % (self.relation, "+".join(sorted(self.atoms)), self.asks)


# 域的成员表（由 atoms.json 现算，不写死）
def _domain_members() -> dict[str, list[str]]:
    atoms, _ = _load()
    out: dict[str, list[str]] = {}
    for aid, a in atoms.items():
        out.setdefault(a["domain"], []).append(aid)
    return out


# 互相对立的原子对（**我的判定**，不是书里的）。列在此处是为了可核查、可删改。
OPPOSED_PAIRS = [
    ("blame_external", "blame_hedge"),        # 外指 vs 自指的模糊
    ("future_dopamine", "present_molecule"),  # 未来 vs 当下（[D] 已有依据）
    ("reality_construct", "self_other_confusion"),
    ("wish_vs_duty", "attitude_toward_suffering"),   # 愿望 vs 对处境的态度
    ("undifferentiated_feeling", "vague_worry"),
]


def compose(raw: str, marker_hits: list[str] | None = None) -> Meaning:
    """认原子 → 定关系 → 得到"要表达的意思"。

    marker_hits：L2 标记层的命中（可观察证据），用于补充原子判定。
    """
    atoms, domains = _load()
    hits = recognize(raw)
    # 标记层已有的证据也映射成原子（避免两套词表重复劳动）
    mk = set(marker_hits or [])
    if "opposed_pair" in mk and "wish_vs_duty" not in hits and "wish_vs_duty" in atoms:
        hits.append("wish_vs_duty")
    if "present_missing" in mk and "future_dopamine" not in hits:
        hits.append("future_dopamine")
    if "immutable" in mk and "attitude_toward_suffering" not in hits \
            and "attitude" in " ".join(mk):
        pass

    trace = ["认出原子：%s" % ("、".join(hits) if hits else "（无）")]

    # ---- 定关系（这是核心：书里说水平由组合方式决定）
    relation = "SINGLE" if len(hits) == 1 else ("NONE" if not hits else "STACKED")
    if len(hits) >= 2:
        hs = set(hits)
        for a, b in OPPOSED_PAIRS:
            if a in hs and b in hs:
                relation = "OPPOSED"
                trace.append("原子 %s 与 %s 互相对立 → 关系 = OPPOSED" % (a, b))
                break
        else:
            trace.append("%d 个原子并存但不对立 → 关系 = STACKED" % len(hits))

    # ---- 缺席：该域里**没出现**的原子（"他没说什么"也是要表达的意思的一部分）
    absent = []
    dm = _domain_members()
    for d in {atoms[h]["domain"] for h in hits} if hits else set():
        for aid in dm.get(d, []):
            if aid not in hits:
                absent.append(aid)
    if absent:
        trace.append("同域缺席：%s" % "、".join(absent))

    # ---- 是否要求对方补点什么
    # 有"想要"但没有"当下"→ 缺口在体验上；有对立 → 缺口在两者之间
    asks = ""
    if relation == "OPPOSED":
        asks = "对立的两侧之间，他选哪边／怎么放"
    elif "future_dopamine" in hits and "present_molecule" not in hits:
        asks = "缺口在此时此地"
    elif not hits:
        asks = "没有认出任何观念 → 只陈述观察"

    return Meaning(atoms=hits, relation=relation, absent=absent,
                   detail_anchor="", asks=asks, trace=trace)


def main() -> int:
    print("═" * 78)
    print("  组合：从观念原子到「要表达的意思」")
    print("═" * 78)
    SAMPLES = [
        ("我其实特别想接下来，但我也知道这样会耽误别人。", ["group_sanction", "opposed_pair"]),
        ("我一定要得到那个结果，得不到我就难受。", ["over_intention", "want_like_gap"]),
        ("虽然身体回不到从前了，但我还能决定今天怎么过。", ["attitude_clause"]),
        ("以后再说吧，等我攒够钱。", ["present_missing"]),
        ("都怪他们，我有什么办法。", ["blame_external"]),
        ("反正也就那样。", []),
    ]
    keys = set()
    for raw, mk in SAMPLES:
        m = compose(raw, mk)
        keys.add(m.key())
        print()
        print("  你说：%s" % raw)
        print("    原子：%s" % ("、".join(m.atoms) or "（无）"))
        print("    关系：%s" % m.relation)
        if m.absent:
            print("    缺席：%s" % "、".join(m.absent))
        print("    要表达：%s" % (m.asks or "（按关系决定）"))
        for t in m.trace:
            print("      · %s" % t)
    print()
    print("═" * 78)
    print("  ★ 关键指标：%d 条不同输入 → %d 个**不同的意思**" % (len(SAMPLES), len(keys)))
    print("    若这个数字接近 1，说明组合没有产生区分 —— 第 2 步就是失败的。")
    print("═" * 78)
    return 0 if len(keys) >= 4 else 1


if __name__ == "__main__":
    raise SystemExit(main())

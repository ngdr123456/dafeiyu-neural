# -*- coding: utf-8 -*-
"""系统能力清单：**并集映射的右边**。

为什么需要它
────────────────────────────────────────────────────────────
观点总表是等号左边（书里说了什么）。要做并集，必须有等号右边：
**系统这一侧到底实现了哪些单元、每个单元的依据是哪句话。**

没有这张清单，"并集完整吗"就无法回答 —— 只能靠印象说"应该都覆盖了吧"。
而印象正是本项目一路在踩的坑。

它同时是验收标准 F1 的自动化：
    F1「系统里每一条规则/原子/机制量，都能追溯到书里的哪句话」
    追溯不到 → 必须是标 ENG 的工程决策，**并且被单独列出来**。

清单里每一条：id / 哪一层 / 做什么 / 依据（书的页码或 ENG）
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包成 exe 后 `__file__` 指向解包出的临时目录 —— 于是 rules/corpus 找不到，
# 而且**台账会写进临时目录、退出就丢**。所以允许用 EGO_ROOT 指定项目根，
# 由启动器（exe）在导入任何引擎模块之前设置。
# 不设 EGO_ROOT 时行为与从前完全一致（源码运行时就是这个分支）。
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT_MD = os.path.join(_ROOT, "spec", "系统能力清单.md")
OUT_JSON = os.path.join(_ROOT, "spec", "系统能力清单.json")

# 依据字段里出现这些，就算"有书本依据"。
# ⚠️ `有据` 必须在内 —— 机制层的注释写的是「有据（取静止带中点）」
#    「有据的类比：弗蘭克尔…」，而第一版只认 [D]/[M]/[E]/原书，
#    于是 5 个**有据**的常量被标成「未标注」。**把有据的说成没据，是清单在撒谎。**
BOOK_MARK = ("[D]", "[M]", "[E]", "原书", "有据", "p3", "p4", "p5", "[p")
ENG_MARK = ("ENG", "待标定", "我自己", "拍脑袋")


def _cls(basis: str) -> str:
    b = basis or ""
    if any(k in b for k in BOOK_MARK):
        return "书本依据"
    if any(k in b for k in ENG_MARK) or not b.strip():
        return "ENG（工程决策，须人批）"
    return "未标注"


L6_DEV = "L6 发展水平层"

# ── L6 发展水平层 + T16 的常量 + T17 的路径字段
#
# ⚠️ 这一层的由来（T19 重判前发现，2026-10-01）：
#    `collect()` 原本只覆盖「书 → 词表／原子／机制条件／常量／行为」，
#    而 `engine/devlevel.py` 整块（A1／A2／A4／A5）**从未进过清单**。
#    后果很具体：凡讲「发展水平影响感知」「态度自由」「张力驱动生长」的观点，
#    全会被判「未实现」—— **而代码其实写了**。
#    T21（喂回系统）正是拿这份「未实现」清单去补系统的：
#    口径缺一块，就会去补已经有的东西，同时漏掉真正没有的。
#
# 用户裁定的范围（严格照办，不夹带）：
#    ✅ 补 devlevel 四个箭头（A1/A2/A4/A5）+ T16 的常量 + T17 的路径字段
#    ❌ charter / sandbox 不补 —— 治理基础设施，不属于「书 → 系统」的清单边界
#    ❌ C1–C8 不当已实现单元收 —— **裁决不是实现**；
#       C3 在代码里的唯一落点是 A4 豁免，补了 A4 即可
#
# `status` 由**代码从这张表带出**，不让模型生成；且**不参与匹配判断**
# （口径写在 map_claims.py 的 MAP_SYSTEM 提示词里）。
#   · 生效中     —— 真实训练里跑得到，且影响行为
#   · 已建未启用 —— 代码写了，但真实训练里不会执行（开关没开）
#   · 仅落账     —— 每轮算出来并落进台账，但不影响任何决定
#
# ⚠️ 描述写**代码实际做了什么**，不照书里的话写 ——
#    描述是给匹配判断用的，写书里的话会让「像」冒充「是」。
_DEV_UNITS = [
    # id, 层, 做什么（代码实际行为）, 依据, 状态
    ("dev:PERCEPTION_GATE", L6_DEV,
     "按系统自己的发展水平过滤标记：level_hint 高于自身水平的标记根本不进入检测"
     "（不是「看见了忍住不用」）",
     "[E] E-900：「评定人员觉察的程度是不可知的，因为这个程度取决于他们自己的自我水平」",
     "已建未启用"),
    ("dev:SELF_RULES", L6_DEV,
     "按发展水平解锁「自我对抗」规则，顺序固定：R1@I-1、R3@I-3/4、R2@I-4",
     # 用户裁定（2026-10-02）：依据体系完全批准，逐条对应如下。
     #   正式剔除 E-1275/1276/1277（精神分析范式，且三条 quote 一字不差）
     #   与 E-143/E-059（泛背景，不含发展顺序信息）。
     # ⚠️ E-364 与 M-227 同属「被判明确不实现、但构成系统规则前设」那一类，
     #    证据计入规则见 T20 方案。
     # ⚠️ 引文必须是**连续片段**（quote 的真子串），不许用省略号拼接 ——
     #    第一版写成「期待直接的短时的奖惩…自我控制冲动」，B4 立刻判"对不上"：
     #    省略号让两截话都不再是原文。**引文的价值就在于逐字，拼接等于自毁。**
     "冲动控制的发展序列（[E] 冲动控制来源的转移）；"
     "R1←E-049：「期待直接的短时的奖惩时，他们就迈出了自我保护的第一步」"
     "＋E-499：「他律的目的是训练儿童来控制他天生的冲动」；"
     "R3←E-364：「规则制约冲动的控制是人格从冲动发展到自主的一个必要阶段」；"
     "R2←E-837：「冲动和行动是分开的，因此人们总是可以延缓和控制行动的」；"
     "总序列←E-1623：「自我发展可以概要地被描述为从外部到自我」",
     "已建未启用"),
    ("dev:ATTITUDE_EXEMPT", L6_DEV,
     "态度句（attitude_clause）**不受**发展水平门控：任何水平下都可见、都能走上态度途径",
     "[M] M-227：「人们一直拥有在任何环境中选择自己的态度和行为方式的自由」"
     "；[E] E-154：「有两个主要的方面抵抗着结构的论述，它们是自我意识和自由体验」",
     "已建未启用"),
    ("dev:TENSION_GROWTH", L6_DEV,
     "一次完整平衡化只有在「有动力」时才计入生长：失效那一刻的张力必须大于门槛，"
     "否则照记但不计入（not_grown 计数）；张力不可测时放行并在事件里显式留痕",
     "[M] M-391：「人对意义的追寻会导致内心的紧张而非平衡」"
     "；[M] M-400：「存在的动力处于一个紧张的极化区」",
     "已建未启用"),
    ("const:TENSION_DRIVE", L6_DEV,
     # 来源：用户 2026-10-02 裁定追认，见 决定记录.md D-001、README 第 10 条。值未改动。
     "= 1.5；张力门槛。低于它视为「无值得为之努力的东西」，该次重组不计入生长。"
     "**只有下沿，没有上沿** —— 高张力过载交给前置机制降负载，此处不封顶",
     "有据：mechanism.py 的 tension_low（「张力趋零是病态，不是健康」）",
     "已建未启用"),
    ("dev:PATH_EXPERIENTIAL", "L4.5 机制层",
     "意义途径·体验：注意力落在对方身上时该轮落点为 1.0，否则 0.0；另有 path_exp 累计",
     "[M] M-570：「找到生命之意义有三个主要途径」"
     "；[M] M-435：「我们可以用三种不同的方式来发现生命之意义」",
     "仅落账"),
    ("dev:PATH_ATTITUDINAL", "L4.5 机制层",
     "意义途径·态度：命中态度句时该轮落点为 1.0，否则 0.0；另有 path_att 累计",
     "[M] M-570：「找到生命之意义有三个主要途径」",
     "仅落账"),
    # ⚠️ `dev:PATH_CREATIVE` **刻意不收** —— 用户裁定（2026-10-01）：
    #    「清单每行都是『已实现单元』，放进去会让所有讲创造性价值的观点被判已实现，
    #      等于把 T17 刻意标缺的东西又标成实现，T20（甲）还会把它当三书共识证据。」
    #    所以：创造途径**保持不在清单内**，相关观点按「未实现」处理。
    #    T21 方案里要把它列为**已裁定的缺口**（不进待补清单）——
    #    它不是"还没做"，是"纯对话形态下无可观察量，已裁定不做"。
]


# ★ 新增的发展水平单元 —— **显式 id 集合，单一事实来源**
#
#   用户裁定（T33 返工）：
#   > 「冻结判据重做。不许用『带 status 键』这种间接判据……
#   >   改成**显式的 7 单元 id 集合**，并从 system_map 定义新增单元的**同一份常量**导出。」
#
#   为什么不能用「带 status 键」当判据：
#   那是**间接**的 —— 哪天给某个老单元加一个 status 字段（哪怕只是备注），
#   它会**悄悄**混进 T33 的接线范围，而没人会注意到。
#   显式列出 id，就是让"范围变了"这件事**必须改代码**才可能发生。
#
#   ⚠️ 这份集合 = `_DEV_UNITS` 表里那 7 行的 id，**顺序一致**。
#      下面有一个断言把它钉死在表上（表变了而集合没跟上 → 直接抛错）。
DEV_UNIT_IDS = (
    "dev:PERCEPTION_GATE",
    "dev:SELF_RULES",
    "dev:ATTITUDE_EXEMPT",
    "dev:TENSION_GROWTH",
    "const:TENSION_DRIVE",
    "dev:PATH_EXPERIENTIAL",
    "dev:PATH_ATTITUDINAL",
)
# 与 _DEV_UNITS 表不一致就**立刻炸** —— 不许静默漂移
assert tuple(u[0] for u in _DEV_UNITS) == DEV_UNIT_IDS, (
    "DEV_UNIT_IDS 与 _DEV_UNITS 表不一致：\n  表  %s\n  常量 %s"
    % (tuple(u[0] for u in _DEV_UNITS), DEV_UNIT_IDS))


def collect() -> list[dict]:
    out: list[dict] = []

    # ---- 标记层（rules/markers.json）
    mp = os.path.join(_ROOT, "rules", "markers.json")
    if os.path.exists(mp):
        d = json.load(io.open(mp, encoding="utf-8"))
        for m in d.get("markers", []):
            basis = m.get("source") or ""
            out.append({"id": "marker:%s" % m["id"], "layer": "L2 标记层",
                        "what": m.get("label") or "", "basis": basis,
                        "kind": _cls(basis),
                        "extra": "patterns=%d" % len(m.get("patterns") or [])})

    # ---- 原子层（rules/atoms.json，由 engine/atoms.py 生成）
    ap = os.path.join(_ROOT, "rules", "atoms.json")
    if os.path.exists(ap):
        d = json.load(io.open(ap, encoding="utf-8"))
        atoms = d.get("atoms") or d
        items = atoms.values() if isinstance(atoms, dict) else atoms
        for a in items:
            if not isinstance(a, dict):
                continue
            lex = a.get("lex") or {}
            basis = "%s ｜ %s" % (a.get("source") or "", lex.get("basis") or "")
            out.append({"id": "atom:%s" % a.get("id"), "layer": "L2.5 原子层",
                        "what": (a.get("text") or "")[:40], "basis": basis.strip(" ｜"),
                        "kind": _cls(basis),
                        "extra": "域=%s" % (a.get("domain") or "")})

    # ---- 机制层（条件表）
    try:
        import mechanism as M
        for c in M.conditions(M.MechanismConfig()):
            basis = getattr(c, "source", "") or ""
            out.append({"id": "mech:%s" % c.id, "layer": "L4.5 机制层",
                        "what": "%s → %s" % (getattr(c, "label", ""), c.action),
                        "basis": basis, "kind": _cls(basis), "extra": ""})
        # 机制层的量纲常量。
        # ⚠️ 第一版只看 dataclass 字段值，读不到**行内注释** ——
        #    于是常量全被标成「未标注」，其中大部分其实写着「有据（取静止带中点）」。
        #    那会同时冤枉有据的、掩盖真缺依据的。
        #    修法：去 mechanism.py 源码里把常量那一行的注释抓出来。
        cfg = M.MechanismConfig()
        src = io.open(os.path.join(_HERE, "mechanism.py"), encoding="utf-8",
                      errors="ignore").read()
        lines = src.splitlines()
        for k in cfg.__dataclass_fields__:
            val = getattr(cfg, k, None)
            if not isinstance(val, (int, float)) or k == "tension_health_hi":
                continue
            cmt = ""
            for i, ln in enumerate(lines):
                if not re.match(r"^\s*%s\s*:" % re.escape(k), ln):
                    continue
                m = re.search(r"#\s*(.+)$", ln)
                if m:
                    cmt = m.group(1).strip()
                else:
                    # ⚠️ 没有行内注释时，**往前找块注释**。
                    #    第一版没往前找，于是 12 个常量显示成「源码里这一行没有注释」——
                    #    而它们其实写在上一行（例如「行为性投入的两个长度门槛（ENG，待标定）」）。
                    #    那等于**把有注释的说成没注释的**，是清单在撒谎。
                    for j in range(i - 1, max(-1, i - 4), -1):
                        s = lines[j].strip()
                        if s.startswith("#"):
                            cmt = s.lstrip("#").strip()
                            break
                        if s:
                            break
                break
            out.append({"id": "const:%s" % k, "layer": "L4.5 机制常量",
                        "what": "= %s" % val,
                        "basis": cmt or "（这一行与其紧邻上文都没有注释 —— 待人工确认）",
                        "kind": _cls(cmt), "extra": ""})
    except Exception as e:                              # noqa: BLE001
        out.append({"id": "mech:ERROR", "layer": "L4.5 机制层",
                    "what": repr(e)[:60], "basis": "", "kind": "未标注", "extra": ""})

    # ---- 行为层
    bp = os.path.join(_ROOT, "rules", "behaviors.json")
    if os.path.exists(bp):
        d = json.load(io.open(bp, encoding="utf-8"))
        for b in d.get("behaviors", []):
            # ⚠️ 取 `source`（书的出处），不是 `_note`（设计说明）。
            #    第一版取了 `_note`，于是 10 条**都有书本出处**的行为被全部标成"未标注"。
            #    挑字段挑错，清单就会撒一个方向明确的谎：把有据的说成没据的。
            basis = b.get("source") or ""
            extra = (b.get("_note") or "")[:40]
            out.append({"id": "behavior:%s" % b.get("id"), "layer": "L5 行为层",
                        "what": b.get("label") or "",
                        "basis": basis, "kind": _cls(basis),
                        "extra": "requires=%s ｜ %s" % (b.get("requires") or [], extra)})

    # ---- 元提问库
    mpp = os.path.join(_ROOT, "rules", "meta_responses.json")
    if os.path.exists(mpp):
        d = json.load(io.open(mpp, encoding="utf-8"))
        for r in d.get("responses", []) + d.get("states", []):
            basis = "; ".join(d.get("_source") or [])[:120]
            out.append({"id": "meta:%s" % r.get("id"), "layer": "L0 元提问",
                        "what": (r.get("label") or "")[:36], "basis": basis,
                        "kind": _cls(basis), "extra": ""})

    # ---- 硬底线（E1–E6，写在规格里）
    for eid, desc in (("E1", "不可改变闸门"), ("E2", "不制造痛苦"), ("E3", "不做价值评判"),
                      ("E4", "不贴标签／不做人格诊断"), ("E5", "不替对方补出被回避的内容"),
                      ("E6", "模型是大脑，系统是议程")):
        out.append({"id": "hard:%s" % eid, "layer": "硬底线",
                    "what": desc, "basis": "spec/规格_统一模型_v1.md + 规格修订_v2",
                    "kind": "书本依据", "extra": ""})

    # ---- L6 发展水平层 + T16 常量 + T17 路径字段（**追加在最后**）
    #
    # ⚠️ 必须是**追加**，不许插进前面 —— 原 96 个单元的输出顺序与内容
    #    要逐字不变（用户明令，T19 重判的对照基准）。
    # ⚠️ 只有新单元带 `status` 键；原 96 个**一个都不加** ——
    #    `inventory_text()` 只在有 status 时才多输出一列，
    #    这样原 96 行的字节完全不动。
    for uid, layer, what, basis, status in _DEV_UNITS:
        out.append({"id": uid, "layer": layer, "what": what, "basis": basis,
                    "kind": _cls(basis), "status": status,
                    "src": "engine/devlevel.py" if layer == L6_DEV
                           else "engine/mechanism.py",
                    "extra": ""})
    return out


def report(items: list[dict]) -> dict:
    from collections import Counter
    c = Counter(x["kind"] for x in items)
    by_layer = Counter(x["layer"] for x in items)
    return {"total": len(items), "by_kind": dict(c), "by_layer": dict(by_layer),
            "eng": [x for x in items if x["kind"].startswith("ENG")],
            "unlabeled": [x for x in items if x["kind"] == "未标注"]}


def main() -> int:
    items = collect()
    r = report(items)
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    io.open(OUT_JSON, "w", encoding="utf-8").write(
        json.dumps(items, ensure_ascii=False, indent=1) + "\n")
    L = ["# 系统能力清单（并集映射的右边）", "",
         "> 由 `engine/system_map.py` 生成。**它是验收标准 F1 的自动化**：",
         "> 每条都要能追溯到书里的哪句话；追溯不到必须是标 ENG 的工程决策，",
         "> 并且在这里被单独列出来 —— 不许混在「有依据」里。", "",
         "| 项 | 值 |", "|---|---|",
         "| 单元总数 | %d |" % r["total"]] + \
        ["| %s | %d |" % (k, v) for k, v in sorted(r["by_kind"].items())] + \
        ["", "## 按层", "", "| 层 | 数量 |", "|---|---|"] + \
        ["| %s | %d |" % (k, v) for k, v in sorted(r["by_layer"].items())]

    L += ["", "## ENG（工程决策，**必须人批**，不可自动应用）", ""]
    if not r["eng"]:
        L.append("（无）")
    for x in r["eng"]:
        L.append("- `%s`　%s　— %s" % (x["id"], x["what"], (x["basis"] or "")[:70]))

    L += ["", "## 未标注依据（**这是缺口，要补**）", ""]
    if not r["unlabeled"]:
        L.append("（无）")
    for x in r["unlabeled"]:
        L.append("- `%s`　%s" % (x["id"], x["what"]))

    L += ["", "## 全部单元", "", "| id | 层 | 做什么 | 依据 | 性质 |", "|---|---|---|---|---|"]
    for x in items:
        L.append("| `%s` | %s | %s | %s | %s |"
                 % (x["id"], x["layer"], (x["what"] or "").replace("|", "／")[:36],
                    (x["basis"] or "").replace("|", "／")[:60], x["kind"]))

    io.open(OUT_MD, "w", encoding="utf-8").write("\n".join(L) + "\n")

    print("=" * 70)
    print("系统能力清单")
    print("=" * 70)
    print("单元总数：%d" % r["total"])
    print("按性质：%s" % r["by_kind"])
    print("按层：%s" % r["by_layer"])
    print()
    print("ENG（工程决策，须人批）：%d 条" % len(r["eng"]))
    for x in r["eng"][:10]:
        print("   · %s  %s" % (x["id"], x["what"][:40]))
    print("\n未标注依据（缺口）：%d 条" % len(r["unlabeled"]))
    for x in r["unlabeled"][:10]:
        print("   · %s  %s" % (x["id"], x["what"][:40]))
    print("\n已写出：%s" % OUT_MD)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

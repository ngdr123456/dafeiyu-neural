# -*- coding: utf-8 -*-
"""共识核：把三本书的观点证据按**系统单元**归拢，判每个单元被几本书支持。

输出
────
    spec/共识核.jsonl     103 个单元各一行的证据表（**共识核 = 「层」为「三本」的行**）
    spec/共识核报告.md    给人看的版本

    ⚠️ 用户裁定：「**不要写空列表文件**」——
       所以即使「三本」的行是 0，也照写 103 行的证据表，而不是写一个 `[]`。

三种口径（用户裁定，都要算）
────────────────────────────────────────────────────────────
    ① 全部已实现（126 条）           —— 「层」字段用这一口径
    ② 只算稳定的（两次都已实现 73 条） —— 「层_稳定」
    ③ 严格：稳定且独立命中（70 条）    —— 「层_严格」
       （排除指定依据、待核、线索类）

    三种口径下「三本」都是 0。**这是判据与书的分布的结果，不是系统缺了什么** ——
    在「同一件事」判据、仅 126 条已实现、三本书主题不同（多巴胺／意义／自我发展）
    的条件下，单元级重叠为 0。

稳定性（用 remap_from + 侧日志算）
────────────────────────────────────────────────────────────
    两次都已实现                     73   ← 共识核候选只取这一类
    首次判定已实现                    30   ← 降一级标注
    旧已实现_第二次没复现_保留旧结论        15   ← **不属于「稳定」**，要进 T21 候选池
    旧非已实现_第二次已实现_采纳            8   ← **不属于「稳定」**（与上面 15 条同类）
    ────────────────────────────────────
    合计                          126  ✓ 对账通过

运行状态（用户裁定）
────────────────────────────────────────────────────────────
    映射到「已建未启用／仅落账」单元的观点，标 **已实现（未启用）**。
    含义：代码里写了 ≠ 真实训练里跑得到。**T21 对这类是接线（T33），不是重写。**

「依据列泄题」的影响（用户裁定的表述）
────────────────────────────────────────────────────────────
    E 跑批时提示词里的依据列是**完整的**（方案 (A)），M、DB 跑时被**截断在 52 字**。
    ⇒ 跨书的「指定依据命中数」**不可直接比较**，E 天然占优。

    ⚠️ 而且：**模型能读到依据列，所以它对「指定依据」条目的判断受依据列影响 ——
       不论方向，都不当独立验证。**
       （E-837、E-499 是依据列里写着的，模型**反而没采纳**，
        说明它不是照单全收；但这不改变"该判断受过影响"这一点。）

不碰的东西（用户裁定的范围）
────────────────────────────────────────────────────────────
    engine/map_claims.py｜engine/system_map.py
    spec/观点总表/{M,DB,E}.jsonl｜spec/重判侧日志.jsonl（**只读**）
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT_JSON = os.path.join(_ROOT, "spec", "共识核.jsonl")
OUT_MD = os.path.join(_ROOT, "spec", "共识核报告.md")
SIDE = os.path.join(_ROOT, "spec", "重判侧日志.jsonl")
BOOKS = ("M", "DB", "E")

# ★ 新增的发展水平单元 —— 直接从 system_map 导入那份常量（单一事实来源）。
#   为什么必须直连导入：导入期就绑死名字，常量被改名/删掉会**立刻 ImportError**；
#   写成 `import system_map as S` 再取属性是运行期查找，改名后会迟到才炸。
#   见 决定记录.md（T33 返工裁定）。
from system_map import DEV_UNIT_IDS          # noqa: E402
BOOK_NAME = {"M": "活出生命的意义", "DB": "贪婪的多巴胺", "E": "自我的发展"}

# ★ 待核 5 条（用户裁定）：不计证据，但**也不能悄悄离开 T21 候选池**
WAIT = {
    "E-168": "通用阶段论命题（层次／不可逆），SELF_RULES 是冲动控制规则按水平解锁 —— 宽松命中",
    "E-229": "「不变序列」同样是通用阶段论 —— 宽松命中",
    "E-156": "同时挂 const:TENSION_DRIVE(1.5)/error_low(0.15)/error_high(0.60)；"
             "常量数值书里不会有，claim 不可能「实现」一个数值",
    "E-892": "讲「行为反映不出未达到的水平」是**产出侧**；PERCEPTION_GATE 是**感知侧** —— 近亲不是同一件事",
    "M-232": "同一句里含「创造性的工作」，而创造途径是 T17 **刻意标缺**的；"
             "判它已实现会让缺口隐身",
}

ID_RE = re.compile(r"\b(?:M|DB|E)-\d+\b")

# 运行状态：UNIT 表里没有 status 键 = 原 96 个单元 = 一直生效中
ST_ON = "生效中"
ST_OFF = "已建未启用"
ST_LOG = "仅落账"


def _load_claims() -> dict:
    out = {}
    for b in BOOKS:
        p = os.path.join(_ROOT, "spec", "观点总表", "%s.jsonl" % b)
        for line in io.open(p, encoding="utf-8"):
            if line.strip():
                c = json.loads(line)
                out[c["id"]] = (b, c)
    return out


def _load_side() -> dict:
    out = {}
    if os.path.exists(SIDE):
        for line in io.open(SIDE, encoding="utf-8"):
            if line.strip():
                x = json.loads(line)
                out[x["id"]] = x
    return out


def stability(cid: str, c: dict, side: dict) -> str:
    """四分类（用户裁定）。对账：73+30+15+8 = 126。"""
    rf = c.get("remap_from")
    if not rf:
        return "首次判定已实现"
    if rf.get("status") == "已实现":
        new = side[cid]["新"] if cid in side else c.get("status")
        return "两次都已实现" if new == "已实现" else "旧已实现_第二次没复现_保留旧结论"
    return "旧非已实现_第二次已实现_采纳"


def run_status(u: dict) -> str:
    return u.get("status") or ST_ON


def main() -> int:
    import system_map as S
    units = S.collect()
    claims = _load_claims()
    side = _load_side()

    # ── 分类集合
    all_impl = {cid for cid, (b, c) in claims.items() if c.get("status") == "已实现"}
    stab = {cid for cid in all_impl if stability(cid, claims[cid][1], side) == "两次都已实现"}
    desig_all = {cid for u in units for cid in ID_RE.findall(u.get("basis") or "")}
    clue = set()
    for cid, (b, c) in claims.items():
        wy = (c.get("why_not") or "") + (side.get(cid, {}).get("新_why_not") or "")
        if any(u["id"] in wy for u in units if u["id"] in DEV_UNIT_IDS):
            clue.add(cid)
    strict = {cid for cid in stab if cid not in desig_all and cid not in WAIT and cid not in clue}

    # ── 三个口径各自的「单元 → 书 → 观点」
    def sup(cids):
        d = {}
        for cid in cids:
            b, c = claims[cid]
            for u in (c.get("maps_to") or []):
                d.setdefault(u, {}).setdefault(b, []).append(cid)
        return d

    S1, S2, S3 = sup(all_impl), sup(stab), sup(strict)

    def layer(d, uid):
        bs = [b for b in BOOKS if d.get(uid, {}).get(b)]
        return {3: "三本", 2: "两本", 1: "单本", 0: "无"}[len(bs)]

    def books_of(d, uid):
        return [b for b in BOOKS if d.get(uid, {}).get(b)]

    # ── 逐单元出证据行
    rows = []
    for u in units:
        uid = u["id"]
        desig = []
        for cid in sorted(set(ID_RE.findall(u.get("basis") or ""))):
            if cid not in claims:
                continue
            c = claims[cid][1]
            desig.append({
                "id": cid, "书": claims[cid][0],
                "稳定性": stability(cid, c, side) if c.get("status") == "已实现" else "非已实现",
                "当前状态": c.get("status"),
                # ★ 用户要求加的字段：模型**有没有**把这条判到该单元
                "模型是否确认": uid in (c.get("maps_to") or []),
            })
        hit = [cid for cid, (b, c) in claims.items() if uid in (c.get("maps_to") or [])]
        desig_ids = {d["id"] for d in desig}
        rows.append({
            "单元": uid,
            "做什么": u.get("what") or "",
            "依据": (u.get("basis") or "")[:200],
            "运行状态": run_status(u),
            "层": layer(S1, uid),
            "层_稳定": layer(S2, uid),
            "层_严格": layer(S3, uid),
            "支撑书": books_of(S1, uid),
            "指定依据": desig,
            "独立命中": sorted(c for c in hit
                             if c not in desig_ids and c not in WAIT and c not in clue),
            "待核": sorted(c for c in hit if c in WAIT),
            "线索类": sorted(c for c in clue
                           if uid in ((claims[c][1].get("why_not") or "")
                                      + (side.get(c, {}).get("新_why_not") or ""))),
            "泄题风险": ("该单元依据列在 E 跑批时**完整可见**（方案 A）；"
                         "M/DB 跑批时被截断在 52 字" if uid in DEV_UNIT_IDS else ""),
        })

    # ── ★ 召回检验（用户补的第 1 项，不花 API）
    #
    #   问：依据列里写的观点，有多少被模型判成已实现、并**回映到该单元**？
    #   这是"指定依据"这条路的**召回率** —— 它给"单元级重叠为 0"提供解释：
    #   如果召回本身就不高，那 0 有一部分来自判据偏严，不能全算成"书里没有共识"。
    withid = [u for u in units if ID_RE.findall(u.get("basis") or "")]
    recall = []
    d_all, ok_all, uniq_d, uniq_ok = 0, 0, set(), set()
    for u in withid:
        desig = sorted(set(ID_RE.findall(u.get("basis") or "")))
        ok = [c for c in desig
              if c in claims and u["id"] in (claims[c][1].get("maps_to") or [])]
        miss = [{"id": c, "当前状态": claims[c][1].get("status") if c in claims else "不存在"}
                for c in desig if c not in ok]
        recall.append({"单元": u["id"], "依据": desig, "回映": ok, "未回映": miss,
                       "是否新增": u["id"] in DEV_UNIT_IDS})
        d_all += len(desig); ok_all += len(ok)
        uniq_d |= set(desig); uniq_ok |= set(ok)
    r_recall = {"按单元": recall,
                "依据条数": d_all, "回映条数": ok_all,
                "依据去重": len(uniq_d), "回映去重": len(uniq_ok),
                "召回率": round(100.0 * ok_all / max(1, d_all), 1),
                "召回率_去重": round(100.0 * len(uniq_ok) / max(1, len(uniq_d)), 1),
                "带编号单元数": len(withid),
                "老单元里带编号的": len([u for u in withid if not u.get("status")])}

    io.open(OUT_JSON, "w", encoding="utf-8").write(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    # ── 报告
    from collections import Counter
    lv1 = Counter(r["层"] for r in rows)
    lv2 = Counter(r["层_稳定"] for r in rows)
    lv3 = Counter(r["层_严格"] for r in rows)
    L = ["# 共识核报告", "",
         "> 由 `engine/consensus.py` 生成。**共识核 = 「层」为「三本」的行。**", "",
         "## 一句话", "",
         "**在「同一件事」判据、仅 126 条已实现、三本书主题不同"
         "（多巴胺／意义／自我发展）的条件下，单元级重叠为 0。**", "",
         "这不是「系统缺了什么」—— 是判据与书的分布的结果。", "",
         "### 定性（用户裁定，2026-10-02）", "",
         "**交集为 0 是正常且健康的结果。**", "",
         "它说明三本书是**三维正交、各司其职**的：", "",
         "| 书 | 维度 | 管什么 |", "|---|---|---|",
         "| 贪婪的多巴胺 | **生理动力** | 想要／喜欢的生化回路 |",
         "| 自我的发展 | **心智阶段** | 自我能看见什么、能行使哪条规则 |",
         "| 活出生命的意义 | **精神态度** | 面对不可改变之事取什么姿态 |", "",
         "**它们本来就不是同义反复** —— 一个讲「力气从哪来」，一个讲「人长到哪一步」，",
         "一个讲「往哪去」。三者互相**不可替代**，所以单元级重叠为 0 不是缺陷，",
         "**是这套材料本身的结构**。", "",
         "⚠️ **但这个 0 有一部分来自判据偏严**：已知**召回上限约 %.0f%%**"
         "（依据列里 %d 条观点，只有 %d 条被模型判成已实现并回映到该单元）。"
         "所以「重叠为 0」不能单独读成「书里没有共识」——"
         "**要等召回检验的完整结果再看**。" % (r_recall["召回率"], r_recall["依据条数"],
                                                r_recall["回映条数"]), "",
         "## 三种口径", "",
         "| 口径 | 参与计算 | 三本 | 两本 | 单本 | 无 |", "|---|---|---|---|---|---|"]
    for name, cids, lv in (("① 全部已实现", len(all_impl), lv1),
                           ("② 只算稳定的", len(stab), lv2),
                           ("③ 严格：稳定且独立命中", len(strict), lv3)):
        L.append("| %s | %d 条 | %d | %d | %d | %d |"
                 % (name, cids, lv.get("三本", 0), lv.get("两本", 0),
                    lv.get("单本", 0), lv.get("无", 0)))
    L += ["", "## 口径①下「两本」的单元", ""]
    for r in rows:
        if r["层"] == "两本":
            L.append("- `%s`　%s　— %s" % (r["单元"], r["支撑书"], r["做什么"][:44]))
    L += ["", "## 稳定性对账", "",
          "| 类别 | 条数 |", "|---|---|"]
    sc = Counter(stability(cid, claims[cid][1], side) for cid in all_impl)
    for k in ("两次都已实现", "首次判定已实现",
              "旧已实现_第二次没复现_保留旧结论", "旧非已实现_第二次已实现_采纳"):
        L.append("| %s | %d |" % (k, sc.get(k, 0)))
    L.append("| **合计** | **%d** |" % sum(sc.values()))
    L += ["", "⚠️ 后两类**不属于「稳定」**，与 T21 候选池相关。", "",
          "## 运行状态", "",
          "| 运行状态 | 单元数 | 含义 |", "|---|---|---|",
          "| 生效中 | %d | 真实训练里跑得到 |" % sum(1 for r in rows if r["运行状态"] == ST_ON),
          "| 已建未启用 | %d | 代码写了，训练里不执行 |" % sum(1 for r in rows if r["运行状态"] == ST_OFF),
          "| 仅落账 | %d | 算出来落进台账，不影响决定 |" % sum(1 for r in rows if r["运行状态"] == ST_LOG),
          "", "**T21 对「已建未启用／仅落账」的处置是接线（T33），不是重写。**", "",
          # ★ 「T33 接线范围」是**冻结的工程交付基准**（用户裁定，方案甲）
          #
          #   用户原话：
          #   > 「接线清单是 T33 的工程交付基准，**不能因单元通电成功而在报表里自我蒸发**。」
          #
          #   第一版的判据是 `if 运行状态 == "生效中": continue` ——
          #   于是 5 个单元一通电，属于它们的 12 条命中就从清单里消失了（19 → 7）。
          #   **判据必须是"这个单元是不是新增的发展水平单元"（带不带 status 键），
          #   而不是"它现在通没通电"。** 通电前后都该是 19 条。
          "## T33 接线范围（**冻结**，不随运行状态变化）", "",
          "判据：**`system_map.DEV_UNIT_IDS` 里显式列出的 7 个单元 id**"
          "（与 `_DEV_UNITS` 表同源，带一致性断言），**不看它当前的值**。", "",
          "**这是 T33 的工程交付基准 —— 通电前后都是这 7 个单元、19 条观点。**", "",
          "⚠️ 这些说的是「代码里写了」，不是「真实训练里跑得到」。", ""]
    n_wire = 0
    # ★ 判据：**显式的 7 单元 id 集合**，从 system_map 的同一份常量导出。
    #
    #   用户裁定（T33 返工）：
    #   > 「不许用『带 status 键』这种间接判据……改成显式的 7 单元 id 集合。」
    #   间接判据的毛病：哪天给某个老单元加个 status 字段，它会**悄悄**混进
    #   接线范围，而没人注意到。显式列出 id，"范围变了"就必须改代码。
    for r in rows:
        if r["单元"] not in DEV_UNIT_IDS:
            continue
        hits = ([d["id"] for d in r["指定依据"] if d["模型是否确认"]]
                + list(r["独立命中"]) + list(r["待核"]))
        if not hits:
            continue
        n_wire += len(hits)
        L.append("- **`%s`**（%s）—— %d 条命中" % (r["单元"], r["运行状态"], len(hits)))
        for d in r["指定依据"]:
            if d["模型是否确认"]:
                L.append("    - 指定依据 `%s` [%s] %s" % (d["id"], d["书"], d["稳定性"]))
        for c in r["独立命中"]:
            L.append("    - 独立命中 `%s`" % c)
        for c in r["待核"]:
            L.append("    - **待核** `%s`" % c)
    L.append("")
    L.append("**合计 %d 条命中（去重 %d 个观点）。**"
             % (n_wire, len({i for r in rows
                             if r["单元"] in DEV_UNIT_IDS
                             for i in ([d["id"] for d in r.get("指定依据") or []
                                        if d.get("模型是否确认")]
                                       + list(r.get("独立命中") or [])
                                       + list(r.get("待核") or []))
            if r["单元"] in DEV_UNIT_IDS})))
    L.append("")
    L.append("**T21 对这些的处置是接线（T33 通电），不是重写。**")
    L.append("")
    L.append("⚠️ 本节的条数**不随通电变化**。"
             "各单元**当前**通没通电，见上面「运行状态」一节。")
    L += ["", "## 召回检验", "",
          "| 项 | 值 |", "|---|---|",
          "| 依据列带 claim 编号的单元 | %d 个（老 96 个里 **%d 个**——"
          "老约定用 [E]/[M]/[D]+页码，所以口径③对老单元是**空操作**） |"
          % (r_recall["带编号单元数"], r_recall["老单元里带编号的"]),
          "| 依据条数 | %d（去重 %d） |" % (r_recall["依据条数"], r_recall["依据去重"]),
          "| 回映条数 | %d（去重 %d） |" % (r_recall["回映条数"], r_recall["回映去重"]),
          "| **召回率** | **%.1f%%**（去重 %.1f%%） |"
          % (r_recall["召回率"], r_recall["召回率_去重"]), "",
          "### 未回映的（模型没判回该单元）", ""]
    for rec in r_recall["按单元"]:
        for m in rec["未回映"]:
            L.append("- `%s` 的依据 `%s` **未回映**｜当前状态 %s"
                     % (rec["单元"], m["id"], m["当前状态"]))
    # ── 主张级一节（读丙的产出；没有就跳过）
    L += ["", "## 主张级共识核（丙）", "",
          "由 `engine/consensus_claims.py --claims` 生成"
          "（提炼 12 批 + 交叉 1 批，跑两遍 = 26 批）。", ""]
    pj = os.path.join(_ROOT, "spec", "共识核_主张级.jsonl")
    if os.path.exists(pj):
        rows2 = [json.loads(l) for l in io.open(pj, encoding="utf-8") if l.strip()]
        nA = sum(1 for x in rows2 if x.get("档") == "A")
        L += ["| 项 | 值 |", "|---|---|",
              "| 产出条数 | %d |" % len(rows2),
              "| **档 A（两遍一致）** | **%d 条** |" % nA,
              "| 档 B（未复现／单列待裁） | %d 条 |" % (len(rows2) - nA), ""]
        for x in rows2:
            if x.get("档") != "A" and x.get("共识"):
                L += ["**未复现条目（不进共识核）**：", "",
                      "> %s" % x["共识"], "",
                      "用户裁定：「直接作为**未复现条目**归档，不进共识核。"
                      "它的概念太宽泛，落不成具体判据。」", ""]
    L += ["", "## 泄题风险", "",
          "E 跑批时依据列**完整可见**，M/DB 被**截断在 52 字** —— 跨书的「指定依据命中数」"
          "**不可直接比较**。", "",
          "**模型能读到依据列，所以它对「指定依据」条目的判断受依据列影响 —— "
          "不论方向，都不当独立验证。**", "",
          "（E-837、E-499 是依据列里写着的，模型**反而没采纳**，说明它不是照单全收；"
          "但这不改变「该判断受过影响」这一点。）"]
    io.open(OUT_MD, "w", encoding="utf-8").write("\n".join(L) + "\n")

    # ── 控制台
    print("=" * 80)
    print("共识核｜%d 个单元" % len(rows))
    print("=" * 80)
    print()
    print("三种口径：")
    for name, cids, lv in (("① 全部已实现", len(all_impl), lv1),
                           ("② 只算稳定的", len(stab), lv2),
                           ("③ 严格：稳定且独立命中", len(strict), lv3)):
        print("   %-22s 参与 %3d 条｜三本 %d｜两本 %d｜单本 %d｜无 %d"
              % (name, cids, lv.get("三本", 0), lv.get("两本", 0),
                 lv.get("单本", 0), lv.get("无", 0)))
    print()
    print("口径①下「两本」的单元：")
    for r in rows:
        if r["层"] == "两本":
            print("   %-30s %s" % (r["单元"], r["支撑书"]))
    print()
    print("稳定性对账：")
    for k in ("两次都已实现", "首次判定已实现",
              "旧已实现_第二次没复现_保留旧结论", "旧非已实现_第二次已实现_采纳"):
        print("   %-36s %3d" % (k, sc.get(k, 0)))
    print("   %-36s %3d %s" % ("合计", sum(sc.values()),
                               "✓ = 126" if sum(sc.values()) == 126 else "★ ≠126"))
    print()
    print("共识核（层=三本）：**%d 条**" % lv1.get("三本", 0))
    print()
    print("召回检验：依据 %d 条（去重 %d）｜回映 %d 条（去重 %d）｜**召回率 %.1f%%**（去重 %.1f%%）"
          % (r_recall["依据条数"], r_recall["依据去重"],
             r_recall["回映条数"], r_recall["回映去重"],
             r_recall["召回率"], r_recall["召回率_去重"]))
    for rec in r_recall["按单元"]:
        for m in rec["未回映"]:
            print("   未回映 %-8s ← %s｜当前状态 %s" % (m["id"], rec["单元"], m["当前状态"]))
    print()
    print("T33 接线范围（冻结）：%d 条命中（system_map.DEV_UNIT_IDS 那 7 个，与通电与否无关）"
          % n_wire)
    print()
    print("已写出：%s" % OUT_JSON)
    print("已写出：%s" % OUT_MD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

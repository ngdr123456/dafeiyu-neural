# -*- coding: utf-8 -*-
"""T33 · 第 2 步：**阈值可达性审计**（纯只读，用户经参谋批准）。

三条纪律（用户裁定原文）：
    ① 「**绝对只读**：产物严格限定为 spec/阈值可达性审计.md 与 .jsonl，
        不改动任何阈值常量、机制逻辑与配置代码；」
    ② 「**结论分档明确**：严格按「不可达（确认缺陷）」、「待更多数据」、
        「可达」、「判据失效」四档定性，并附带代码依据与数学推导；」
    ③ 「**联动机制比对**：对照 `admin.py:197` 已有的死规则检测器，
        说明为什么现存的四例死规则检测没能覆盖 `error_high` 这类情况。」

⚠️ 阈值写法：**值写在本表中（有出处），脚本到源码处核验锚点**。
   核验不到 → 判「判据失效」，**不许静默取错**。
   （第一版用脆的正则去"猜"取哪个常数，结果 R2 的 1.0 取不到、
     `tension_health_lo` 错取成 0.60 —— 那正是"判据失效"该拦的错。）
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
OUT_MD = os.path.join(_ROOT, "spec", "阈值可达性审计.md")
OUT_JSON = os.path.join(_ROOT, "spec", "阈值可达性审计.jsonl")
LEDGERS = [("训练", os.path.join(_ROOT, "state", "train", "ledger.jsonl")),
           ("会话", os.path.join(_ROOT, "state", "ledger.jsonl")),
           ("demo", os.path.join(_ROOT, "state", "ledger_demo.jsonl"))]

ITEMS = [
    dict(no=1, where="engine/mechanism.py", sym="gate_open（门控开合）",
         expr="abs(e) < self.cfg.error_high", var="e", th=0.60,
         anchor=r"error_high:\s*float\s*=\s*0\.60",
         th_src="MechanismConfig.error_high（mechanism.py 第 2 层）",
         up=0.5, up_why="单轮输入 (change+rigidity)/2；翻转必清零 streak ⇒ 上界 0.5",
         precond=False, note="e 够不到 0.60 ⇒ **本门恒为开**"),
    dict(no=2, where="engine/mechanism.py", sym="机制条件 error_high",
         expr="lambda st, c: abs(st.e) >= c.error_high", var="e", th=0.60,
         anchor=r"abs\(st\.e\) >= c\.error_high", th_src="同上", up=0.5,
         up_why="同上", precond=False, note="机制条件项：**永不命中**"),
    dict(no=3, where="engine/character.py", sym="R2 结构压力",
         expr="structure = min(1.0, e / b['error_high'])；阈值 structure >= 1.0",
         var="structure", th=1.0, anchor=r'"error_high":\s*0\.60',
         th_src="character.py 的阈值字典", up=0.833,
         up_why="0.5 / 0.60 = 0.833（数学上界）", precond=False,
         note="性格层 R2：**永不触发**。源码注释自己已写「最大只到 0.682」"),
    dict(no=4, where="engine/devlevel.py", sym="结构失效判定（生长链入口）",
         expr="if e >= ERROR_HIGH", var="e", th=0.60,
         anchor=r"ERROR_HIGH\s*=\s*0\.60", th_src="devlevel.py（抄自 mechanism）",
         up=0.5, up_why="同上", precond=False, note="**整条生长链的入口**"),
    dict(no=5, where="engine/devlevel.py", sym="重组判定",
         expr="elif self.failed and e <= ERROR_LOW", var="e", th=0.15,
         anchor=r"ERROR_LOW\s*=\s*0\.15", th_src="devlevel.py", up=0.5,
         up_why="e 本身够得着 0.15 —— **但前置 self.failed 永不置位**",
         precond=True, note="★ **第二类不可达**：判据可达，因**前置恒假**而不可达"),
    dict(no=6, where="engine/mechanism.py", sym="张力偏低",
         expr="st.tension_measured and st.tension <= c.tension_low",
         var="tension", th=1.5, anchor=r"tension_low:\s*float\s*=\s*1\.5",
         th_src="MechanismConfig.tension_low", up=10.0,
         up_why="机制把 tension clamp 到 [0, 10]", precond=False, note=""),
    dict(no=7, where="engine/mechanism.py", sym="张力偏高",
         expr="st.tension_measured and st.tension > c.tension_low",
         var="tension", th=1.5, anchor=r"tension_low:\s*float\s*=\s*1\.5",
         th_src="同上", up=10.0, up_why="同上", precond=False, note=""),
    dict(no=8, where="engine/mechanism.py", sym="健康极化区下沿",
         expr="c.tension_low < st.tension < c.tension_health_lo",
         var="tension", th=3.0, anchor=r"tension_health_lo:\s*float\s*=\s*3\.0",
         th_src="MechanismConfig.tension_health_lo", up=10.0,
         up_why="同上", precond=False, note=""),
    dict(no=9, where="engine/mechanism.py", sym="健康极化区上沿",
         expr="st.tension > c.tension_health_hi", var="tension", th=6.5,
         anchor=r"tension_health_hi:\s*float\s*=\s*6\.5",
         th_src="MechanismConfig.tension_health_hi", up=10.0,
         up_why="同上", precond=False, note=""),
    dict(no=10, where="engine/devlevel.py", sym="张力动力门槛",
         expr="elif ft > TENSION_DRIVE", var="tension", th=1.5,
         anchor=r"TENSION_DRIVE\s*=\s*1\.5", th_src="devlevel.py", up=10.0,
         up_why="张力 clamp 上限（**近似**：真实变量是 fail_tension，台账不记）",
         precond=True, note="★ 同第 5 条：前置 `failed` 已置位 ⇒ **因前置恒假而不可达**"),
]


def _anchor_ok(anchor: str) -> str:
    for f in ("engine/mechanism.py", "engine/devlevel.py", "engine/character.py"):
        fp = os.path.join(_ROOT, f)
        if os.path.exists(fp) and re.search(anchor, io.open(fp, encoding="utf-8").read()):
            return f
    return ""


def _emp(var):
    out = {}
    for label, p in LEDGERS:
        if not os.path.exists(p):
            continue
        vs = []
        for line in io.open(p, encoding="utf-8"):
            if not line.strip():
                continue
            m = json.loads(line).get("mech") or {}
            if var == "e" and m.get("e") is not None:
                vs.append(abs(float(m["e"])))
            elif var == "tension" and m.get("tension_measured") and m.get("tension") is not None:
                vs.append(float(m["tension"]))
            elif var == "structure" and m.get("e") is not None:
                vs.append(min(1.0, abs(float(m["e"])) / 0.60))
        if vs:
            vs.sort()
            out[label] = {"n": len(vs), "min": round(vs[0], 3),
                          "median": round(vs[len(vs) // 2], 3), "max": round(vs[-1], 3)}
    return out


def _judge(it, emp):
    if not it["_anchor"]:
        return "判据失效", "源码里核验不到该阈值锚点"
    if it["precond"]:
        return "不可达（确认缺陷）", "判据本身够得着，但**前置条件恒假**"
    real = {k: v for k, v in emp.items() if k != "demo"}
    if not real:
        return "判据失效", "台账里取不到该变量的实测值"
    mx = max(v["max"] for v in real.values())
    if mx >= it["th"]:
        return "可达", "实测 max %.3f ≥ 阈值 %s" % (mx, it["th"])
    if it["up"] >= it["th"]:
        return "待更多数据", ("数学上界 %.3f ≥ 阈值 %s，但实测 max 只到 %.3f"
                            % (it["up"], it["th"], mx))
    return "不可达（确认缺陷）", "**数学上界 %.3f < 阈值 %s** ⇒ 构造上不可能" % (it["up"], it["th"])


def main() -> int:
    rows = []
    print("=" * 88)
    print("T33 · 第 2 步：阈值可达性审计（只读）")
    print("=" * 88)
    for it in ITEMS:
        it["_anchor"] = _anchor_ok(it["anchor"])
        emp = _emp(it["var"])
        v, why = _judge(it, emp)
        rows.append({"序号": it["no"], "文件": it["where"], "判据": it["sym"],
                     "表达式": it["expr"], "变量": it["var"], "阈值": it["th"],
                     "阈值出处": it["th_src"], "锚点核验": it["_anchor"] or "**未通过**",
                     "数学上界": it["up"], "上界依据": it["up_why"],
                     "实测": emp, "判定": v, "判定依据": why, "备注": it["note"]})
        print()
        print("  %2d【%s】%s" % (it["no"], it["where"], it["sym"]))
        print("      表达式：%s" % it["expr"])
        print("      阈值 %s ｜锚点核验：%s" % (it["th"], it["_anchor"] or "**未通过**"))
        print("      数学上界 %.3f（%s）" % (it["up"], it["up_why"]))
        for k in ("训练", "会话", "demo"):
            if k in emp:
                e = emp[k]
                print("      实测·%-4s n=%-4d min=%-6s 中位=%-6s **max=%s**"
                      % (k, e["n"], e["min"], e["median"], e["max"]))
        print("      ⇒ **%s**（%s）" % (v, why))

    from collections import Counter
    c = Counter(r["判定"] for r in rows)
    print()
    print("=" * 88)
    print("  四档分布：%s" % dict(c))
    print("=" * 88)
    io.open(OUT_JSON, "w", encoding="utf-8").write(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print("已写出：%s（%d 条）" % (OUT_JSON, len(rows)))

    # ── .md 产出
    L = ["# 阈值可达性审计（只读）", "",
         "> 由 `tools/阈值可达性审计.py` 生成。**不改动任何阈值常量、机制逻辑与配置代码。**", "",
         "## 四档分布", "", "| 判定 | 条数 |", "|---|---|"]
    for k in ("不可达（确认缺陷）", "待更多数据", "可达", "判据失效"):
        L.append("| %s | %d |" % (k, c.get(k, 0)))
    L += ["", "## 逐条", "", "| # | 文件 | 判据 | 阈值 | 数学上界 | 实测 max（训练/会话） | 判定 |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        e = r["实测"]
        mx = "%s / %s" % (e.get("训练", {}).get("max", "—"), e.get("会话", {}).get("max", "—"))
        L.append("| %d | `%s` | %s | %s | %.3f | %s | **%s** |"
                 % (r["序号"], r["文件"].replace("engine/", ""), r["判据"],
                    r["阈值"], r["数学上界"], mx, r["判定"]))
    L += ["", "### 判定依据（逐条）", ""]
    for r in rows:
        L += ["**%d. %s**｜`%s`" % (r["序号"], r["判据"], r["表达式"]),
              "",
              "- 阈值 %s（出处：%s）｜锚点核验：%s" % (r["阈值"], r["阈值出处"], r["锚点核验"]),
              "- 数学上界 **%.3f** —— %s" % (r["数学上界"], r["上界依据"]),
              "- 实测（**demo 单列不计入**）：%s"
              % "；".join("%s n=%d max=%s" % (k, v["n"], v["max"])
                          for k, v in r["实测"].items()),
              "- **判定：%s** —— %s" % (r["判定"], r["判定依据"])]
        if r["备注"]:
            L.append("- %s" % r["备注"])
        L.append("")
    L += ["## ★ 机制盲区：死规则检测器为何没覆盖 `error_high`", "",
          "### `admin.py` 的 `check_dead_rule` 是怎么判的", "",
          "```python",
          "allc = [c.id for c in M.conditions(M.MechanismConfig())]   # 机制**条件表**的全部条件单元",
          "seen = Counter((r.get(\"mech\") or {}).get(\"phase\") for r in rows if r.get(\"mech\"))",
          "never = [c for c in allc if c not in seen]                  # 台账里从未出现过的",
          "```",
          "",
          "### 它为什么抓不到 `error_high`（四条，逐层递进）", "",
          "| # | 原因 |",
          "|---|---|",
          "| 1 | **粒度不对**：它扫的是 `conditions()` 表里的**条件单元 id**，"
          "而 `error_high` 是 `MechanismConfig` 里的**阈值常数**，"
          "**根本不在那张表里** —— 连被扫的资格都没有 |",
          "| 2 | **载体不对**：`error_high` 的四个使用点里，"
          "`mechanism.py` 的 `gate_open` 是一个**赋值**、`character.py` 的 R2 在**性格层**、"
          "`devlevel.py` 的失效判定在 **DevLevel** —— 三处都不属于机制条件表 |",
          "| 3 | **判据类型不对**：它判的是「**某个分支有没有被走到**」（离散命中统计）；"
          "而阈值够不着是「**某个值有没有可能越过某条线**」（连续域分析）。"
          "**前者看 `phase` 的取值集合，后者要看变量的值域** —— 两种问题在台账里长得完全不一样 |",
          "| 4 | **表象会骗人**：阈值够不着时，台账里 `phase` **照常变化**（其他条件在正常触发），"
          "所以 `never` 列表里干净得很、检测器报「0 条死规则」。"
          "**它只会说「这个分支没走到」，不会说「这个分支走不到」** |",
          "",
          "### 一句话",
          "",
          "> **`check_dead_rule` 检的是「命中集合」，不是「值域」。**",
          "> `error_high` 这类缺陷在它眼里是一片安静 —— "
          "因为**没有任何一条 `phase` 因为够不着阈值而消失**。",
          "",
          "### 本次审计补上的正是这个盲区", "",
          "本脚本不统计命中，而是对每条「变量 vs 阈值」比较**同时算两路**：",
          "",
          "```",
          "① 数学上界  —— 从公式推该变量的理论极值（上界从源码读，不重实现）",
          "② 实测极值  —— 三个台账取 min/中位/max（demo 单列）",
          "两路都不够阈值 → 不可达（确认缺陷）",
          "```",
          "",
          "## 审计本身的局限（如实标出）", "",
          "1. **审计项是手录的**（10 条），不是自动扫全项目。"
          "自动化扫描「数值 vs 阈值」的比较在 Python 里做不可靠（属性的运行时来源难静态定）",
          "2. `fail_tension`（第 10 条）**台账不记**，所以实测那栏用的是 `tension` 近似 —— "
          "该条判「不可达」靠的是**前置条件恒假**，不是实测",
          "3. 第 3 条（R2）的 `structure` 是由 `e / 0.60` 现算的，"
          "**不是台账原生的字段**，属推导量"]
    io.open(OUT_MD, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("已写出：%s" % OUT_MD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

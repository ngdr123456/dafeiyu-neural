# -*- coding: utf-8 -*-
"""对照实验：**接台账（延续态）vs 冷启动态**，看到底有没有差别。

为什么做这个 —— 管理员要求的，不是我自己想到的
────────────────────────────────────────────────────────────
    我补"元提问轮没内部读数"这个缺陷时，顺手加了一处**它没要求的东西**：
    从台账接上"上次结束时的状态"，理由是"系统的状态本来就跨会话延续"。

    管理员验收时把我这处定性为 **ENG（无独立依据的判据）**，并给了条件：

    > 「对『跨会话接上台账上次结束状态』做**对照实验** —— 同一批元提问分别在
    >   冷启动态与延续态下跑，看管理员可审计条数是否由延续态贡献。
    >   **若②对照无差异则回退为冷启动态。**」

    也就是说：**这处修复得挣到自己的位置，挣不到就删掉。**
    这是管理员该做的事，我按它的条件执行。

判据（提前写死，免得跑完才想怎么算赢）
────────────────────────────────────────────────────────────
    自变量：`seed_from_ledger`（True=延续态 / False=冷启动态）
    因变量：**该轮的管理员可审计条数**（mech 键数 > 0 即算可审计）
    同一批元提问、同一段历史台账、同一套代码，只有开关不同。

    结论规则：
      · 延续态可审计数 **显著高于** 冷启动态 → 这处修复有效，保留
      · 两者**无差异** → 回退为冷启动态（管理员的条件）
"""
from __future__ import annotations

import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "engine"), os.path.join(_ROOT, "state")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 同一批元提问。**它们本身就是"在问系统"的话**，会走元提问分支。
META_BATCH = [
    "你在干嘛",
    "你现在用的是什么模型",
    "你能帮我吗",
    "你是人吗",
    "我该说什么",
    "你愿意了解我吗",
    "为什么你只是重复我的话",
    "你觉得我怎么样",
]

# 用来先造一段历史的普通对话（让台账里有状态可接）
SEED_TURNS = [
    "都是他们害的，我当初要是不听他们的就好了。",
    "我怕别人怎么看我，同事都在背后说。",
]


def run_once(seed: bool, workdir: str) -> dict:
    from pipeline import Pipeline
    lp = os.path.join(workdir, "ledger.jsonl")
    cp = os.path.join(workdir, "char.json")
    # ① 先造历史（两种模式共用同一段历史，所以历史不是变量）
    p0 = Pipeline(ledger_path=lp, auto_audit=False, character_path=cp, use_api=False)
    for t in SEED_TURNS:
        p0.turn(t, None)
    # ② 新会话跑同一批元提问，只改一个开关
    p = Pipeline(ledger_path=lp, auto_audit=False, character_path=cp,
                 use_api=False, seed_from_ledger=seed)
    rows = []
    for q in META_BATCH:
        r = p.turn(q, None)
        m = r.mech or {}
        rows.append({"q": q, "behavior": r.behavior, "keys": len(m),
                     "auditable": bool(m), "seeded": bool(m.get("_seeded"))})
    return {"mode": "延续态" if seed else "冷启动态", "seed": seed,
            "rows": rows,
            "auditable": sum(1 for x in rows if x["auditable"]),
            "total": len(rows)}


def main() -> int:
    base = tempfile.mkdtemp(prefix="ego_ctrl_")
    # 两种模式各用一个独立工作目录：台账不同，其余全同。
    # ⚠️ 上一版我把这里写成了一行嵌套技巧，既难读又直接报错 —— 改直白。
    a_dir = os.path.join(base, "carry")
    b_dir = os.path.join(base, "cold")
    os.makedirs(a_dir, exist_ok=True)
    os.makedirs(b_dir, exist_ok=True)
    a = run_once(True, a_dir)
    b = run_once(False, b_dir)

    print("=" * 76)
    print("对照实验：接台账（延续态）vs 冷启动态")
    print("=" * 76)
    print("自变量：seed_from_ledger｜因变量：该轮管理员**可审计条数**（mech 键数>0）")
    print("同一批元提问 %d 条、同一段历史、同一套代码，只改这一个开关。"
          % len(META_BATCH))
    print()
    for run in (a, b):
        print("【%s】可审计 %d / %d" % (run["mode"], run["auditable"], run["total"]))
        for x in run["rows"]:
            print("   %-22s 行为=%-11s mech键数=%-3d %s%s"
                  % (x["q"][:20], x["behavior"], x["keys"],
                     "可审计" if x["auditable"] else "**看不见**",
                     "（来自台账）" if x["seeded"] else ""))
        print()
    d = a["auditable"] - b["auditable"]
    print("-" * 76)
    print("差异：%+d 条（延续态 %d － 冷启动态 %d）" % (d, a["auditable"], b["auditable"]))
    if d > 0:
        print("结论：**有差异** —— 这处修复确实在供给可审计性，按管理员的条件**保留**。")
    else:
        print("结论：**无差异** —— 按管理员的条件，这处修复**应当回退为冷启动态**。")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

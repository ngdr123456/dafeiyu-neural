# -*- coding: utf-8 -*-
"""交集：从观点总表里找**互相矛盾的观点**，产出待裁队列。

用户要求：「做并集交集整理，形成逻辑闭环」。
并集＝每条都有归宿（map_claims.py）。交集＝观点之间不矛盾（本模块）。

为什么不做两两比对
    2921 条观点有 421 万对。逐对判断既贵又荒谬 —— 而且我试过：
    那种做法找出来的绝大多数是"措辞不同、意思相同"，噪声会把真矛盾埋掉。

做法：**按题聚类，簇内找矛盾**
    1. 给一个话题（如「苦难」）和它的关键词
    2. 把总表里命中的观点全取出来
    3. 交给模型：**这些里面有没有两条互相矛盾？**
    4. 只输出"矛盾对"，每条必须指出两条的 id 与矛盾点

⭐ 校验规矩（这是本模块可信度的全部来源）
    **先用已知的 8 条裁决试。** 规格里已经冻结了 8 处冲突（平衡／价值中立／
    自由与决定／快乐的地位／发展上限／想要vs意义／苦难／系统能否宣布目标）。
    如果本工具在「苦难」簇里**找不出**已知的 C7 冲突，那它就是坏的，
    它之后报的任何"没发现矛盾"都不算数。

⚠️ 只报告，不裁决。裁决是价值判断，由人或管理员做，写回冲突裁决表。
"""
from __future__ import annotations

import io
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包成 exe 后 `__file__` 指向解包出的临时目录 —— 于是 rules/corpus 找不到，
# 而且**台账会写进临时目录、退出就丢**。所以允许用 EGO_ROOT 指定项目根，
# 由启动器（exe）在导入任何引擎模块之前设置。
# 不设 EGO_ROOT 时行为与从前完全一致（源码运行时就是这个分支）。
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CAND = os.path.join(_ROOT, "spec", "待裁矛盾队列.jsonl")

FIND_SYSTEM = """你在找**互相矛盾的观点**。

给你一批来自同一主题的论点，每条有 id 与内容。你要找出**哪两条互相矛盾**。

什么算矛盾（判据要严）：
  · 两条**不能同时为真**。甲说"苦难只有不可避免时才有意义"，
    乙说"苦难本身就有意义" —— 这两条不能同时成立，算矛盾。
  · 甲说"X 是 A"，乙说"X 不是 A" —— 算。

什么**不算**矛盾（这些是噪声，报出来会被骂）：
  · 只是措辞不同、意思相近（最常见）
  · 一条更细、一条更粗（这是细化，不是矛盾）
  · 一条讲群体、一条讲个体（不同层级，除非作者混用了）
  · 一条是"某人认为"（转述），另一条是作者自己的主张 —— 除非作者明确反驳
  · 角度不同但可并存（如"多巴胺带来动力"与"意义带来方向"）

⚠️ **宁可少报，不可错报。** 找不到矛盾就回空数组 —— 那是合法答案。
   报一堆假矛盾比不报更坏：真矛盾会被埋在噪声里，而且人会开始不信任这个工具。

只输出 JSON 数组：
[{"a":"id1","b":"id2","why":"两条为什么不能同时为真（一句话）","kind":"真冲突|假冲突"}]

`kind` 的含义（与规格 §1 一致）：
  · 真冲突 = 两条确实不能同时为真，必须判给一边
  · 假冲突 = 看起来矛盾，其实是**不同的量或不同的层**，说清楚就能并存

不要输出别的字。"""


def cluster(claims: list[dict], keywords: list[str], limit: int = 15) -> list[dict]:
    """按关键词取一个话题簇，**并按书均衡取样**。

    ⚠️ 实测发现的真限制（写在这里，免得后人以为它能找跨书矛盾）：
       第一版就是"关键词命中后取前 N 条"。结果是**簇会整体倒向一本书**：
       「想要 vs 意义」簇 15 条**全部来自《贪婪的多巴胺》**，另两本零条。
       而规格里冻结的 8 处冲突有 6 处是**跨书**的 ——
       一本书内部按定义不会有"跨书矛盾"这种东西。

       后果很隐蔽：工具会**静默地报"没发现矛盾"**，而那看起来像
       "这两条并不矛盾"，其实只是**它们从没被放进同一个簇**。

    修法：先按书分组，再轮转取样。这样每本书都必然在簇里有代表，
    跨书矛盾才有可能被看见。
    """
    hit = [c for c in claims
           if any(k in (c.get("claim") or "") + (c.get("quote") or "")
                  for k in keywords)]
    by_book: dict[str, list[dict]] = {}
    for c in hit:
        by_book.setdefault(c.get("book") or "?", []).append(c)
    out: list[dict] = []
    i = 0
    while len(out) < limit and any(len(v) > i for v in by_book.values()):
        for b in sorted(by_book):                  # 轮转：每轮每本书各取一条
            if len(out) >= limit:
                break
            if len(by_book[b]) > i:
                out.append(by_book[b][i])
        i += 1
    return out


def find(topic: str, keywords: list[str], limit: int = 15, dry: bool = False) -> dict:
    """在话题簇里找矛盾。

    ⚠️ 实测坑：limit=40 时**三次重试全部空正文**（finish=length）——
       推理模型把输出预算全花在"想"上，正文一个字没写。
       后果不是报错，而是**静默地"没发现矛盾"**，那比报错坏得多：
       校验时「苦难」簇因此 0 命中，看起来像"这两条并不矛盾"。
       所以默认降到 15 条，并且**空正文必须当成失败说出来**，不许当成"无矛盾"。
    """
    import claims as C
    allc = C.load()
    got = cluster(allc, keywords, limit)
    print("话题「%s」：命中 %d 条（上限 %d）" % (topic, len(got), limit))
    if len(got) < 2:
        return {"topic": topic, "n": len(got), "pairs": [], "note": "命中不足，无法比对"}
    if dry:
        for c in got[:12]:
            print("   %s %s" % (c["id"], (c["claim"] or "")[:56]))
        return {"topic": topic, "n": len(got), "pairs": [], "note": "dry run"}

    from understand import ApiReader
    rd = ApiReader()
    if not rd.available:
        print("API 不可用 —— 找矛盾需要判断，离线做不了。")
        return {"topic": topic, "n": len(got), "pairs": [], "note": "no api"}

    body = "\n".join("%s ｜ %s" % (c["id"], (c.get("claim") or "")[:90]) for c in got)
    msgs = [{"role": "system", "content": FIND_SYSTEM},
            {"role": "user", "content": "【主题】%s\n\n【论点】\n%s\n\n请输出 JSON 数组。"
             % (topic, body)}]
    txt = ""
    for attempt in range(3):
        try:
            d, _ = rd._post(msgs)
        except Exception as e:                     # noqa: BLE001
            print("  调用失败：%r" % e)
            break
        ch = (d.get("choices") or [{}])[0]
        txt = ((ch.get("message", {}) or {}).get("content") or "").strip()
        if txt:
            break
        print("  空正文(finish=%s) → 预算翻倍重试" % ch.get("finish_reason"))
        rd.max_tokens = min(rd.max_tokens * 2, 16384)
    pairs = []
    ok = False
    if txt:
        try:
            if txt.startswith("```"):
                txt = txt.strip("`")
                txt = txt[txt.find("["):]
            pairs = json.loads(txt)
            ok = True
        except Exception as e:                     # noqa: BLE001
            print("  解析失败 %s｜尾部=%s" % (repr(e)[:40], txt[-70:]))
    if not ok:
        # ★ 失败不能伪装成"没发现矛盾"。这两件事必须分开。
        print("  ✗ 本次判定**失败**（不是「没矛盾」）—— 这个簇的结论不可用")
        return {"topic": topic, "n": len(got), "pairs": [], "failed": True}
    ids = {c["id"] for c in got}
    keep = []
    for p in pairs if isinstance(pairs, list) else []:
        a, b = p.get("a"), p.get("b")
        if a in ids and b in ids and a != b:
            keep.append({"topic": topic, "a": a, "b": b,
                         "why": str(p.get("why") or "")[:160],
                         "kind": p.get("kind") if p.get("kind") in ("真冲突", "假冲突")
                                 else "真冲突",
                         "found_at": time.strftime("%Y-%m-%d %H:%M:%S")})
    if keep:
        with io.open(CAND, "a", encoding="utf-8") as f:
            for k in keep:
                f.write(json.dumps(k, ensure_ascii=False) + "\n")
    return {"topic": topic, "n": len(got), "pairs": keep}


# 已知的 8 处冲突（规格 §1）——用来校验本工具是不是坏的
KNOWN = [
    ("苦难", ["苦难", "痛苦", "受害", "折磨"], "C7"),
    ("快乐的地位", ["快乐", "幸福", "满足", "愉悦"], "C4"),
    ("想要 vs 意义", ["想要", "欲望", "意义", "渴求"], "C6"),
    ("价值中立", ["评判", "价值", "中立", "应该"], "C2"),
]


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="交集：找互相矛盾的观点")
    ap.add_argument("--topic", default=None)
    ap.add_argument("--keywords", default=None, help="逗号分隔")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="用已知的 8 处冲突校验本工具（**先跑这个**）")
    a = ap.parse_args()
    if a.verify:
        print("=" * 74)
        print("校验：拿已知冲突试 —— 找不出来就说明工具是坏的")
        print("=" * 74)
        for topic, kws, cid in KNOWN:
            r = find(topic, kws, a.limit, dry=a.dry)
            hit = len(r["pairs"])
            print("   → 命中 %d 对%s\n" % (hit, "" if hit else "  ← 应当至少命中 1 对"))
        return 0
    if a.topic and a.keywords:
        r = find(a.topic, a.keywords.split(","), a.limit, dry=a.dry)
        print(json.dumps(r, ensure_ascii=False, indent=1)[:1500])
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

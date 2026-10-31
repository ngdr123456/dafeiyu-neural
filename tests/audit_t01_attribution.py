# -*- coding: utf-8 -*-
"""查证：「他在 T01 这个话题上换过 6 次」是谁造成的？

为什么要专门查这一条
────────────────────────────────────────────────────────────
`/character` 的「注意到但不说」栏里有这一句，而它**会被用来调整行为**
（原话：以上只用于调整我自己，「少往那儿问」）。
如果这 6 次其实是我的话题调度 bug 造成的，那系统就是在
**把程序错误记成用户的回避倾向，并据此默默改变行为，还不告诉他** ——
被错误建模而不被通知，比被冒犯更难发现。

判据怎么来（不能靠我的印象）
────────────────────────────────────────────────────────────
`CHANGED_SUBJECT` 的算法只有一句：前后两轮 `topic_id` 不同。
而话题会变有三种可能：
  ① 用户真的把话题带走了（R1：用户带进来的域优先）
  ② 话题阶梯按既定规则推进（机制的既定行为，不是他的动作）
  ③ 我的 `visited` bug 造成的重复／回退（本轮已修）
所以要把每一次 T01 的离开逐个摊开看是哪一种，而不是数一个总数。

⚠️ 只读。不写任何文件。
"""
from __future__ import annotations

import io
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "engine"), os.path.join(_ROOT, "state")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_LEDGER = os.path.join(_ROOT, "state", "ledger.jsonl")
_TOPICS = os.path.join(_ROOT, "corpus", "topics.json")
ZW = "\ufeff\u200b\u200c\u200d\u2060\ufffd \t\r\n"


def load_rows():
    rows = []
    for line in io.open(_LEDGER, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if d.get("__ERA_BOUNDARY__") or d.get("void"):
            continue
        rows.append(d)
    return rows


def sessions(rows):
    """按 turn_id 归零切分会话（台账里 turn_id 每个会话重新计数）。"""
    out, cur = [], []
    last = 0
    for d in rows:
        t = d.get("turn_id") or 0
        if t <= last and cur:
            out.append(cur)
            cur = []
        cur.append(d)
        last = t
    if cur:
        out.append(cur)
    return out


def main() -> int:
    rows = load_rows()
    sss = sessions(rows)
    print("=" * 78)
    print("查证：T01 的离开是谁造成的")
    print("=" * 78)
    print("有效轮次 %d ｜ 切成 %d 个会话" % (len(rows), len(sss)))

    # 用户原话里出现的"域词"，用来判断他是不是自己把话题带走了
    topics = json.load(io.open(_TOPICS, encoding="utf-8"))["topics"]
    dom = {}
    for t in topics:
        for w in (t.get("_domain_words") or []):
            dom[w] = t["id"]

    print("\n" + "─" * 78)
    print("① 每个会话的话题序列（→ 表示话题在这一轮之后变了）")
    print("─" * 78)
    t01_leaves = []
    for si, s in enumerate(sss, 1):
        seq = []
        for i, d in enumerate(s):
            tp = d.get("topic_id") or "—"
            nxt = s[i + 1] if i + 1 < len(s) else None
            mark = ""
            if nxt is not None:
                nt = nxt.get("topic_id") or "—"
                if nt != tp:
                    mark = "→" + nt
                    if tp == "T01":
                        t01_leaves.append((si, i, d, nxt))
            raw = "".join(ch for ch in (d.get("raw_input") or "") if ch not in ZW)
            seq.append("%s%s[%s:%s]" % (tp, mark, d.get("behavior", "?"), raw[:10]))
        print("  会话%-2d (%d轮): %s" % (si, len(s), "  ".join(seq)))

    print("\n" + "─" * 78)
    print("② T01 的每一次离开，逐个判定归因")
    print("─" * 78)
    if not t01_leaves:
        print("  台账里没有 T01→其他 的转移。")
    by_verdict = {}
    for si, i, d, nxt in t01_leaves:
        cur_raw = "".join(ch for ch in (d.get("raw_input") or "") if ch not in ZW)
        nxt_raw = "".join(ch for ch in (nxt.get("raw_input") or "") if ch not in ZW)
        prev_beh = d.get("behavior", "?")
        # 判据：association.py 的启发式是「话题变了 且 上一轮我不是在问」→ 判成"我换的话题"
        #   若上一轮我在问 → 判成"他换的"
        # 这里再加上一条：他的下一句里有没有出现**另一个域**的词。
        other_dom = sorted({v for w, v in dom.items() if w in nxt_raw and v != "T01"})
        if prev_beh == "ASK_DETAIL":
            why = "上一轮我在问细节 → association 判成『他换的』"
        else:
            why = "上一轮我不是在问 → association 判成『我换的话题』"
        if other_dom:
            why += "；且他的下一句含有 %s 的域词（像是他自己带走的）" % "、".join(other_dom)
        else:
            why += "；他的下一句里**没有任何别的域词**（不像他自己带走的）"
        print("  会话%d 第%d轮  我做的=%-14s 他下一句=「%s」" % (si, i + 1, prev_beh, nxt_raw[:24]))
        print("       %s" % why)
        key = "他换的" if prev_beh == "ASK_DETAIL" else "我换的话题"
        by_verdict[key] = by_verdict.get(key, 0) + 1

    print("\n" + "─" * 78)
    print("③ 交叉核对：noticed_about_user 报的是「他」换的，还是全部？")
    print("─" * 78)
    from association import Association
    a = Association.derive_from_ledger()
    ch = [p for p in a.pairs if p.his == "CHANGED_SUBJECT"]
    from collections import Counter
    print("  CHANGED_SUBJECT 总数: %d" % len(ch))
    print("  按『我之前那个话题』分布:", dict(Counter(p.topic for p in ch)))
    for l in a.noticed_about_user():
        print("  报出 → %s" % l)

    print("\n" + "─" * 78)
    print("④ ★ 会话边界：配对有没有跨会话？")
    print("─" * 78)
    # association.derive_from_ledger 把**相邻两行**配成一对（rows[i] 与 rows[i+1]），
    # 而它**不切会话边界** —— 于是上一个会话的最后一句会和下一个会话的第一句配成一对，
    # 产生一个"反应"：他在两个**互不相干的会话**之间的长度变化与话题变化。
    # 这一节把这个数算出来。
    rows_txt = [d for d in rows if (d.get("raw_input") or "").strip()]
    cross = []
    for i in range(len(rows_txt) - 1):
        a, b = rows_txt[i], rows_txt[i + 1]
        if (b.get("turn_id") or 0) <= (a.get("turn_id") or 0):
            cross.append((a, b))
    print("  有原话的有效轮次: %d" % len(rows_txt))
    print("  名义配对数（相邻两行）: %d" % (len(rows_txt) - 1))
    print("  其中**跨会话**的: %d  ← 这些对是伪造的，两端不属于同一次对话" % len(cross))
    print("  真正同一会话内的: %d" % (len(rows_txt) - 1 - len(cross)))
    if cross:
        print("\n  跨会话配对明细（前 12 条）：")
        for a, b in cross[:12]:
            print("     会话末「%s」(topic=%s)  ×  会话首「%s」(topic=%s)  话题变了=%s"
                  % (("".join(c for c in (a.get("raw_input") or "") if c not in ZW))[:14],
                     a.get("topic_id"),
                     ("".join(c for c in (b.get("raw_input") or "") if c not in ZW))[:14],
                     b.get("topic_id"),
                     a.get("topic_id") != b.get("topic_id")))

    # 量化影响：把跨会话对去掉，重算三个关键统计
    print("\n" + "─" * 78)
    print("⑤ 去掉跨会话对之后，数字变了多少")
    print("─" * 78)
    from association import _reaction_of
    def tally(seq):
        c = Counter()
        for i in range(len(seq) - 1):
            a, b = seq[i], seq[i + 1]
            if (b.get("turn_id") or 0) <= (a.get("turn_id") or 0):
                continue
            c[_reaction_of(a.get("raw_input", ""), b.get("raw_input", ""),
                           a.get("topic_id"), b.get("topic_id"))] += 1
        return c
    c_all = tally(rows_txt)
    print("  同一会话内配对的实际反应分布:", dict(c_all))
    print("  （上面 association 报的 CHANGED_SUBJECT 数包含了跨会话对，所以更大）")

    print("\n" + "─" * 78)
    print("⑥ 归因小计")
    print("─" * 78)
    print("  T01 离开共 %d 次（同一会话内）" % len(t01_leaves))
    for k, v in sorted(by_verdict.items(), key=lambda x: -x[1]):
        print("     %s：%d 次" % (k, v))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

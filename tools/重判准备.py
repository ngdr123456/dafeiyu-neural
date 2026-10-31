# -*- coding: utf-8 -*-
"""重判准备（**只在副本上跑**）：把原结论存进 remap_from，再把状态重置成"待判"。

为什么需要它
────────────────────────────────────────────────────────────
`map_claims.main()` 只挑 `status == "未实现" and not mapped_at` 的条目。
M 的 601 条**全都判过了** —— 不重置的话，一条都不会重判。

用户裁定的四条前置条件（原话）
────────────────────────────────────────────────────────────
  ① 先对三份 jsonl 做命名快照并记哈希        → 由 tools/重判准备.py 之外的手工步骤完成
  ② 清之前把原 status/mapped_at/mapped_by 记进新字段（如 remap_from）
  ③ 做完逐行比对，**已实现 88 条、明确不实现 360 条必须逐字不变**
  ④ 「明确不实现」做定向核查（+ 随机 20 条）

⚠️ **这个脚本拒绝在真实项目上运行。** 它检查 EGO_ROOT 的目录名里必须带
   「副本」二字 —— 宁可误拦，也不许把主数据表重置掉。

⚠️ 本脚本**不碰** `apply_map`：`apply_map` 只写 status/maps_to/why_not/
   mapped_by/mapped_at/map_note，其余字段原样保留 —— 所以 `remap_from` 会活下来。
"""
from __future__ import annotations

import io
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DIR = os.path.join(_ROOT, "spec", "观点总表")


def guard() -> None:
    """★ 硬闸：只许在副本上跑。"""
    name = os.path.basename(os.path.abspath(_ROOT))
    if "副本" not in name:
        raise SystemExit(
            "★ 拒绝运行：EGO_ROOT 指向 %s\n"
            "  这个脚本会**重置主数据表的状态**，只允许在名字带「副本」的目录上跑。\n"
            "  正确用法：先设 EGO_ROOT 到重判工作副本，再运行。" % _ROOT)


def prep(book: str) -> dict:
    p = os.path.join(DIR, "%s.jsonl" % book)
    rows = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
    stat = {"总": len(rows), "已判": 0, "重置": 0, "跳过": 0}
    from collections import Counter
    before = Counter()
    for c in rows:
        st = c.get("status")
        before[st] += 1
        if not c.get("mapped_at"):
            stat["跳过"] += 1
            continue
        stat["已判"] += 1
        # ② 原结论存进 remap_from（**只在第一次**存，重复跑不覆盖）
        if "remap_from" not in c:
            c["remap_from"] = {
                "status": c.get("status"),
                "maps_to": c.get("maps_to"),
                "why_not": c.get("why_not"),
                "mapped_by": c.get("mapped_by"),
                "mapped_at": c.get("mapped_at"),
            }
            c["remap_batch"] = time.strftime("%Y-%m-%d %H:%M:%S")
        # 重置成"待判" —— 两条件都要满足，main() 才会挑中它
        c["status"] = "未实现"
        c.pop("mapped_at", None)
        c.pop("maps_to", None)
        c.pop("why_not", None)
        c.pop("map_note", None)
        stat["重置"] += 1
    io.open(p, "w", encoding="utf-8").write(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in rows))
    stat["原状态分布"] = dict(before)
    return stat


def main() -> int:
    guard()
    books = sys.argv[1:] or ["M"]
    print("=" * 74)
    print("重判准备｜EGO_ROOT = %s" % _ROOT)
    print("=" * 74)
    for b in books:
        s = prep(b)
        print("  %-3s 总 %4d｜已判 %4d｜**重置 %4d**｜本来就是待判 %d"
              % (b, s["总"], s["已判"], s["重置"], s["跳过"]))
        print("      原状态：%s" % s["原状态分布"])
    print()
    print("  下一步：python engine/map_claims.py --book %s --batch 8" % books[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

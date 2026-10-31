# -*- coding: utf-8 -*-
"""重判对账：按用户裁定的**采纳规则**合并新结果，并把被拒的翻盘记进侧日志。

用户最终裁定的采纳规则（原话，2026-10-02）
────────────────────────────────────────────────────────────
> 「新规则：**任何原状态的条目，只有新结果是『已实现』且 maps_to 命中 7 个新增单元
>   之一时才覆盖旧结论，其余一律保留旧结论，新结果进侧日志。**」

所以只有一种情况会覆盖旧结论：

    新 status == 已实现  AND  set(新 maps_to) ∩ NEW_UNITS ≠ ∅

**别的全都不覆盖**。从未判过的条目（没有 `remap_from`）没有旧结论可保护，
新结果就是首次判定，照常采纳。

第二轮修订（用户逐条点名，2026-10-02）
────────────────────────────────────────────────────────────
> 「还原必须逐字。旧 why_not 为空时要把新写的 why_not 删掉……
>   侧日志不得截断（现在是 [:120]），新旧 why_not、maps_to 全文保存。
>   防呆：不设 EGO_ROOT 时默认指向真实项目。--apply 前必须校验 EGO_ROOT 已设置、
>   在 backups\\重判工作副本_* 之下、且不等于真实根，并打印目标绝对路径，不满足就拒绝。
>   写文件改原子写（临时文件 + os.replace），写前写后核对条数和 id 集合不变。
>   幂等：已带 remap_rejected 的条目跳过，不得重复写侧日志。
>   采纳时合并 maps_to：旧状态为已实现的条目，采纳后 maps_to 取旧∪新，不得丢旧单元。」

用法
    EGO_ROOT=<副本> python tools/重判对账.py --book M            # 只报告
    EGO_ROOT=<副本> python tools/重判对账.py --book M --apply    # 落盘（带全部防呆）
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)

# ★ 真实项目根 —— `--apply` 时**绝不允许**指向它
REAL_ROOT = r"C:\Users\22082\Desktop\DEPSK\books\ego-dialogue"
WORK_PREFIX = "重判工作副本_"

# ★ 新增的 7 个单元 —— 只有新结果命中其中之一，才允许覆盖旧结论
NEW_UNITS = {
    "dev:PERCEPTION_GATE", "dev:SELF_RULES", "dev:ATTITUDE_EXEMPT",
    "dev:TENSION_GROWTH", "const:TENSION_DRIVE",
    "dev:PATH_EXPERIENTIAL", "dev:PATH_ATTITUDINAL",
}
# `dev:PATH_CREATIVE` **不在名单里** —— 用户裁定不收它

# 还原时要逐字处理的键（`remap_from` 里存的就是这几个）
_RESTORE_KEYS = ("status", "maps_to", "why_not", "mapped_by", "mapped_at")


def guard_apply(root: str) -> str:
    """★ --apply 前的防呆。返回通过校验的目标绝对路径，不满足就退出。

    用户原话：「不设 EGO_ROOT 时默认指向真实项目。--apply 前必须校验 EGO_ROOT 已设置、
    在 backups\\重判工作副本_* 之下、且不等于真实根，并打印目标绝对路径，不满足就拒绝。」
    """
    raw = os.environ.get("EGO_ROOT")
    if not raw:
        raise SystemExit(
            "★ 拒绝 --apply：**EGO_ROOT 没有设置**。\n"
            "  不设它时脚本会默认指向真实项目（%s）—— 那是主数据表，不许动。\n"
            "  正确用法：先 $env:EGO_ROOT = '<重判工作副本>'" % REAL_ROOT)
    absroot = os.path.abspath(raw)
    if os.path.normcase(absroot) == os.path.normcase(os.path.abspath(REAL_ROOT)):
        raise SystemExit("★ 拒绝 --apply：EGO_ROOT 指向**真实项目根**：%s" % absroot)
    parent = os.path.basename(os.path.dirname(absroot))
    leaf = os.path.basename(absroot)
    if not (leaf.startswith(WORK_PREFIX) and parent.lower() == "backups"):
        raise SystemExit(
            "★ 拒绝 --apply：EGO_ROOT 不在 backups\\%s* 之下。\n"
            "  实际指向：%s" % (WORK_PREFIX, absroot))
    print("  【防呆通过】目标绝对路径：%s" % absroot)
    return absroot


def restore_verbatim(c: dict, rf: dict) -> None:
    """★ 逐字还原（用户点名）。

    ⚠️ 第一版写的是「`if rf.get("why_not"):` 才还原」——
       于是**旧 why_not 为空**的那些（正是那 45 条）会把新写的理由留在身上，
       变成「未实现却带着明确不实现的理由」，自相矛盾。
       现在：存的是 **None** 就说明**原来没有这个键** → **删掉它**。
    """
    for k in _RESTORE_KEYS:
        v = rf.get(k)
        if v is None:
            c.pop(k, None)          # 原来没有 → 删掉（不是设成空串）
        else:
            c[k] = v


def load(book: str, root: str) -> list:
    p = os.path.join(root, "spec", "观点总表", "%s.jsonl" % book)
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]


def atomic_write_jsonl(path: str, rows: list) -> None:
    """★ 原子写：临时文件 + os.replace（用户点名）。"""
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for c in rows:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser(description="重判对账")
    ap.add_argument("--book", required=True)
    ap.add_argument("--apply", action="store_true", help="真正落盘")
    ap.add_argument("--seed", type=int, default=20261002,
                    help="随机抽样的种子（固定种子，结果可复现）")
    a = ap.parse_args()

    root = guard_apply(DEFAULT_ROOT) if a.apply else DEFAULT_ROOT
    rows = load(a.book, root)
    from collections import Counter

    pending = first_time = skipped = 0
    adopted, protected = [], []
    matrix = Counter()
    why_but_no_map = []
    rej_ids = {c["id"] for c in rows if c.get("remap_rejected")}

    for c in rows:
        rf = c.get("remap_from")
        if not rf:
            if c.get("mapped_at"):
                first_time += 1
                adopted.append({"id": c["id"], "旧": None, "新": c.get("status"),
                                "maps_to": c.get("maps_to") or []})
            continue
        if c.get("id") in rej_ids:
            skipped += 1                    # ★ 幂等：已处理过的跳过
            continue
        if not c.get("mapped_at"):
            pending += 1
            continue

        old, new = rf.get("status"), c.get("status")
        new_mt = c.get("maps_to") or []
        matrix["%s → %s" % (old, new)] += 1

        wy = c.get("why_not") or ""
        if not new_mt and any(u in wy for u in NEW_UNITS):
            why_but_no_map.append({
                "id": c["id"], "旧": old, "新": new,
                "旧_why_not": rf.get("why_not") or "",
                "新_why_not": wy,
                "命中": sorted(u for u in NEW_UNITS if u in wy)})

        adopt = (new == "已实现" and (set(new_mt) & NEW_UNITS))
        if adopt:
            # ★ 采纳时合并 maps_to（用户点名）：旧状态为已实现的，取旧 ∪ 新，不丢旧单元
            merged = list(new_mt)
            if old == "已实现":
                for u in (rf.get("maps_to") or []):
                    if u not in merged:
                        merged.append(u)
            adopted.append({"id": c["id"], "旧": old, "新": new,
                            "maps_to": merged, "原新maps_to": new_mt})
            c["maps_to"] = merged
        else:
            protected.append({"id": c["id"], "旧": old, "新": new,
                              "旧_maps_to": rf.get("maps_to"),
                              "新_maps_to": new_mt,
                              "旧_why_not": rf.get("why_not") or "",
                              "新_why_not": wy})

    print("=" * 82)
    print("重判对账｜%s｜共 %d 条｜根：%s" % (a.book, len(rows), root))
    print("  本轮已判 %d｜尚未判到 %d｜从未判过 %d｜**已处理过（跳过）%d**"
          % (sum(1 for c in rows if c.get("mapped_at")), pending,
             first_time, skipped))
    print("=" * 82)
    print()
    print("【★ 新旧状态完整对照矩阵】（用户点名要，取代作废的噪声率）")
    tot = sum(matrix.values()) or 1
    for k, v in sorted(matrix.items(), key=lambda t: -t[1]):
        print("   %-30s %4d   %5.1f%%" % (k, v, 100.0 * v / tot))
    flip = sum(v for k, v in matrix.items()
               if {k.split(" → ")[0], k.split(" → ")[1]} == {"未实现", "明确不实现"})
    print("   ────────────────────────────────────────────")
    print("   **「未实现 ↔ 明确不实现」互翻合计：%d 条（%.0f%%）**" % (flip, 100.0*flip/tot))
    print()
    print("【采纳】%d 条" % len(adopted))
    for x in adopted:
        tag = ""
        if x["旧"] == "已实现" and set(x["maps_to"]) != set(x.get("原新maps_to") or []):
            tag = "（maps_to 已合并旧单元）"
        print("   %-8s %s → %s｜%s%s" % (x["id"], x["旧"], x["新"], x["maps_to"], tag))
    print()
    print("【保护旧结论】%d 条 → 记入侧日志（全文，不截断）" % len(protected))
    print()
    print("【why_not 里点了新单元的名、却没填 maps_to】%d 条" % len(why_but_no_map))
    for x in why_but_no_map:
        print("   %-8s %s → %s｜命中 %s" % (x["id"], x["旧"], x["新"], x["命中"]))
        print("      旧 why_not（全文）：%s" % (x["旧_why_not"] or "（空）"))
        print("      新 why_not（全文）：%s" % (x["新_why_not"] or "（空）"))

    # ── 随机抽样（固定种子，可复现；**不用前 10 条**——那是连续的集中营史实，样本有偏）
    print()
    print("=" * 82)
    print("【随机抽样】seed=%d（可复现）" % a.seed)
    print("=" * 82)
    rnd = random.Random(a.seed)
    for label, pair in (("未实现 → 明确不实现", ("未实现", "明确不实现")),
                        ("明确不实现 → 未实现", ("明确不实现", "未实现"))):
        pool = [x for x in protected if (x["旧"], x["新"]) == pair]
        print()
        print("── %s：池子 %d 条，随机抽 %d 条 ──" % (label, len(pool), min(10, len(pool))))
        for x in rnd.sample(pool, min(10, len(pool))):
            print("   %s" % x["id"])
            print("      旧 why_not：%s" % (x["旧_why_not"] or "（空）"))
            print("      新 why_not：%s" % (x["新_why_not"] or "（空）"))
            print("      旧 maps_to=%s｜新 maps_to=%s" % (x["旧_maps_to"], x["新_maps_to"]))

    if a.apply:
        noise = os.path.join(root, "state", "remap_noise.jsonl")
        os.makedirs(os.path.dirname(noise), exist_ok=True)
        # ★ 侧日志：**按 id 去重 + 原子重写**（用户要求幂等；第一版有洞）
        #
        # ⚠️ 第一版是 `io.open(noise, "a")` **追加**，而且写在"标记行"之前。
        #    进程若死在这两步之间 → 行没被标记 → 重跑**又追加一遍**。
        #    实测撞到过：我自己用 `Select-Object -First N` 截断输出，
        #    那会提前关管道、杀掉进程，于是侧日志变成了 1188 条（594 条重复两遍）。
        #    现在：先读回已有条目 → 按 id 合并去重 → 整份原子重写。
        #    **崩在哪一步都不影响：重跑只会合并，不会重复。**
        old_noise: dict = {}
        if os.path.exists(noise):
            for l in io.open(noise, encoding="utf-8"):
                if l.strip():
                    e = json.loads(l)
                    old_noise[e["id"]] = e
        for x in protected:
            x["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
            x["book"] = a.book
            old_noise[x["id"]] = x            # 同 id 以本次为准
        atomic_write_jsonl(noise, list(old_noise.values()))

        for c in rows:
            if c["id"] in {x["id"] for x in protected}:
                restore_verbatim(c, c["remap_from"])     # ★ 逐字还原
                c["remap_rejected"] = True               # ★ 幂等标记
        p = os.path.join(root, "spec", "观点总表", "%s.jsonl" % a.book)
        before_ids = [c["id"] for c in rows]
        before_n = len(rows)
        atomic_write_jsonl(p, rows)
        after = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
        assert len(after) == before_n, \
            "★ 写后条数变了：%d → %d" % (before_n, len(after))
        assert [c["id"] for c in after] == before_ids, "★ 写后 id 集合/顺序变了"
        print()
        print("  已落盘（原子写）：%s" % p)
        print("  条数 %d 未变｜id 集合与顺序未变 ✓" % len(after))
        print("  侧日志：%s（**去重后 %d 条**，全文）" % (noise, len(old_noise)))
    else:
        print()
        print("  （未加 --apply，**只报告没落盘**）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

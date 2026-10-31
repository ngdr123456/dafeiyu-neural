# -*- coding: utf-8 -*-
"""把重判结果从工作副本写回**真实项目**。

默认 **dry-run**（只打印将要改什么，不落盘）。真写要显式 `--apply`。

用户裁定的写回方案（原话，2026-10-02）
────────────────────────────────────────────────────────────
> ① 写回前核对真实表哈希等于快照哈希，不一致就停。
> ② 按 id 合并映射字段，**不整表覆盖**。
> ③ 全项目搜所有读取 spec\\观点总表 的代码，确认对新增键不敏感。
> ④ remap_from 保留作审计。
> ⑤ 写回后回读比对。

第二轮修订（用户逐条点名，2026-10-02）
────────────────────────────────────────────────────────────
> 「① 回读比对加**快照基准**。现在 ⑧ 只拿写完的真实表和副本比，
>    副本是还原出来的，**这是循环验证**。
>    加：(a) 1261 条被还原的行，status/maps_to/why_not/mapped_at/mapped_by/map_note
>        与快照里对应行逐字一致；(b) **所有行**的非映射字段与快照逐字一致；
>        (c) 采纳和首次判定的行，写回字段与副本一致。
>  ② **三本原子性**：先把三本都写成临时文件并各自校验（条数、id 顺序、字段），
>    全部通过再统一 os.replace。**任何一本不过，一本都不替换**，并打印恢复办法。
>  ③ 侧日志同样先写临时文件再替换，写后核对条数 1261 且 **id 无重复**。
>  ④ dry-run 第④项"采纳"的口径写错了……改成
>    「有 remap_from 且 remap_rejected 不为 True」。
>  ⑤ **备份后校验**：备份文件哈希必须等于快照哈希，不等就停。」

③ 的核查结论（写在这里便于日后复查）
────────────────────────────────────────────────────────────
· **键集合**：全项目没有"只许有这些键"的断言。唯一的字段检查是
  `claims.py:89` 的 `REQUIRED`，用在 `check_schema()` 里，判据是
  **`if k not in c`（必须有）**，不是白名单。
· **值分支**：按 `status`/`maps_to`/`mapped_at` 的值做分支的只有
  `claims.check_schema` / `claims.closure` / `claims.merge_parts`
  —— 三者**都只在 `claims.main()`（CLI 体检）里调用**（行 333/323/311）。
  训练路径只用 `claims.load()`，只做 `json.loads`，**零值分支**。
· **整行序列化**：`claims.py` 与 `map_claims.py` 的 `json.dumps(c)` 全部是
  **写文件**，没有一处把整行 dict 塞进提示词或界面。
  `admin_agent.claims()` 只被 `len(...)` 用来报条数。
· **可达性**：`conflicts.py` / `find_conflicts.py` 从训练路径**不可达**。
· ⚠️ 更正：`training_studio.py:785` 读的是 **charter**（总纲领），不是观点总表。

侧日志位置：`spec\\重判侧日志.jsonl`。`claims.py:249` 只 glob
`spec\\观点总表\\<book>_part*.jsonl`、`syntax_gate` 只 glob `*.py` —— 都扫不到它。

⚠️ 关于"原子性"的诚实说明：Windows 上**没有**跨文件的真事务。
   本脚本做到的是**"全部校验通过之后才开始替换"** ——
   三本各自写临时文件 + 逐本校验，**任何一本不过就一本都不替换**。
   替换阶段三次 `os.replace` 之间仍有极小窗口（毫秒级），
   真要绝对安全只能靠备份回滚 —— 所以备份是前置的、且校验哈希。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_ROOT = os.environ.get("EGO_ROOT") or ""

REAL_ROOT = r"C:\Users\22082\Desktop\DEPSK\books\ego-dialogue"
WORK_PREFIX = "重判工作副本_"
SNAP_PREFIX = "重判前快照_"
BACKUP_ROOT = r"C:\Users\22082\Desktop\DEPSK\backups"
BOOKS = ("M", "DB", "E")
SIDE_LOG_NAME = "重判侧日志.jsonl"

# ★ 只覆盖这些字段。**其余字段一个字节不动。**
WRITE_FIELDS = ("status", "maps_to", "why_not", "mapped_by", "mapped_at",
                "raw_status", "downgraded", "remap_from", "remap_rejected",
                # `remap_batch` 是准备脚本写下的审计时间戳，与 `remap_from` 同族。
                # 第一版漏了它 —— dry-run 立刻报成"非映射字段改了 601 处"。
                "remap_batch")
# 只在"没被还原"（采纳或首次判定）时才写：
#   `map_note` 不写被还原的条目 —— 准备脚本 pop 掉了旧 note、apply_map 又写进了
#   新 note；对被拒的条目，新 note 对应的是**被拒的结论**，不该落盘。
COND_FIELDS = ("map_note",)

# ①(a)：被还原的 1261 条要与**快照**逐字比这 6 个字段
RESTORED_CHECK = ("status", "maps_to", "why_not", "mapped_at", "mapped_by", "map_note")


def guard(apply: bool) -> tuple:
    """双向防呆：源必须是工作副本，目标必须是真实根。"""
    if not SOURCE_ROOT:
        raise SystemExit("★ EGO_ROOT 没设置 —— 本脚本的**源**是重判工作副本。")
    src = os.path.abspath(SOURCE_ROOT)
    dst = os.path.abspath(REAL_ROOT)
    leaf, parent = os.path.basename(src), os.path.basename(os.path.dirname(src))
    if not (leaf.startswith(WORK_PREFIX) and parent.lower() == "backups"):
        raise SystemExit("★ 源不在 backups\\%s* 之下：%s" % (WORK_PREFIX, src))
    if os.path.normcase(src) == os.path.normcase(dst):
        raise SystemExit("★ 源与目标相同 —— 拒绝。")
    if not os.path.isdir(dst):
        raise SystemExit("★ 真实项目根不存在：%s" % dst)
    print("  【防呆通过】源（工作副本）：%s" % src)
    print("  【防呆通过】目标（真实项目）：%s" % dst)
    return src, dst


def load_rows(p: str) -> list:
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]


def dump_rows(path: str, rows: list) -> None:
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        for c in rows:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def sha(p: str) -> str:
    return hashlib.sha256(io.open(p, "rb").read()).hexdigest()


def merge_one(c: dict, w: dict) -> dict:
    """按 id 合并：只覆盖 WRITE_FIELDS，map_note 只在未被还原时写。"""
    c2 = dict(c)
    for k in WRITE_FIELDS:
        if k in w:
            c2[k] = w[k]
        else:
            c2.pop(k, None)
    if not w.get("remap_rejected"):
        if "map_note" in w:
            c2["map_note"] = w["map_note"]
        else:
            c2.pop("map_note", None)
    return c2


def main() -> int:
    ap = argparse.ArgumentParser(description="把重判结果写回真实项目")
    ap.add_argument("--apply", action="store_true", help="真写（默认 dry-run）")
    a = ap.parse_args()
    src, dst = guard(a.apply)

    snap_dir = None
    for d in sorted(os.listdir(BACKUP_ROOT)):
        if d.startswith(SNAP_PREFIX):
            snap_dir = os.path.join(BACKUP_ROOT, d)
    if not snap_dir:
        raise SystemExit("★ 找不到重判前快照目录（backups\\%s*）" % SNAP_PREFIX)

    print()
    print("=" * 84)
    print("写回真实项目｜%s" % ("**真写**" if a.apply else "**dry-run（不落盘）**"))
    print("  快照基准：%s" % snap_dir)
    print("=" * 84)

    # ── ① 哈希闸
    print()
    print("① 哈希闸：真实表当前哈希 必须等于 快照哈希")
    for b in BOOKS:
        rp = os.path.join(dst, "spec", "观点总表", "%s.jsonl" % b)
        sp = os.path.join(snap_dir, "观点总表", "%s.jsonl" % b)
        hr, hs = sha(rp), sha(sp)
        print("   %-3s %s…｜快照 %s…｜%s" % (b, hr[:20], hs[:20],
                                          "✓" if hr == hs else "★ **不一致，立即停止**"))
        if hr != hs:
            print()
            print("   ★ 真实表在重判期间被改动过 —— 写回会覆盖那次改动。停止。")
            return 4
    print("   ✓ 三本全部一致，可以继续")

    # ── 载入三份数据：真实、副本、快照
    P = {}
    for b in BOOKS:
        rp = os.path.join(dst, "spec", "观点总表", "%s.jsonl" % b)
        wp = os.path.join(src, "spec", "观点总表", "%s.jsonl" % b)
        sp = os.path.join(snap_dir, "观点总表", "%s.jsonl" % b)
        real, work, snap = load_rows(rp), load_rows(wp), load_rows(sp)
        ri = [c["id"] for c in real]
        wi = [c["id"] for c in work]
        si = [c["id"] for c in snap]
        if not (ri == wi == si):
            print("   ★ %s 的 id 集合/顺序在 真实/副本/快照 之间不一致 —— 停止" % b)
            return 5
        P[b] = {"rp": rp, "real": real, "work": work, "snap": snap,
                "wmap": {c["id"]: c for c in work}, "smap": {c["id"]: c for c in snap}}

    print()
    print("② 按 id 合并（只覆盖 %d 个字段，其余不动）" % len(WRITE_FIELDS))
    for b in BOOKS:
        print("   %-3s %4d 条｜真实/副本/快照 三方 id 集合与顺序一致 ✓"
              % (b, len(P[b]["real"])))

    print()
    print("③ 每个字段将改动的条数")
    for b in BOOKS:
        d = P[b]
        print()
        print("   【%s】" % b)
        for k in list(WRITE_FIELDS) + list(COND_FIELDS):
            ch = 0
            for c in d["real"]:
                w = d["wmap"][c["id"]]
                if k in COND_FIELDS and w.get("remap_rejected"):
                    continue
                if c.get(k) != w.get(k):
                    ch += 1
            print("      %-16s 改动 %4d 条" % (k, ch))
        others = set()
        for c in d["real"]:
            others |= set(c.keys())
        for c in d["work"]:
            others |= set(c.keys())
        skip = set(WRITE_FIELDS) | set(COND_FIELDS)
        bad = [(k, sum(1 for c in d["real"] if c.get(k) != d["wmap"][c["id"]].get(k)))
               for k in sorted(others - skip)
               if any(c.get(k) != d["wmap"][c["id"]].get(k) for c in d["real"])]
        print("      非映射字段（应全为 0）：%s" % (bad or "✓ 全部 0"))

    # ── ④ 三类分布（口径按用户更正：有 remap_from 且 remap_rejected 不为 True = 采纳）
    print()
    print("④ 三类条目的分布（口径：有 remap_from 且 remap_rejected 不为 True = 采纳）")
    for b in BOOKS:
        work = P[b]["work"]
        acc = [c for c in work if c.get("remap_from") and c.get("remap_rejected") is not True]
        rej = [c for c in work if c.get("remap_rejected") is True]
        first = [c for c in work if not c.get("remap_from")]
        print("   %-3s 采纳 %3d｜被还原 %4d｜首次判定 %4d"
              % (b, len(acc), len(rej), len(first)))

    # ── ⑤ 侧日志
    sl_src = os.path.join(src, "state", "remap_noise.jsonl")
    sl_dst = os.path.join(dst, "spec", SIDE_LOG_NAME)
    side = load_rows(sl_src) if os.path.exists(sl_src) else []
    side_ids = [x["id"] for x in side]
    print()
    print("⑤ 侧日志：%s → %s" % (sl_src, sl_dst))
    print("   条数 %d｜不同 id %d｜重复 %d"
          % (len(side), len(set(side_ids)), len(side_ids) - len(set(side_ids))))

    if not a.apply:
        print()
        print("=" * 84)
        print("  dry-run 结束 —— **一个字节都没写**。加 --apply 才真写。")
        print("=" * 84)
        return 0

    # ══════════════════════════════════════════════════════════
    # 真写
    # ══════════════════════════════════════════════════════════
    print()
    print("⑥ 备份真实表（三本）+ 备份后校验哈希 == 快照")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    bk = os.path.join(BACKUP_ROOT, "写回前_%s" % stamp)
    os.makedirs(os.path.join(bk, "观点总表"), exist_ok=True)
    for b in BOOKS:
        dstf = os.path.join(bk, "观点总表", "%s.jsonl" % b)
        shutil.copy2(os.path.join(dst, "spec", "观点总表", "%s.jsonl" % b), dstf)
        hb = sha(dstf)
        hs = sha(os.path.join(snap_dir, "观点总表", "%s.jsonl" % b))
        print("   %-3s 备份 %s…｜快照 %s…｜%s"
              % (b, hb[:20], hs[:20], "✓" if hb == hs else "★ **不等，停止**"))
        if hb != hs:
            print()
            print("   ★ 备份与快照不一致 —— 备份不可信，停止。已有备份：%s" % bk)
            return 6
    if os.path.exists(sl_src):
        shutil.copy2(sl_src, os.path.join(bk, SIDE_LOG_NAME))
    print("   备份目录：%s（三本表 + 侧日志，已校验）" % bk)

    # ── ⑦ 写全部临时文件并逐本校验（一本不过 → 一本都不替换）
    print()
    print("⑦ 写临时文件并逐本校验（全部通过才统一替换）")
    tmps = {}
    ok_all = True
    for b in BOOKS:
        d = P[b]
        merged = [merge_one(c, d["wmap"][c["id"]]) for c in d["real"]]
        tp = d["rp"] + ".tmp"
        dump_rows(tp, merged)
        back = load_rows(tp)
        errs = []
        if len(back) != len(d["real"]):
            errs.append("条数 %d≠%d" % (len(back), len(d["real"])))
        if [c["id"] for c in back] != [c["id"] for c in d["real"]]:
            errs.append("id 顺序变了")
        for c in back:
            w = d["wmap"][c["id"]]
            if any(c.get(k) != w.get(k) for k in WRITE_FIELDS):
                errs.append("%s 字段不符" % c["id"])
                break
        print("   %-3s 临时文件校验：%s"
              % (b, "✓ 通过" if not errs else "★ " + "；".join(errs[:3])))
        if errs:
            ok_all = False
        tmps[b] = tp
    if not ok_all:
        for tp in tmps.values():
            if os.path.exists(tp):
                os.remove(tp)
        print()
        print("   ★ 有临时文件未通过校验 —— **一本都不替换**。临时文件已删除。")
        print("     真实表**未被触碰**。恢复办法：无需恢复；备份在 %s" % bk)
        return 7

    print()
    print("   全部通过 → 统一替换")
    for b in BOOKS:
        os.replace(tmps[b], P[b]["rp"])
        print("   %-3s 已替换" % b)

    # 侧日志：临时文件 + 校验 + 替换
    if side:
        sl_tmp = sl_dst + ".tmp"
        dump_rows(sl_tmp, side)
        back = load_rows(sl_tmp)
        bids = [x["id"] for x in back]
        dup = len(bids) - len(set(bids))
        if len(back) != 1261 or dup:
            os.remove(sl_tmp)
            print("   ★ 侧日志校验不过（条数 %d，重复 %d）—— 未替换。"
                  % (len(back), dup))
            print("     恢复办法：从 %s 取三本表覆盖回去。" % bk)
            return 8
        os.replace(sl_tmp, sl_dst)
        print("   侧日志已写：%s（%d 条，id 无重复 ✓）" % (sl_dst, len(back)))

    # ── ⑧ 回读比对（加快照基准）
    print()
    print("⑧ 回读比对")
    allbad = 0
    for b in BOOKS:
        d = P[b]
        after = load_rows(d["rp"])
        amap = {c["id"]: c for c in after}
        e1 = e2 = e3 = 0
        # (a) 被还原的条目：6 个字段与**快照**逐字一致
        for c in d["work"]:
            if c.get("remap_rejected") is not True:
                continue
            got, sn = amap[c["id"]], d["smap"][c["id"]]
            for k in RESTORED_CHECK:
                if got.get(k) != sn.get(k):
                    e1 += 1
                    if e1 <= 3:
                        print("      ★ %s.%s：实际=%r｜快照=%r"
                              % (c["id"], k, got.get(k), sn.get(k)))
                    break
        # (b) 所有行的**非映射字段**与快照逐字一致
        for c in d["snap"]:
            got = amap[c["id"]]
            for k in c:
                if k in WRITE_FIELDS or k in COND_FIELDS:
                    continue
                if got.get(k) != c.get(k):
                    e2 += 1
                    break
        # (c) 采纳与首次判定的行：写回字段与**副本**一致
        for c in d["work"]:
            if c.get("remap_rejected") is True:
                continue
            got = amap[c["id"]]
            if any(got.get(k) != c.get(k) for k in WRITE_FIELDS) \
               or got.get("map_note") != c.get("map_note"):
                e3 += 1
        print("   %-3s (a)被还原 vs 快照 %d 处不符｜(b)非映射字段 vs 快照 %d 处不符"
              "｜(c)采纳+首次 vs 副本 %d 处不符" % (b, e1, e2, e3))
        allbad += e1 + e2 + e3

    print()
    print("=" * 84)
    if allbad:
        print("  ★ 回读比对有 %d 处不符 —— 从 %s 恢复。" % (allbad, bk))
        return 9
    print("  ✓ 回读比对全部通过")
    for b in BOOKS:
        print("   %-3s 新哈希：%s" % (b, sha(P[b]["rp"])))
    print("  备份目录：%s" % bk)
    print("=" * 84)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""观点总表：把三本书的**每个观点**变成可核对、可检查的条目。

为什么需要它（用户原话）
────────────────────────────────────────────────────────────
> 「至于怎么验证书籍的每个观点，这需要你自己整理并做并集交集整理，
>   形成逻辑闭环。最后再喂回系统里。」

所以这张表要同时承担四件事：
  ① **并集**：书里每个观点都有归宿 —— 要么被系统实现，要么写明为什么不实现。
     **不许有"没提到"**。
  ② **交集**：观点之间不互相矛盾；矛盾必须进裁决表，不许沉默。
  ③ **闭环**：从观点 → 规则 → 行为 → 输出，每一步都能反查。
  ④ **喂回**：未覆盖的观点直接变成待补的原子/规则。

一条观点的字段（少一个都不行）
    id          唯一编号，前缀标书（DB/M/E）
    book        哪本书
    locator     定位：章节名，或 [pNNN]
    quote       **逐字**原句（≤120 字）—— 它是证据，必须能在全文里精确命中
    claim       一句话主张（我的概括）
    kind        事实／机制／规范／临床／方法
    operational 能不能被代码判：是／否／部分
    maps_to     系统里对应什么（原子／标记／机制量／行为／开关）
    status      已实现／未实现／明确不实现／冲突待裁
    why_not     status=明确不实现 时必填理由（否则就是"漏了"伪装成"不做"）

纪律
    · `quote` 必须逐字。`verify_quotes()` 会去全文里查；查不到的就是编的。
    · `status=未实现` 是**合法且重要的结果** —— 它就是我们下一步要补的清单。
    · 不许为了让并集好看而把"没实现"写成"明确不实现"。
"""
from __future__ import annotations

import io
import glob
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
DIR = os.path.join(_ROOT, "spec", "观点总表")
BOOKS = {
    "DB": os.path.join(os.path.dirname(_ROOT), "01_贪婪的多巴胺_全文清洗版.txt"),
    "M": os.path.join(os.path.dirname(_ROOT), "02_活出生命的意义_全文.txt"),
    "E": os.path.join(os.path.dirname(_ROOT), "03_自我的发展_全文.txt"),
}
BOOK_NAME = {"DB": "贪婪的多巴胺", "M": "活出生命的意义", "E": "自我的发展"}
KINDS = (
    "事实",       # 作者陈述的客观情况
    "机制",       # 心理／生理如何运作
    "规范",       # 应该／价值判断（一般性的）
    "临床",       # 治疗与干预的做法
    "方法",       # 研究方法或分类框架
    # --- 以下三类是抽第一分片时**装不下**才补的，每类都有书的依据（E5 补） ---
    "伦理",       # 作者自己的立场抉择（如"我必须署名"）。与"规范"不同：
                  #   规范说的是"人应该怎样"，伦理说的是"作者自己怎么选"。
    "生存策略",    # 具体的生存技术与本土范畴（囚徒亚文化里的做法与标签：
                  #   刮脸挺直腰板、Moslem 这一称呼）。既不是机制也不是临床。
    "精神性",      # ★ [M] 弗兰克尔自己的三层区分：肉体痛苦／心理痛苦／**精神性痛苦**
                  #   （noogenic，源于意义受挫）。"最痛的不是肉体而是不公正"属这一层。
                  #   这不是我为了分类方便造的 —— 是书里本来就有的划分。
)
STATUS = ("已实现", "未实现", "明确不实现", "冲突待裁")

# `operational` 的**精确定义**（补：第一版我没给定义，抽取的分片只能猜，
# 结果同一批数据里三种口径混着填 —— 是任务书的疏漏，不是执行者的错）。
#
#   问：**这条观点能不能变成代码里可判定的东西？**
#
#   是   = 能直接编码成规则／判据／数值。
#          例：「张力趋零是病态」→ 可变成 tension_low 这个阈值。
#   部分 = 只能部分实现：能做成枚举或提示，但观点本身不可判。
#          例：「人有三种意义来源（创造／体验／态度）」→ 能列成三项，
#                但"某个人的意义来自哪一种"代码判不了。
#   否   = 是作者的价值立场、叙事或历史事实，代码无法也不该实现。
#          例：「我必须鼓起勇气署名公开发表」。
#
# ⚠️ `operational=否` **不等于可以不管它**。它仍必须进并集，
#    状态写「明确不实现」并在 `why_not` 里写明理由 ——
#    否则"没实现"就会伪装成"不用做"，而那正是并集最容易漏掉的一块。
OPERATIONAL = ("是", "部分", "否")
REQUIRED = ("id", "book", "locator", "quote", "claim", "kind",
            "operational", "maps_to", "status")


def _ensure() -> None:
    os.makedirs(DIR, exist_ok=True)


def path(book: str) -> str:
    return os.path.join(DIR, "%s.jsonl" % book)


def load(book: str | None = None) -> list[dict]:
    books = [book] if book else list(BOOKS)
    out = []
    for b in books:
        p = path(b)
        if not os.path.exists(p):
            continue
        for line in io.open(p, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:                  # noqa: BLE001
                    pass
    return out


def save(book: str, claims: list[dict]) -> int:
    _ensure()
    seen = {c["id"] for c in load(book)}
    n = 0
    with io.open(path(book), "a", encoding="utf-8") as f:
        for c in claims:
            if c.get("id") in seen:
                continue
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
            seen.add(c.get("id"))
            n += 1
    return n


# ------------------------------------------------------------------ 检查

def _book_text(b: str) -> str:
    p = BOOKS.get(b)
    if not p or not os.path.exists(p):
        return ""
    return io.open(p, encoding="utf-8", errors="ignore").read()


def verify_quotes() -> dict:
    """逐字核对：每条 quote 必须能在原文里精确命中。**这是防编造的唯一手段。**"""
    texts = {b: _book_text(b) for b in BOOKS}
    bad, ok = [], 0
    for c in load():
        b = c.get("book_key") or _guess_book(c)
        q = (c.get("quote") or "").strip()
        if not q:
            bad.append({"id": c.get("id"), "why": "quote 为空"})
            continue
        t = texts.get(b, "")
        # 允许原文里的换行/空格差异：归一化后再比对
        if q in t or re.sub(r"\s+", "", q) in re.sub(r"\s+", "", t):
            ok += 1
        else:
            bad.append({"id": c.get("id"), "why": "原文里找不到这句",
                        "quote": q[:50]})
    return {"ok": ok, "bad": bad}


def _guess_book(c: dict) -> str:
    n = c.get("book") or ""
    for k, v in BOOK_NAME.items():
        if v in n:
            return k
    return (c.get("id") or "?")[0:1] if c.get("id") else "?"


def check_schema() -> dict:
    miss = []
    for c in load():
        for k in REQUIRED:
            if k not in c or c[k] in (None, ""):
                if k == "why_not" and c.get("status") != "明确不实现":
                    continue
                miss.append({"id": c.get("id"), "missing": k})
        if c.get("status") == "明确不实现" and not (c.get("why_not") or "").strip():
            miss.append({"id": c.get("id"), "missing": "why_not（明确不实现必须写理由）"})
        if c.get("kind") not in KINDS:
            miss.append({"id": c.get("id"), "bad_kind": c.get("kind")})
        if c.get("status") not in STATUS:
            miss.append({"id": c.get("id"), "bad_status": c.get("status")})
    return {"problems": miss}


def closure() -> dict:
    """闭环体检：并集完整吗？交集一致吗？"""
    cs = load()
    by_status = {}
    for c in cs:
        by_status[c.get("status", "?")] = by_status.get(c.get("status", "?"), 0) + 1
    orphans = [c for c in cs if c.get("status") == "未实现"]
    conflicts = [c for c in cs if c.get("status") == "冲突待裁"]
    by_book = {}
    for c in cs:
        b = c.get("book") or _guess_book(c)
        by_book[b] = by_book.get(b, 0) + 1
    return {"total": len(cs), "by_status": by_status, "by_book": by_book,
            "未实现（要补的清单）": [{"id": c["id"], "claim": c.get("claim"),
                                     "locator": c.get("locator")} for c in orphans],
            "冲突待裁": [{"id": c["id"], "claim": c.get("claim")} for c in conflicts]}


def tag_rhetoric(book: str, needle: str, tag: str, note: str = "") -> list[str]:
    """按**内容片段**给条目打修辞标记（直述／反问／归谬／转述）。

    ⚠️ 为什么按内容而不是按 id：合并时会统一重编号，
       于是子代理报的 id 与合并后的 id **对不上**。
       按 id 去改会改错条目 —— 那比不改更糟。
       按 quote/claim 的片段定位，改的是"那一条本身"。

    为什么需要这个字段：有些句子**字面方向与作者立场相反**。
    例：「如果病人不再重要，那安乐死理应合法化」是作者的**归谬前提**，
    他反对这个结论。按字面读，系统会把作者反对的观点当成他的主张。
    """
    cs = load(book)
    hit = []
    for c in cs:
        blob = (c.get("quote") or "") + " " + (c.get("claim") or "")
        if needle in blob:
            c["rhetoric"] = tag
            if note:
                c["rhetoric_note"] = note
            hit.append(c["id"])
    if hit:
        with io.open(path(book), "w", encoding="utf-8") as f:
            for c in cs:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return hit


def merge_parts(book: str) -> dict:
    """把 <book>_partN.jsonl 合并成 <book>.jsonl：**按文件顺序重新连续编号**。

    ★ 这里修过一个我自己造出来的错，值得写下来：
      我按固定 100 块给分片分配起始号（part1 从 M-001、part2 从 M-101、
      part3 从 M-201…），却**假设每片不超过 100 条**。part2 实际出了 111 条
      （M-101…M-211），于是与 part3 的 M-201…M-211 撞号。

      而第一版的合并是 `allc[c["id"]] = c` —— **撞号会静默覆盖**：
      part2 的 11 条会无声消失，而且看不出来。
      这正是本项目一路在防的那类丢失（"写了等于没写"的近亲）。

      修法不是重挑一个起始号（part4 还会再撞），而是**取消固定块**：
      合并时按文件名顺序（part1 → part2 → …）重新连续编号。
      同时**撞号必须报错**，不许静默。
    """
    _ensure()
    parts = sorted(glob.glob(os.path.join(DIR, "%s_part*.jsonl" % book)))
    seq: list[dict] = []
    dup: list[str] = []
    seen_ids: set[str] = set()
    for p in parts:
        for line in io.open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                c = json.loads(line)
            except Exception:                      # noqa: BLE001
                continue
            cid = c.get("id")
            if cid in seen_ids:
                dup.append(cid)
            seen_ids.add(cid)
            c["_src_part"] = os.path.basename(p)
            seq.append(c)
    # 重新编号：保住顺序，去掉撞号
    old2new = {}
    for i, c in enumerate(seq, 1):
        old = c.get("id")
        new = "%s-%03d" % (book, i)
        if old != new:
            c["_id_was"] = old
        old2new[old] = new
        c["id"] = new
    # ★ 保留已有的映射结果（按 quote 对齐）。
    #
    # 为什么：合并会**整份重写** M.jsonl。第一次跑的时候，我已经给 8 条做过映射，
    # 随后为了合并分片又跑了一次 merge —— 那 8 条的 mapped_at 就被抹掉了，
    # 而它代表的是已经花掉的 API 成本。**派生工作不该被一次重写无声清空。**
    # 按 quote（逐字、唯一性高）对齐，而不是按 id（会重编号）。
    keep: dict[str, dict] = {}
    if os.path.exists(path(book)):
        for old in load(book):
            if old.get("mapped_at") and old.get("quote"):
                keep[old["quote"]] = {k: old[k] for k in
                                      ("status", "maps_to", "why_not", "mapped_at",
                                       "mapped_by", "map_note", "rhetoric",
                                       "rhetoric_note", "conflict_id")
                                      if k in old}
    for c in seq:
        k = keep.get(c.get("quote") or "")
        if k:
            c.update(k)
    with io.open(path(book), "w", encoding="utf-8") as f:
        for c in seq:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return {"n": len(seq), "parts": [os.path.basename(p) for p in parts],
            "duplicates_found": dup, "mapping_preserved": len(keep)}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="观点总表体检")
    ap.add_argument("--merge", default=None, help="合并分片：--merge M")
    ap.add_argument("--import", dest="imp", default=None,
                    help="从 JSON 文件导入（{'book':'M','claims':[...]}）")
    a = ap.parse_args()
    if a.merge:
        r = merge_parts(a.merge)
        print("合并 %s 的分片 → %d 条｜来源 %s" % (a.merge, r["n"], r["parts"]))
        if r["duplicates_found"]:
            print("   ⚠️ 撞号 %d 个（已按文件顺序重编号，原号保留在 _id_was）"
                  % len(r["duplicates_found"]))
        if r.get("mapping_preserved"):
            print("   保留了已有映射结果 %d 条（按 quote 对齐）"
                  % r["mapping_preserved"])
    if a.imp:
        d = json.load(io.open(a.imp, encoding="utf-8"))
        n = save(d["book"], d["claims"])
        print("导入 %d 条（去重后）" % n)
    cl = closure()
    print("=" * 74)
    print("观点总表体检")
    print("=" * 74)
    print("总条数：%d｜按书：%s" % (cl["total"], cl["by_book"]))
    print("按状态：%s" % cl["by_status"])
    q = verify_quotes()
    print("\n逐字核对：%d 条通过，%d 条**原文里找不到**" % (q["ok"], len(q["bad"])))
    for b in q["bad"][:10]:
        print("   ✗ %s：%s  %s" % (b.get("id"), b.get("why"), b.get("quote", "")))
    sp = check_schema()
    print("字段完整性：%d 处问题" % len(sp["problems"]))
    for p in sp["problems"][:10]:
        print("   ✗ %s" % p)
    print("\n并集未完成 —— 待补清单（%d 条）:" % len(cl["未实现（要补的清单）"]))
    for o in cl["未实现（要补的清单）"][:12]:
        print("   · %s [%s] %s" % (o["id"], o["locator"], (o["claim"] or "")[:52]))
    if cl["冲突待裁"]:
        print("\n交集待裁（%d 条）:" % len(cl["冲突待裁"]))
        for o in cl["冲突待裁"][:12]:
            print("   · %s %s" % (o["id"], (o["claim"] or "")[:60]))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""依据列可追溯性：清单里每个 claim id 必须**真实存在于观点总表**。

为什么需要这条测试（它是一次真事故换来的）
────────────────────────────────────────────────────────────
2026-10-01，我在给用户的口头报告里写下「M-970 第三途径」。
**M-970 在 1718 条 [E] / 601 条 [M] 里根本不存在** —— 正确的编号是 M-570。
用户是靠**人工核对**发现的。

编号写错不是小事：`spec/系统能力清单.*` 是验收判据 F1（「每条规则可追溯到
书里哪句」）的自动化载体。里面挂一个不存在的编号，等于**追溯链断了却看不出来** ——
比"没有依据"更坏，因为它看起来有依据。

所以这条测试把「依据列里的 id 必须存在」钉死：
    · 扫出依据列里所有形如 M-123 / DB-45 / E-6789 的编号
    · 逐个去观点总表里查
    · 查不到 → 失败，并**指名道姓**说是哪个单元、哪个编号、以及表里最接近的候选

⚠️ 另外锁一条：**允许暂时没有 id 的单元必须登记在册**（`_NO_ID_OK`），
   不许悄悄多出来 —— 否则「依据列可以随便写句话」就成了后门。

⚠️ 运行请带 `-B`。
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

_ROOT_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT_PROJ, "engine"))
os.environ.setdefault("EGO_ROOT", _ROOT_PROJ)

import system_map as S              # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []
CASES: list[tuple[str, object]] = []

# 依据列里出现的编号形态：M-570 / DB-498 / E-1718 / [p428] 不算（那是页码）
_ID_RE = re.compile(r"\b(?:M|DB|E)-\d+\b")

# ⚠️ 允许**暂时**没有 claim id 的单元 —— 必须登记在册，且写明为什么。
#    这份名单只允许变短，不允许悄悄变长。
# 本轮新增的 7 个单元（claim id 约定只对它们生效）
_NEW7 = ("dev:PERCEPTION_GATE", "dev:SELF_RULES", "dev:ATTITUDE_EXEMPT",
         "dev:TENSION_GROWTH", "const:TENSION_DRIVE",
         "dev:PATH_EXPERIENTIAL", "dev:PATH_ATTITUDINAL")

_NO_ID_OK = {
    "const:TENSION_DRIVE":
        "依据是**代码常量**（mechanism.py 的 tension_low），不是某一条观点",
}


def case(name: str):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def _run_one(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except AssertionError as e:
        RESULTS.append((name, False, str(e) or "断言失败"))
    except Exception as e:                         # noqa: BLE001
        RESULTS.append((name, False, "%s: %s" % (type(e).__name__, e)))


_BOOKS: dict = {}


def _load(book: str) -> dict:
    if book not in _BOOKS:
        p = os.path.join(_ROOT_PROJ, "spec", "观点总表", "%s.jsonl" % book)
        _BOOKS[book] = {json.loads(l)["id"]: json.loads(l)
                        for l in io.open(p, encoding="utf-8") if l.strip()}
    return _BOOKS[book]


def _all_ids() -> set:
    out = set()
    for b in ("M", "DB", "E"):
        out |= set(_load(b).keys())
    return out


def _claim(cid: str):
    return _load(cid.split("-")[0]).get(cid)


def _near(cid: str) -> list:
    """编号写错时，给出表里最接近的候选 —— 让报错直接可修。"""
    pre, _, num = cid.rpartition("-")
    try:
        n = int(num)
    except ValueError:
        return []
    return ["%s-%d" % (pre, x) for x in (n - 1, n + 1, n - 10, n + 10)
            if _claim("%s-%d" % (pre, x))]


# ══════════════════════════════════════════════════════════════
@case("【B1】依据列里的每个 claim id 都真实存在于观点总表")
def b1():
    items = S.collect()
    bad = []
    checked = 0
    for x in items:
        basis = x.get("basis") or ""
        for cid in _ID_RE.findall(basis):
            checked += 1
            if _claim(cid) is None:
                bad.append("单元 %s 引了不存在的编号 %s（最接近的候选：%s）"
                           % (x["id"], cid, "、".join(_near(cid)) or "无"))
    assert checked > 0, "一个编号都没扫到 —— 判据失效了"
    assert not bad, "★ 依据列里有不存在的编号：\n         " + "\n         ".join(bad)
    # 反向确认判据有效：一个编造的编号必须被抓到
    fake = "M-99999"
    assert _claim(fake) is None, "M-99999 竟然存在？测试前提失效"
    assert _ID_RE.findall("依据 [M] M-99999：编的") == ["M-99999"], "正则抓不到编号"


# ══════════════════════════════════════════════════════════════
@case("【B2】没有 claim id 的单元必须在册（不许悄悄多出来）")
def b2():
    items = S.collect()
    no_id = {}
    for x in items:
        basis = x.get("basis") or ""
        # ⚠️ **只查新增的 7 个单元**。原 96 个用的是 `[E]`/`[M]`/`[D]` ＋页码 `[p428]`
        #    的引用约定 —— claim id 这个约定是本轮给新单元新引入的。
        #    第一版没限定范围，把 96 个老单元全报成"没有 id"，那是**判据写宽了**，
        #    不是数据有问题。老约定要不要统一，是另一个议题，不在这条测试的职权内。
        if x["id"] not in _NEW7 or x["id"] in _NO_ID_OK:
            continue
        if not _ID_RE.findall(basis):
            no_id[x["id"]] = basis[:60]
    assert not no_id, (
        "★ 这些单元的依据列里没有任何 claim id，却没登记在 _NO_ID_OK：\n         "
        + "\n         ".join("%s → %s" % kv for kv in no_id.items()))
    # 名单里的单元必须真的没有 id（名单不许挂空名）
    for uid, why in _NO_ID_OK.items():
        hits = [x for x in items if x["id"] == uid]
        assert hits, "_NO_ID_OK 里的 %s 在清单里不存在 —— 名单过期了" % uid
        assert not _ID_RE.findall(hits[0].get("basis") or ""), (
            "%s 已经有 claim id 了，应当从 _NO_ID_OK 里删掉" % uid)


# ══════════════════════════════════════════════════════════════
@case("【B3】新增单元的依据列必须带原文，不能只写编号")
def b3():
    """光有编号不够 —— 验收判据 F1 要的是「追溯到书里哪**句**」。"""
    items = S.collect()
    for uid in _NEW7:
        x = next((y for y in items if y["id"] == uid), None)
        assert x is not None, "新增单元 %s 不在清单里" % uid
        basis = x.get("basis") or ""
        assert "：" in basis, "%s 的依据列没有「编号：原文」形式：%s" % (uid, basis[:60])
        # 编号后面必须跟一段原文（≥8 字），不能就一个编号了事
        for cid in _ID_RE.findall(basis):
            # ⚠️ 依据列的内部**分号**是 2026-10-02 从 ｜ 改过来的 ——
            #    内文分隔符与列分隔符同形会诱发模型的"列错位"幻觉
            #    （用户原话：「极易诱发『列错位』幻觉，导致模型误将依据切片当作运行状态」）。
            tail = basis.split(cid, 1)[1]
            txt = tail.split("；")[0]
            assert len(txt.strip("：: ")) >= 8, (
                "%s 引了 %s 但没跟原文：%r" % (uid, cid, txt[:40]))


# ══════════════════════════════════════════════════════════════
@case("【B4】依据列与观点总表的原文一致（逐字核对）")
def b4():
    """依据列里引的原文，必须是那条观点的 quote 的**子串**。
    防的是"编号对、原文自己另写一句"。"""
    items = S.collect()
    checked = 0
    for x in items:
        if x["id"] not in _NEW7:            # 同 B2：只查新单元（老约定不在本条职权内）
            continue
        basis = x.get("basis") or ""
        for cid in _ID_RE.findall(basis):
            c = _claim(cid)
            if c is None:
                continue                    # B1 管这个
            tail = basis.split(cid, 1)[1].split("；")[0].strip("：: ")
            if len(tail) < 8:
                continue                    # B3 管这个
            quote = (c.get("quote") or "").replace("\n", "")
            checked += 1
            # ⚠️ 先剥掉引用符号再取头 —— 依据列里习惯写成「原文」，
            #    而表里的 quote 不带引号。第一版没剥，`「评定人员觉察…`[:12]
            #    把 `「` 一起取进去了，于是永远对不上。**判据不能把格式差当成内容差。**
            head = tail.strip("「」『』：:  ")[:12]
            assert head in quote, (
                "单元 %s 引 %s 的原文对不上：\n"
                "           依据列写：%s\n"
                "           表里原文：%s"
                % (x["id"], cid, tail[:50], quote[:50]))
    assert checked > 0, "一条都没核对到 —— 判据失效了"


def main() -> int:
    for name, fn in CASES:
        _run_one(name, fn)
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 80)
    print("依据列可追溯性（claim id 必须存在）")
    print("=" * 80)
    for name, passed, msg in RESULTS:
        print("  [%s] %s" % ("PASS" if passed else "FAIL", name))
        if not passed:
            print("         %s" % msg)
    print("-" * 80)
    print("结果: %d 通过 / %d 失败 / 共 %d"
          % (ok, len(RESULTS) - ok, len(RESULTS)))
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())

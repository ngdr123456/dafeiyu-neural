# -*- coding: utf-8 -*-
"""T21 补缺清单的不变量测试。

为什么要有这个
────────────────────────────────────────────────────────────
用户逐格重数抓到了三处对不上：

    高行 771≠772｜未定列 489≠490｜按书 1616≠1615

根因：**两种视图用了不同的分母** ——
控制台的统计用 `rows`（含「人工恢复」那一行），交叉表用 `real`（纯候选池）。
三个差额全部来自那一行（它在「补缺」里、置信=高、缺口类型=未定、书=M）。

**一行人工恢复的插入，不该改变任何一格统计。** 这条现在被测试钉死。

钉死的不变量
────────────────────────────────────────────────────────────
    V1 四类归属互斥，且合计 == 候选池条数
    V2 **人工恢复那一行不参与任何统计**（插一行、所有格子必须一格不动）
    V3 补缺 = 候选池 − 先修OCR − 接线 − 待核
    V4 红线①：创造途径必须在，且理由里点明 M-232
    V5 红线②：待核严格 = 20（待核 5 ＋ 未复现 15）
    V6 池内「接线」计 0，且是"11 在池外 + 5 被待核先认领"，不是"都不在池里"
    V7 置信分级与 remap_from / 侧日志一致
    V8 带真噪声 → 「先修 OCR」；页码标记**不算**噪声
    V9 只写两个产出文件，不碰别的
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

_ROOT_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RESULTS: list = []
CASES: list = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def _mkroot(claims, side=None, consensus=None):
    """造一个最小 EGO_ROOT。claims = {book: [row, ...]}"""
    d = tempfile.mkdtemp(prefix="ego_gap_")
    os.makedirs(os.path.join(d, "spec", "观点总表"), exist_ok=True)
    for b, rows in claims.items():
        with io.open(os.path.join(d, "spec", "观点总表", "%s.jsonl" % b),
                     "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if side is not None:
        with io.open(os.path.join(d, "spec", "重判侧日志.jsonl"),
                     "w", encoding="utf-8") as f:
            for x in side:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
    if consensus is not None:
        with io.open(os.path.join(d, "spec", "共识核.jsonl"),
                     "w", encoding="utf-8") as f:
            for x in consensus:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
    return d


def _run(root):
    """在指定 root 下跑 gapfill，返回 (rows, 控制台输出)。"""
    import importlib
    old = os.environ.get("EGO_ROOT")
    os.environ["EGO_ROOT"] = root
    sys.path.insert(0, os.path.join(_ROOT_PROJ, "engine"))
    for m in ("gapfill",):
        if m in sys.modules:
            del sys.modules[m]
    G = importlib.import_module("gapfill")
    buf = io.StringIO()
    oldout = sys.stdout
    sys.stdout = buf
    try:
        G.main()
    finally:
        sys.stdout = oldout
        if old is None:
            os.environ.pop("EGO_ROOT", None)
        else:
            os.environ["EGO_ROOT"] = old
    rows = [json.loads(l) for l in
            io.open(os.path.join(root, "spec", "补缺清单.jsonl"), encoding="utf-8")
            if l.strip()]
    return rows, buf.getvalue()


def _base():
    """一个最小的三本 + 侧日志 + 共识核。"""
    claims = {
        "M": [
            {"id": "M-001", "quote": "干净的话", "claim": "c1", "kind": "机制",
             "status": "未实现"},
            {"id": "M-002", "quote": "干净的话二", "claim": "c2", "kind": "方法",
             "status": "未实现"},
            # 原已实现、重判未复现 → 待核
            {"id": "M-003", "quote": "q3", "claim": "c3", "kind": "事实",
             "status": "已实现",
             "remap_from": {"status": "已实现", "maps_to": [], "why_not": ""}},
            # 摇摆：侧日志里"新"是已实现
            {"id": "M-004", "quote": "q4", "claim": "c4", "kind": "事实",
             "status": "未实现", "remap_from": {"status": "未实现", "maps_to": []}},
            # 带真噪声
            {"id": "M-005", "quote": "出--致的概念", "claim": "c5", "kind": "机制",
             "status": "未实现"},
            # 只有页码标记 → **不算**噪声
            {"id": "M-006", "quote": "[p428] 正常句子", "claim": "c6", "kind": "机制",
             "status": "未实现"},
        ],
        "DB": [{"id": "DB-001", "quote": "干净", "claim": "d1", "kind": "规范",
                "status": "未实现"}],
        "E": [
            {"id": "E-168", "quote": "q", "claim": "待核一条", "kind": "事实",
             "status": "已实现", "remap_from": {"status": "未实现", "maps_to": []}},
        ],
    }
    side = [{"id": "M-003", "book": "M", "旧": "已实现", "新": "未实现"},
            {"id": "M-004", "book": "M", "旧": "未实现", "新": "已实现"}]
    cons = [{"单元": "dev:SELF_RULES", "运行状态": "已建未启用",
             "指定依据": [{"id": "E-168", "模型是否确认": True}],
             "独立命中": [], "待核": []}]
    return claims, side, cons


# ══════════════════════════════════════════════════════════════
@case("【V1】四类归属互斥，合计 == 候选池条数")
def v1():
    claims, side, cons = _base()
    root = _mkroot(claims, side, cons)
    try:
        rows, _ = _run(root)
        real = [r for r in rows if r["来源状态"] != "人工恢复"]
        from collections import Counter
        b = Counter(r["归属"] for r in real)
        assert set(b) <= {"补缺", "先修 OCR", "接线", "待核"}, b
        assert sum(b.values()) == len(real), (sum(b.values()), len(real))
        assert b["接线"] == 0, "本例里接线命中 E-168 被待核先认领，池内应为 0"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【V2】★ 人工恢复那一行不参与任何统计（插一行，所有格子一格不动）")
def v2():
    """这条正是三处数字对不上的那个 bug。"""
    claims, side, cons = _base()
    root = _mkroot(claims, side, cons)
    try:
        rows, out = _run(root)
        real = [r for r in rows if r["来源状态"] != "人工恢复"]
        art = [r for r in rows if r["来源状态"] == "人工恢复"]
        assert len(art) == 1, "人工恢复行必须恰好 1 行"
        # 人工恢复那行确实在「补缺」里 —— 所以"用不用它当分母"会真的改变数字
        assert art[0]["归属"] == "补缺", art[0]["归属"]

        import re as _re
        from collections import Counter
        sub = [r for r in real if r["归属"] == "补缺"]
        conf = Counter(r["置信"] for r in sub)
        kt = Counter(r["缺口类型"] for r in sub)
        bk = Counter(r["书"] for r in sub)
        # ⚠️ 第一版这里**自己重算了一遍**，于是改 gapfill.py 的统计它抓不到 ——
        #    mutation 验证时"M1 分母改回含人工恢复行"**没让测试失败**。
        #    现在改为**验脚本打印出来的那一行**。
        m = _re.search(r"补缺内部置信：(\{.*?\})", out)
        assert m, "控制台没打印「补缺内部置信」，无法核对：\n%s" % out[-400:]
        printed = eval(m.group(1))                      # noqa: S307 —— 自己的输出
        assert printed == dict(conf), \
            "★ 打印的置信分布与候选池分母不符：\n  打印 %s\n  应为 %s" % (printed, dict(conf))
        m2 = _re.search(r"补缺缺口类型：(\{.*?\})", out)
        assert m2 and eval(m2.group(1)) == dict(kt), \
            "★ 打印的缺口类型与候选池分母不符：%s" % (m2.group(1) if m2 else "缺")
        m3 = _re.search(r"补缺按书：(\{.*?\})", out)
        assert m3 and eval(m3.group(1)) == dict(bk), \
            "★ 打印的按书分布与候选池分母不符：%s" % (m3.group(1) if m3 else "缺")
        assert sum(bk.values()) == len(sub), "按书合计必须等于补缺条数"
        assert sum(kt.values()) == len(sub), "缺口类型合计必须等于补缺条数"
        assert sum(conf.values()) == len(sub), "置信合计必须等于补缺条数"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【V4】红线①：创造途径必须在，且点明被 M-232 遮蔽")
def v4():
    claims, side, cons = _base()
    root = _mkroot(claims, side, cons)
    try:
        rows, _ = _run(root)
        art = [r for r in rows if r["来源状态"] == "人工恢复"]
        assert len(art) == 1
        assert "创造" in art[0]["claim"], art[0]["claim"]
        assert "M-232" in art[0]["归属理由"], "理由里必须点明被 M-232 遮蔽"
        assert "遮蔽" in art[0]["归属理由"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【V5】红线②：待核严格 = 待核5 + 未复现15（用真项目数）")
def v5():
    rows = [json.loads(l) for l in io.open(
        os.path.join(_ROOT_PROJ, "spec", "补缺清单.jsonl"), encoding="utf-8")
        if l.strip()]
    w = [r for r in rows if r["归属"] == "待核"]
    ids = {r["id"] for r in w}
    W5 = {"E-168", "E-229", "E-156", "E-892", "M-232"}
    assert len(w) == 20, "待核应 20 条，实际 %d" % len(w)
    assert W5 <= ids, "待核 5 条必须全在：缺 %s" % sorted(W5 - ids)
    assert len(ids - W5) == 15, "未复现应 15 条，实际 %d" % len(ids - W5)


# ══════════════════════════════════════════════════════════════
@case("【V6】池内「接线」计 0 —— 是 11 在池外 + 5 被待核先认领")
def v6():
    """不是「都不在池里」（第一版写错了）。"""
    rows = [json.loads(l) for l in io.open(
        os.path.join(_ROOT_PROJ, "spec", "补缺清单.jsonl"), encoding="utf-8")
        if l.strip()]
    assert sum(1 for r in rows if r["归属"] == "接线") == 0
    # 共识核里的 19 条命中 → 去重 16 个观点
    # ⚠️ 判据必须是「**该单元带不带 status 键**」（= 是不是新增的发展水平单元），
    #    **不是它当前通没通电**。
    #
    #    第一版写的是 `if r["运行状态"] == "生效中": continue` ——
    #    于是 T33 把那 5 个单元改成生效中之后，19 条立刻缩成 7 条，
    #    这条测试就挂了。**它挂得对**：同一个错我在 consensus.py 里刚修过一次
    #    （方案甲：接线范围冻结），测试里却还留着老的判据。
    #    这是"测试自己抓出了实现与测试的不一致"。
    sys.path.insert(0, os.path.join(_ROOT_PROJ, "engine"))
    import system_map as _S
    # ⚠️ 用**显式常量**，不是「带 status 键」那种间接判据（用户 T33 返工点名）
    _frozen = set(_S.DEV_UNIT_IDS)
    assert len(_frozen) == 7, "冻结集合必须是 7 个单元，实际 %d" % len(_frozen)
    w = []
    for l in io.open(os.path.join(_ROOT_PROJ, "spec", "共识核.jsonl"),
                     encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        if r["单元"] not in _frozen:
            continue
        w += [d["id"] for d in r.get("指定依据") or [] if d.get("模型是否确认")]
        w += list(r.get("独立命中") or [])
        w += list(r.get("待核") or [])
    uniq = set(w)
    wait5 = {"E-168", "E-229", "E-156", "E-892", "M-232"}
    assert len(w) == 19, "接线命中应 19 条，实际 %d" % len(w)
    assert len(uniq) == 16, "去重应 16 个观点，实际 %d" % len(uniq)
    assert uniq & wait5 == wait5, "待核 5 条应全在接线清单里"
    assert len(uniq - wait5) == 11, "非待核的应 11 个"
    # 关键：那 5 条在池里的身份是「待核」，不是「接线」——一物两名，不重复计数
    rows_by_id = {r["id"]: r for r in rows}
    for cid in wait5:
        assert rows_by_id[cid]["归属"] == "待核", \
            "%s 应归「待核」（被先认领），实际 %s" % (cid, rows_by_id[cid]["归属"])

    # ⚠️ 上面读的是**已写好的真实文件** —— 改 gapfill.py 影响不到它，
    #    mutation 验证时"M4 待核让位给接线"**没让这条失败**。
    #    所以补一段：在合成 root 上真跑一遍，验**优先级**。
    claims, side, cons = _base()
    root = _mkroot(claims, side, cons)
    try:
        rr, _ = _run(root)
        byid = {r["id"]: r for r in rr}
        # E-168 同时在 WAIT5 和接线清单里 —— 必须归「待核」（前者优先）
        assert byid["E-168"]["归属"] == "待核", \
            "★ 同时命中待核与接线时，必须归「待核」；实际 %s" % byid["E-168"]["归属"]
        from collections import Counter as _C
        b = _C(r["归属"] for r in rr if r["来源状态"] != "人工恢复")
        assert b.get("接线", 0) == 0, "被待核先认领后，池内接线必须是 0，实际 %d" % b.get("接线", 0)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【V7】置信分级与 remap_from / 侧日志一致")
def v7():
    claims, side, cons = _base()
    root = _mkroot(claims, side, cons)
    try:
        rows, _ = _run(root)
        by = {r["id"]: r for r in rows}
        # M-004：侧日志"新"=已实现 → 摇摆
        assert by["M-004"]["置信"] == "摇摆", by["M-004"]["置信"]
        # M-001：有 remap_from 且旧=未实现 → 高
        #   （本例 M-001 没有 remap_from → 中）
        assert by["M-001"]["置信"] == "中", by["M-001"]["置信"]
        # M-003：原已实现、重判未复现 → 不在补缺，归待核
        assert by["M-003"]["归属"] == "待核", by["M-003"]["归属"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【V8】带真噪声 → 先修 OCR；**页码标记不算噪声**")
def v8():
    claims, side, cons = _base()
    root = _mkroot(claims, side, cons)
    try:
        rows, _ = _run(root)
        by = {r["id"]: r for r in rows}
        assert by["M-005"]["归属"] == "先修 OCR", "连字符噪声应进先修 OCR"
        assert by["M-006"]["归属"] == "补缺", "只有页码标记的**不算噪声**"
        assert by["M-006"]["噪声"] == "无"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【V9】只写两个产出文件（写回纪律）")
def v9():
    src = io.open(os.path.join(_ROOT_PROJ, "engine", "gapfill.py"),
                  encoding="utf-8").read()
    for bad in ("观点总表", "重判侧日志\"", "共识核.jsonl\", \"w",
                "共识核_主张级"):
        # 只允许**读**这些路径，不允许以写模式打开
        for line in src.splitlines():
            if bad in line and '"w"' in line:
                raise AssertionError("gapfill 不该写：%s" % line.strip())
    assert 'OUT_JSON' in src and 'OUT_MD' in src
    # 产出只有这两个
    import re
    writes = re.findall(r'io\.open\((\w+),\s*"w"', src)
    assert set(writes) <= {"OUT_JSON", "OUT_MD"}, "只许写这两个：%s" % writes


# ══════════════════════════════════════════════════════════════
def main() -> int:
    for name, fn in CASES:
        try:
            fn()
            RESULTS.append((name, True, ""))
        except AssertionError as e:
            RESULTS.append((name, False, str(e) or "断言失败"))
        except Exception as e:                          # noqa: BLE001
            RESULTS.append((name, False, "%s: %s" % (type(e).__name__, e)))
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 78)
    print("T21 补缺清单不变量")
    print("=" * 78)
    for name, passed, msg in RESULTS:
        print("  [%s] %s" % ("PASS" if passed else "FAIL", name))
        if not passed:
            print("         %s" % msg)
    print("-" * 78)
    print("结果: %d 通过 / %d 失败 / 共 %d"
          % (ok, len(RESULTS) - ok, len(RESULTS)))
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""提案的稳定主键 / 数据指纹 / 结案记录 —— 守护测试（用户裁定 2026-10-02）。

用户裁定的两条红线
────────────────────────────────────────────────────────────
> 「**稳定主键 sid**：以确定性哈希或命名空间映射生成……
>   位次号 P001 仅供当前界面序号展示，**绝不作持久化外键**」
> 「编写 `tests/test_proposal_log.py`：
>   **贯彻隔离红线：测试必须在 tempfile 沙箱中执行，
>   设置真实 `state/train/` 双向不被碰触的物理断言。**」

Z1~Z3  主键 / 指纹（纯函数，无 IO）
Z4~Z7  结案记录与三种标注（**沙箱**）
Z8     ★★ 隔离红线：真实 state/train + spec/任务清单 双向物理断言
Z9     ★★ 防串号：位次变、sid 不变（**事由就是那次真实串号**）
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "engine"))

import proposal_log as PL                       # noqa: E402

RESULTS: list = []
CASES: list = []

REAL_OUT = os.path.join(_ROOT, "state", "train", "proposal_outcomes.jsonl")
REAL_TASKS = os.path.join(_ROOT, "spec", "任务清单.jsonl")
REAL_DEC = os.path.join(_ROOT, "state", "train", "decisions.jsonl")


def case(name):
    def deco(fn):
        fn._name = name
        CASES.append(fn)
        return fn
    return deco


def _snap():
    """真实文件的存在性 + 大小 + mtime（三重指纹，防"改了但大小没变"）。"""
    out = {}
    for p in (REAL_OUT, REAL_TASKS, REAL_DEC):
        if os.path.exists(p):
            st = os.stat(p)
            out[p] = (st.st_size, st.st_mtime_ns)
        else:
            out[p] = None
    return out


def _tmp():
    d = tempfile.mkdtemp(prefix="ego_plog_")
    os.makedirs(os.path.join(d, "state", "train"), exist_ok=True)
    os.makedirs(os.path.join(d, "spec"), exist_ok=True)
    return d


# ══════════════════════════════════════════════════════════════
@case("【Z1】sid 确定性：同样的 (kind,target) 永远同一个 sid")
def z1():
    a = PL.sid_of("dead_rule", "机制条件表")
    b = PL.sid_of("dead_rule", "机制条件表")
    assert a == b, "不稳定：%r vs %r" % (a, b)
    assert a == "dead_rule:机制条件表", a
    # 空白/特殊字符统一去掉（用户裁定原话）
    assert PL.sid_of("dead_rule", " 机制 条件 表 ") == a, "空白没归一"
    # 不同 kind 不能撞
    assert PL.sid_of("coverage", "机制条件表") != a
    # 长文本走哈希
    long_s = "这是一句很长的话" * 10
    h = PL.sid_of("lexicon_gap", long_s)
    assert len(h) < 40 and "#" in h, "长对象键应走哈希：%s" % h
    assert h == PL.sid_of("lexicon_gap", long_s), "哈希不稳定"
    # 空对象键不崩
    assert PL.sid_of("x", "") == "x:<empty>"


@case("【Z2】★ 位次变、sid 不变（防串号 —— 事由就是那次真实串号）")
def z2():
    """事由：`decisions.jsonl` 里 2026-10-01 的 `P001` 当时指「复核闸门主因」，
    今天重算 `P001` 指「复核沉默轮」—— **同一个 pid 指向了两条提案**。

    ⇒ `pid` 只作界面序号；**一切记录绑 sid**。
    """
    # 第一次算：闸门在前
    first = [("gate_review", PL.TARGETS["gate_review"]),
             ("coverage", PL.TARGETS["coverage"])]
    sids1 = {k: PL.sid_of(k, t) for k, t in first}
    # 第二次算：闸门那条被解决了、不再生成 → 沉默轮从 P002 变成 P001
    second = [("coverage", PL.TARGETS["coverage"])]
    sids2 = {k: PL.sid_of(k, t) for k, t in second}
    assert sids2["coverage"] == sids1["coverage"], \
        "★ 位次变了 sid 却跟着变 —— 又串号了"
    # 而 pid 确实会变（这正是不能用它的原因）
    pid1 = {k: "P%03d" % (i + 1) for i, (k, _) in enumerate(first)}
    pid2 = {k: "P%03d" % (i + 1) for i, (k, _) in enumerate(second)}
    assert pid2["coverage"] != pid1["coverage"], \
        "前提失效：位次号本该会变（不然这条测试没意义）"


@case("【Z3】数据指纹：能看出「依据的数据变了」，且不把生成时间算进去")
def z3():
    rows = [{"mech": {"e_version": 2}, "ts": "2026-10-02T10:00:00"},
            {"mech": {"e_version": 2}, "ts": "2026-10-02T10:05:00"}]
    fp1 = PL.fingerprint(2, 1, rows)
    assert fp1["turns"] == 2 and fp1["evals"] == 1
    assert fp1["e_version_dist"] == {"2": 2}, fp1["e_version_dist"]
    assert fp1["last_ts"] == "2026-10-02T10:05:00"
    # 同一批数据 → 指纹"没变"（生成时间不同也不算变）
    fp2 = PL.fingerprint(2, 1, rows)
    assert not PL.fp_changed(fp1, fp2), "同批数据不该判为变了"
    # 数据涨了 → 变了
    assert PL.fp_changed(fp1, PL.fingerprint(3, 1, rows)), "轮数变了应判为变"
    # ★ 版本换了 → 变了（P003 的教训：v1 数据下的结论在 v2 之后失效）
    #   ⚠️ 这里必须**带上 ts** —— 第一版漏了，于是 last_ts 从"有"变"无"，
    #      判成"变了"，测试自己把自己绊倒。
    rows2 = [{"mech": {"e_version": 2}, "ts": "2026-10-02T10:00:00"},
             {"mech": {"e_version": 2}, "ts": "2026-10-02T10:05:00"}]
    assert not PL.fp_changed(fp1, PL.fingerprint(2, 1, rows2))
    rows3 = [{"mech": {"e_version": None}, "ts": "2026-10-02T10:00:00"},
             {"mech": {"e_version": None}, "ts": "2026-10-02T10:05:00"}]
    assert PL.fp_changed(fp1, PL.fingerprint(2, 1, rows3)), \
        "★ e_version 分布变了必须判为变（这正是 P003 那个坑）"
    # 空指纹不炸
    assert not PL.fp_changed(None, fp1)


# ══════════════════════════════════════════════════════════════
@case("【Z4】结案记录：原子写、可读回、非法决定被拒")
def z4():
    d = _tmp()
    try:
        assert PL.record("k:a", "k", "approved", "标题", root=d), "没写进去"
        assert PL.record("k:a", "k", "rejected", "标题", root=d)
        assert PL.record("k:a", "k", "bogus", "标题", root=d) is None, \
            "★ 非法决定应被拒（封闭集合）"
        rows = PL.load(d)
        assert len(rows) == 2, "应 2 条，实际 %d" % len(rows)
        assert rows[0]["sid"] == "k:a" and rows[0]["decision"] == "approved"
        # 不留半截文件
        p = PL._path(d)
        assert not [x for x in os.listdir(os.path.dirname(p)) if x.endswith(".tmp")], \
            "★ 留下 .tmp 半截文件"
        # 读不到 → 空列表，不抛
        assert PL.load(tempfile.mkdtemp()) == []
    finally:
        shutil.rmtree(d, ignore_errors=True)


@case("【Z5】三种标注：已批准 / 曾驳回 N 次 / ⚠️ 依据已更新")
def z5():
    d = _tmp()
    try:
        sid = "dead_rule:机制条件表"
        prop = {"sid": sid, "kind": "dead_rule"}
        # 无历史 → 无标注
        PL.annotate(prop, None, root=d)
        assert prop["history_n"] == 0 and prop["notes"] == [], prop["notes"]
        # 驳回 2 次 → 「曾驳回 2 次」
        PL.record(sid, "dead_rule", "rejected", "t", root=d)
        PL.record(sid, "dead_rule", "rejected", "t", root=d)
        PL.annotate(prop, None, root=d)
        assert any("曾驳回 2 次" in n for n in prop["notes"]), prop["notes"]
        # 批准 → 「已批准，执行中」
        PL.record(sid, "dead_rule", "approved", "t", fp={"turns": 10, "at": "2026-10-01 00:00:00"}, root=d)
        PL.annotate(prop, {"turns": 99}, root=d)
        ns = prop["notes"]
        assert any("已批准" in n and "执行中" in n for n in ns), ns
        assert any("依据的数据已更新" in n for n in ns), ns
        assert prop["history_n"] == 3
    finally:
        shutil.rmtree(d, ignore_errors=True)


@case("【Z6】★ 驳回**不抑制**（用户裁定：这是管理员观察职责）")
def z6():
    """用户裁定原话：「驳回的可以再提。**这是管理员观察职责**，
    毕竟它有条职责就是负责观察上交升级方案。」"""
    d = _tmp()
    try:
        sid = "coverage:静默轮"
        PL.record(sid, "coverage", "rejected", "t", root=d)
        prop = {"sid": sid, "kind": "coverage"}
        PL.annotate(prop, None, root=d)
        # 标注里有记录，但**没有任何"抑制"字段** —— 提案照常存在于队列里
        assert any("曾驳回" in n for n in prop["notes"])
        assert "suppressed" not in prop and "hidden" not in prop, \
            "★ 出现了抑制字段 —— 用户裁定不要抑制逻辑"
        # 且模块里没有抑制函数
        src = io.open(os.path.join(_ROOT, "engine", "proposal_log.py"),
                      encoding="utf-8").read()
        for bad in ("def suppress", "def is_suppressed", "def filter_out"):
            assert bad not in src, "★ 出现了抑制函数：%s" % bad
    finally:
        shutil.rmtree(d, ignore_errors=True)


@case("【Z7】批准 → 追加待办（幂等）；任务标完成 → completed_sids 认得出")
def z7():
    d = _tmp()
    try:
        sid = "dead_rule:机制条件表"
        tid = PL.enqueue_task(sid, "dead_rule", "机制条件表里有 11 条从未触发",
                              "两条路", root=d)
        assert tid == "P-" + sid, tid
        # 幂等
        assert PL.enqueue_task(sid, "dead_rule", "x", root=d) is None, \
            "★ 重复批准会重复追加待办"
        tp = PL._tasks_path(d)
        rows = [json.loads(l) for l in io.open(tp, encoding="utf-8") if l.strip()]
        assert len(rows) == 1 and rows[0]["status"] == "待办"
        # 还没完成 → 认不出
        assert PL.completed_sids(d) == []
        # 标完成 → 认得出
        rows[0]["status"] = "已完成"
        io.open(tp, "w", encoding="utf-8").write(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        got = PL.completed_sids(d)
        assert got and got[0][0] == sid, got
        # 不带 sid 前缀的普通任务**不该**被认成提案收尾
        rows.append({"id": "T99", "title": "普通任务", "status": "已完成"})
        io.open(tp, "w", encoding="utf-8").write(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        assert len(PL.completed_sids(d)) == 1, "★ 把普通任务也认成提案收尾了"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【Z8】★★ 隔离红线：真实 state/train + spec/任务清单 **双向**物理断言")
def z8():
    """用户裁定：「测试必须在 tempfile 沙箱中执行，
    设置真实 `state/train/` **双向不被碰触**的物理断言。」

    双向 = ①真实文件绝不被创建/改动 ②沙箱里**确实**写出了合法内容。
    （同 test_carry 的 C1 教训：只查一遍会被自己的清理动作擦掉证据。）
    """
    before = _snap()
    d = _tmp()
    p = PL._path(d)

    def both_ways(step, box_should_exist):
        assert _snap() == before, "★ [%s] 真实文件被改动了 —— 隔离破了" % step
        if box_should_exist:
            assert os.path.exists(p), "★ [%s] 沙箱里应有文件却没有" % step
            rows = PL.load(d)
            assert rows and rows[0].get("sid"), "★ [%s] 沙箱内容不合法" % step

    try:
        both_ways("起点", False)
        PL.record("k:a", "k", "approved", "t", root=d)
        both_ways("record 之后", True)
        PL.annotate({"sid": "k:a"}, None, root=d)
        both_ways("annotate 之后", True)
        PL.enqueue_task("k:a", "k", "标题", root=d)
        both_ways("enqueue_task 之后", True)
        PL.completed_sids(d)
        both_ways("completed_sids 之后", True)
        PL.load(d)
        both_ways("load 之后", True)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    assert _snap() == before, "★ 收尾时真实文件与起点不一致"


@case("【Z9】★★ admin.propose() 真的打了 sid，且 pid 仍是位次号")
def z9():
    """源码级：`propose()` 必须**同时**产出 pid（界面序号）与 sid（持久化主键）。"""
    src = io.open(os.path.join(_ROOT, "engine", "admin.py"), encoding="utf-8").read()
    assert 'p["sid"] = PL.sid_of(' in src, "★ propose() 没打 sid"
    assert 'p["pid"] = "P%03d"' in src, "pid 应保留（界面序号）"
    # pid 必须在 sid **之前**赋值（保持可读），且两者都在
    i_pid = src.index('p["pid"] = "P%03d"')
    i_sid = src.index('p["sid"] = PL.sid_of(')
    assert abs(i_pid - i_sid) < 400, "pid/sid 应挨着赋值"
    # 注释里必须写明 pid 不许作外键（防以后有人拿它当键）
    seg = src[i_pid - 200:i_pid + 200]
    assert "位次号" in seg, "★ 缺「位次号」说明 —— 后来人会拿 pid 当外键"
    assert "绝不作持久化外键" in seg, "★ 缺「绝不作持久化外键」这条禁令"
    # 两个调用方都必须传 sid
    for f in ("training_studio.py", "dashboard.py"):
        t = io.open(os.path.join(_ROOT, "engine", f), encoding="utf-8").read()
        assert "sid=" in t, "★ %s 调 log_decision 时没传 sid —— 又会串号" % f


# ══════════════════════════════════════════════════════════════
@case("【Z10】★ 批准 → 追加待办／驳回 → **不追加**（admin.log_decision 整条链）")
def z10():
    """这条补的是一个**真覆盖缺口**：M3 mutation（批准时不追加待办）原来没被抓到 ——
    因为 Z1~Z9 只测了 `proposal_log` 自己的函数，
    **没测 `admin.log_decision` 那条链**。

    ⚠️ 所以本用例必须走 `admin.log_decision`（不是直接调 `enqueue_task`），
       并用 `root=` 把它整条链锁进沙箱。
    """
    d = _tmp()
    before = _snap()
    try:
        import admin as A
        sid = "dead_rule:机制条件表"
        # ① 批准 → 三样都要有
        A.log_decision("P001", True, "机制条件表里有 11 条从未触发",
                       sid=sid, kind="dead_rule", fp={"turns": 211}, root=d)
        rows = PL.load(d)
        assert len(rows) == 1 and rows[0]["decision"] == "approved", rows
        tids = PL.completed_sids(d)
        tp = PL._tasks_path(d)
        assert os.path.exists(tp), "★ 批准之后任务清单里没多出待办"
        tasks = [json.loads(l) for l in io.open(tp, encoding="utf-8") if l.strip()]
        assert len(tasks) == 1 and tasks[0]["id"] == "P-" + sid, tasks
        assert tasks[0]["status"] == "待办"
        assert "已批准" in tasks[0]["evidence"], tasks[0]["evidence"]
        # 决定流水也写了（沙箱里的那份）
        dec = os.path.join(d, "state", "train", "decisions.jsonl")
        assert os.path.exists(dec), "决定流水没写进沙箱"
        assert json.loads(io.open(dec, encoding="utf-8").readline())["sid"] == sid
        # ② 驳回 → 有结案、**没有**待办
        sid2 = "coverage:静默轮"
        A.log_decision("P002", False, "复核沉默轮", sid=sid2, kind="coverage", root=d)
        rows = PL.load(d)
        assert len(rows) == 2 and rows[1]["decision"] == "rejected"
        tasks = [json.loads(l) for l in io.open(tp, encoding="utf-8") if l.strip()]
        assert len(tasks) == 1, "★ 驳回**不该**进任务清单（实际 %d 条）" % len(tasks)
        assert tids == [], "沙箱里不该有已完成任务"
        # ③ 红线：真实文件没被碰
        assert _snap() == before, "★ Z10 碰了真实文件"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
def main() -> int:
    for fn in CASES:
        name = getattr(fn, "_name", fn.__name__)
        try:
            fn()
            RESULTS.append((name, True, ""))
        except AssertionError as e:
            RESULTS.append((name, False, str(e) or "断言失败"))
        except Exception as e:                      # noqa: BLE001
            RESULTS.append((name, False, "%s: %s" % (type(e).__name__, e)))
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 78)
    print("提案稳定主键 / 数据指纹 / 结案记录")
    print("=" * 78)
    for name, passed, msg in RESULTS:
        print("  [%s] %s" % ("PASS" if passed else "FAIL", name))
        if not passed:
            print("         %s" % msg)
    print("-" * 78)
    print("结果: %d 通过 / %d 失败 / 共 %d" % (ok, len(RESULTS) - ok, len(RESULTS)))
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())

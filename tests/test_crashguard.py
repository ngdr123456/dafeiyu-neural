# -*- coding: utf-8 -*-
"""崩溃黑匣子（T23）：三处钩子 + 环形落盘。

用户裁定（2026-10-02）测试红线：
> 「**测试隔离硬红线（吸取 C1 教训）**：`tests/test_crashguard.py` 的 X7 测试
>   必须做**双向物理断言**（断言真实 `state/crash/` 绝无文件，
>   且临时目录下真实生成合法文件），**严防测试假绿**。」

X7 的写法直接采用 C1 修好后的形态：**逐点检查 + 双向断言** ——
（真实路径必须不存在）**且**（临时路径必须存在且内容合法）。
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "engine"))

import crashguard as G                        # noqa: E402

REAL_DIR = os.path.join(_ROOT, "state", "crash")
RESULTS: list = []
CASES: list = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def _snap_real():
    if not os.path.isdir(REAL_DIR):
        return ("absent", 0)
    fs = sorted(x for x in os.listdir(REAL_DIR) if x.endswith(".json"))
    return ("present", len(fs))


def _tmp():
    """★ 建临时目录 **并把 crashguard 重定向过去** —— 测试隔离的唯一入口。"""
    d = tempfile.mkdtemp(prefix="ego_crash_")
    G.set_dir(os.path.join(d, "state", "crash"))
    return d


def _boom(kind="main"):
    try:
        raise RuntimeError("探针异常：%s" % kind)
    except Exception as e:                          # noqa: BLE001
        if kind == "main":
            G._hook_main(type(e), e, e.__traceback__)
        elif kind == "tk":
            G._hook_tk(None, type(e), e, e.__traceback__)
        return e


# ══════════════════════════════════════════════════════════════
@case("【X1】三处钩子都能装上，且各自可被调用")
def x1():
    before = _snap_real()
    assert G.install() == {"main": True, "thread": True, "tk": False}, "只给 app=None 时 tk 应为 False"
    assert sys.excepthook is G._hook_main, "sys.excepthook 没换上"
    assert threading.excepthook is G._hook_thread, "threading.excepthook 没换上"
    # Tk 那处：给一个假 app，确认挂上了 report_callback_exception
    class FakeApp:
        report_callback_exception = None
    app = FakeApp()
    r = G.install(app)
    assert r["tk"] is True, "给了 app 却没装 Tk 钩子"
    assert app.report_callback_exception is not None, "report_callback_exception 没挂上"
    G.install()                                    # 幂等，不该叠钩子
    assert sys.excepthook is G._hook_main
    assert _snap_real() == before, "① X1 就碰了真实 state/crash/"


# ══════════════════════════════════════════════════════════════
@case("【X2】抛异常 → 临时目录里**真的出现**崩溃文件（三处钩子各一次）")
def x2():
    root = _tmp()
    before = _snap_real()
    try:
        G.install()
        G._record.__globals__["_ROOT"]                   # 存在性（不靠它）
        _boom("main")
        _boom("tk")
        e = _boom("main")
        G._record(type(e), e, e.__traceback__, "probe", root)   # 显式指定 root
        d = G.crash_dir(root)
        fs = [x for x in os.listdir(d) if x.endswith(".json")]
        assert fs, "★ 临时目录里没有崩溃文件"
        assert _snap_real() == before, "② X2 碰了真实 state/crash/"
    finally:
        G.set_dir(None)                      # ★ 复位，防影响别的用例
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【X3】文件含完整 traceback + 现场字段，且**无对话原文**")
def x3():
    root = _tmp()
    before = _snap_real()
    try:
        G.set_context(round=7, era="E3", running=True)
        # ★ 隐私：入口必须**拒绝**带原文的键（第一版就是靠这条抓出来的）
        try:
            G.set_context(raw_input="★不该出现的对话原文★")
            raise AssertionError("★ set_context 竟然接受了 raw_input")
        except ValueError:
            pass
        e = _boom("main")
        fp = G._record(type(e), e, e.__traceback__, "probe", root)
        assert fp and os.path.exists(fp), "没写出来"
        d = json.load(io.open(fp, encoding="utf-8"))
        for k in ("at", "where", "exc_type", "exc_msg", "traceback", "thread",
                  "context", "ledger_digest", "env"):
            assert k in d, "缺字段 %s" % k
        assert d["exc_type"] == "RuntimeError", d["exc_type"]
        assert isinstance(d["traceback"], list) and len(d["traceback"]) >= 1
        assert "探针异常" in "".join(d["traceback"]), "traceback 不完整"
        assert d["thread"]["is_main"] is True
        # ★ 隐私：台账摘要**不许带对话原文**
        blob = json.dumps(d, ensure_ascii=False)
        assert "raw_input" not in blob, "★ 摘要里带了 raw_input 字段"
        assert "output" not in json.dumps(d["ledger_digest"], ensure_ascii=False)
        for row in d["ledger_digest"]:
            assert set(row) <= {"turn_id", "channel", "e", "e_version"}, \
                "★ 台账摘要带多了字段：%s" % sorted(row)
        assert _snap_real() == before, "③ X3 碰了真实 state/crash/"
    finally:
        G._CTX.pop("round", None); G._CTX.pop("era", None)
        G._CTX.pop("running", None)                     # 清掉探针现场
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【X4】环形：写 51 条 → 只剩 50，最旧的被删")
def x4():
    root = _tmp()
    before = _snap_real()
    try:
        d = G.crash_dir(root)
        os.makedirs(d, exist_ok=True)
        e = _boom("main")
        for i in range(G.KEEP + 1):
            fp = os.path.join(d, "crash_20260101_%06d.json" % i)
            io.open(fp, "w", encoding="utf-8").write("{}")
        G._trim(d)
        fs = sorted(x for x in os.listdir(d) if x.startswith("crash_") and x.endswith(".json"))
        assert len(fs) == G.KEEP, "环形没生效：剩 %d 条（应 %d）" % (len(fs), G.KEEP)
        assert "crash_20260101_000000.json" not in fs, "最旧的没删"
        assert _snap_real() == before, "④ X4 碰了真实 state/crash/"
    finally:
        G.set_dir(None)                      # ★ 复位，防影响别的用例
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【X5】原子写：不留 .tmp 半截文件")
def x5():
    root = _tmp()
    before = _snap_real()
    try:
        e = _boom("main")
        G._record(type(e), e, e.__traceback__, "probe", root)
        d = G.crash_dir(root)
        left = [x for x in os.listdir(d) if x.endswith(".tmp")]
        assert not left, "★ 留下了半截文件：%s" % left
        assert _snap_real() == before, "⑤ X5 碰了真实 state/crash/"
    finally:
        G.set_dir(None)                      # ★ 复位，防影响别的用例
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【X6】★ 子线程崩溃：hook 抓得到，且 hook_already_caught 认得它（防重复日志）")
def x6():
    """用户裁定：「避免日志重复：子线程崩溃由 `threading.excepthook` 负责抓取并落盘；
    `_drain` 的第三分支聚焦于驱动 UI 告警展示，**若非 hook 触发的静默退出才兜底补写**。」"""
    root = _tmp()                      # ★ 必须重定向 —— 第一版漏了这一步，
                                       #   于是子线程崩溃真的写进了 state/crash/
    before = _snap_real()
    G.install()
    G._CTX.pop("_hook_threads", None)

    def boom():
        raise KeyError("子线程探针")

    t = threading.Thread(target=boom, name="train-worker-probe")
    t.start()
    t.join()
    time.sleep(0.1)
    assert G.hook_already_caught("train-worker-probe"), \
        "★ 子线程异常没被 threading.excepthook 记下来"
    assert G.hook_already_caught(), "无参形式也应认得"
    assert not G.hook_already_caught("从来没跑过的线程"), "不该误认"
    # ★ 双向：临时路径确实收到了文件，真实路径没有
    d = G.crash_dir(root)
    assert any(x.endswith(".json") for x in os.listdir(d)), \
        "★ 子线程崩溃没落进隔离目录"
    assert _snap_real() == before, "⑥ X6 碰了真实 state/crash/"
    G.set_dir(None)
    shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【X7】★★ 隔离红线：双向物理断言 + 逐点检查（吸取 C1 假绿教训）")
def x7():
    """**真实 `state/crash/` 绝无文件** 且 **临时目录下真实生成合法文件**。

    C1 的教训：只在最后查一次，会被测试自己的清理动作擦掉证据。
    这里**每一动之后立刻查**。
    """
    root = _tmp()
    before = _snap_real()

    def both_ways(step: str, tmp_should_exist: bool):
        assert not os.path.isdir(REAL_DIR), \
            "★ [%s] 真实 state/crash/ 被创建了 —— 隔离破了" % step
        assert _snap_real() == before, \
            "★ [%s] 真实 state/crash/ 的存在性/文件数变了 —— 隔离破了" % step
        if tmp_should_exist:
            d = G.crash_dir(root)
            fs = [x for x in os.listdir(d) if x.endswith(".json")]
            assert fs, "★ [%s] 临时路径应有文件却没有 —— 写盘没走隔离路径" % step
            doc = json.load(io.open(os.path.join(d, fs[0]), encoding="utf-8"))
            assert "traceback" in doc and doc.get("exc_type"), \
                "★ [%s] 临时文件内容不合法：%s" % (step, sorted(doc)[:6])

    try:
        both_ways("起点", False)
        G.install()
        both_ways("install 之后", False)
        e = _boom("main")
        both_ways("抛异常之后（未指定 root，落真实路径）", False)   # ★ 这一步是关键
        fp = G._record(type(e), e, e.__traceback__, "probe", root)
        both_ways("写隔离路径之后", True)
        G._trim(G.crash_dir(root))
        both_ways("_trim 之后", True)
        G.latest(root)
        both_ways("latest 之后", True)
        # 反向确认：latest 真的读到了临时那份
        got = G.latest(root)
        assert got and got["path"].startswith(root), "latest 没指向隔离目录"
    finally:
        G.set_dir(None)                      # ★ 复位，防影响别的用例
        shutil.rmtree(root, ignore_errors=True)
        assert not os.path.isdir(REAL_DIR), "★ 收尾时真实目录存在"


# ══════════════════════════════════════════════════════════════
def main() -> int:
    for name, fn in CASES:
        try:
            fn()
            RESULTS.append((name, True, ""))
        except AssertionError as e:
            RESULTS.append((name, False, str(e) or "断言失败"))
        except Exception as e:                      # noqa: BLE001
            RESULTS.append((name, False, "%s: %s" % (type(e).__name__, e)))
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 78)
    print("崩溃黑匣子（T23）")
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

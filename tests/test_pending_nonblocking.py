# -*- coding: utf-8 -*-
"""待批面板「不阻塞训练」的证明（第 4 步）。

用户要求（原话）：
    「确认界面的点击操作只触发 charter.decide_view / charter.decide_report
      事件写入，不直接阻塞训练线程。」
    「做完后发我 diff 与界面在训练中的非阻塞测试证明。」

证明分三层：
  N1 结构 —— `charter.py` 里**没有任何**线程/阻塞原语
  N2 结构 —— 面板的批准/驳回处理函数只调 `charter.decide_*`，不碰 `self.control`
  N3 运行 —— **真的在训练跑着的时候**并发调用 decide，测三件事：
             ① 训练轮次照常跑完（不受影响）
             ② `TrainingControl` 的 paused/stopped 全程未变
             ③ 每次 decide 调用耗时极短（无阻塞）

⚠️ 全程在**临时 EGO_ROOT** 里跑（复制一份项目骨架），绝不碰真实数据。
⚠️ 离线训练（use_api=False），不花 API。运行请带 `-B`。
"""
from __future__ import annotations

import ast
import io
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time

_ROOT_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="ego_nonblock_")
os.environ["EGO_ROOT"] = _TMP
sys.path.insert(0, os.path.join(_ROOT_PROJ, "engine"))

RESULTS: list[tuple[str, bool, str]] = []
CASES: list[tuple[str, object]] = []

_OPEN = ["CHARTER-01", "CHARTER-02", "CHARTER-05", "CHARTER-06",
         "CHARTER-07", "CHARTER-08"]


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


def _setup_project() -> None:
    """复制一份最小项目骨架到临时目录。"""
    for d in ("rules", "corpus", "state"):
        src = os.path.join(_ROOT_PROJ, d)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(_TMP, d), dirs_exist_ok=True)
    # 语料：load_corpus() 从 <ROOT>/tests 里 import corpus_probe
    os.makedirs(os.path.join(_TMP, "tests"), exist_ok=True)
    shutil.copy2(os.path.join(_ROOT_PROJ, "tests", "corpus_probe.py"),
                 os.path.join(_TMP, "tests", "corpus_probe.py"))
    # 训练台账清空，让轮次计数干净
    td = os.path.join(_TMP, "state", "train")
    if os.path.isdir(td):
        for f in os.listdir(td):
            p = os.path.join(td, f)
            if os.path.isfile(p):
                os.remove(p)
    # 总纲领注册表
    import charter as C
    os.makedirs(os.path.dirname(C.CHARTER_FILE), exist_ok=True)
    rows = [{"id": i, "title": "标题-%s" % i, "kind": "测试", "text": "正文-%s" % i,
             "verbatim": "原话", "source": "测试", "constrains": "测试",
             "admin_readable": True, "added_at": "2026-10-01"} for i in _OPEN]
    io.open(C.CHARTER_FILE, "w", encoding="utf-8").write(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def _ledger_lines() -> int:
    p = os.path.join(_TMP, "state", "train", "ledger.jsonl")
    if not os.path.exists(p):
        return 0
    return sum(1 for l in io.open(p, encoding="utf-8") if l.strip())


def _clear_events() -> None:
    import charter as C
    if os.path.exists(C.ESCALATION):
        os.remove(C.ESCALATION)


# ══════════════════════════════════════════════════════════════
# N1：charter 里没有任何线程/阻塞原语
# ══════════════════════════════════════════════════════════════
@case("【N1】charter.py 无任何线程/阻塞原语（结构证明）")
def n1():
    src = io.open(os.path.join(_ROOT_PROJ, "engine", "charter.py"),
                  encoding="utf-8").read()
    tree = ast.parse(src)

    # ① 不得导入并发相关模块
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
    danger = mods & {"threading", "asyncio", "multiprocessing", "queue",
                     "concurrent", "signal", "socket"}
    assert not danger, "★ charter.py 导入了并发相关模块：%s" % danger

    # ② 不得调用阻塞原语。
    #    ⚠️ 判据必须走 AST，而且 `join` 要**区分基座**：
    #       `os.path.join()` 与 `'、'.join()` 是拼字符串，不是 Thread.join()。
    #       第一版直接搜 `".join("` → 被字符串拼接误报；
    #       第二版按属性名判 → 被 `os.path.join` 误报。所以这里白名单化基座。
    BLOCK_ATTRS = {"wait", "acquire", "release", "notify", "wait_for",
                   "run_until_complete", "sleep", "recv", "accept"}
    SAFE_JOIN_BASES = ("os.path", "str")

    def _blocking_calls(tree):
        out = []
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            if isinstance(f, ast.Attribute):
                base = ast.unparse(f.value)
                if f.attr == "join":
                    # join 只有在**不是**字符串/路径拼接时才算阻塞
                    if base.startswith(SAFE_JOIN_BASES):
                        continue
                    if isinstance(f.value, ast.Constant):    # '、'.join(...)
                        continue
                    out.append("%s.join()" % base)
                elif f.attr in BLOCK_ATTRS:
                    out.append("%s.%s()" % (base, f.attr))
            elif isinstance(f, ast.Name) and f.id in BLOCK_ATTRS:
                out.append("%s()" % f.id)
        return out

    hits = _blocking_calls(tree)
    assert not hits, "★ charter.py 里有阻塞调用：%s" % hits

    # ③ 反向确认这个判据真的在工作：喂它已知的样本
    probe_ok = ("import os\n"
                "def f(x, y):\n"
                "    a = os.path.join(x, y)\n"
                "    b = '、'.join([x, y])\n"
                "    return a + b\n")
    probe_bad = ("import time\n"
                 "def g(t):\n"
                 "    t.join()\n"
                 "    time.sleep(1)\n")
    assert _blocking_calls(ast.parse(probe_ok)) == [], \
        "判据把字符串/路径拼接误判成阻塞了：%s" % _blocking_calls(ast.parse(probe_ok))
    assert set(_blocking_calls(ast.parse(probe_bad))) == {"t.join()", "time.sleep()"}, \
        "判据抓不到真正的阻塞：%s" % _blocking_calls(ast.parse(probe_bad))


# ══════════════════════════════════════════════════════════════
# N2：面板的处理函数不碰训练控制
# ══════════════════════════════════════════════════════════════
@case("【N2】面板处理函数只调 charter.decide_*，不碰 self.control（结构证明）")
def n2():
    src = io.open(os.path.join(_ROOT_PROJ, "engine", "training_studio.py"),
                  encoding="utf-8").read()
    tree = ast.parse(src)
    # 找出面板相关的处理函数
    names = ("_pending_view_buttons", "_pending_report_buttons",
             "_refresh_pending", "_pending_card", "_build_pending")
    found = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name in names:
            found[n.name] = ast.get_source_segment(src, n)
    for nm in names:
        assert nm in found, "找不到 %s" % nm
    body = "\n".join(found.values())
    # ① 必须调 decide_view / decide_report
    assert "decide_view" in body, "面板没有调用 decide_view"
    assert "decide_report" in body, "面板没有调用 decide_report"
    # ② 不得碰训练控制、线程、队列
    for bad in ("self.control", "TrainingControl", "self.worker", "self.q",
                "threading", ".pause(", ".resume(", ".stop()", "self.root.after"):
        assert bad not in body, "★ 面板里出现 %s —— 可能阻塞或干扰训练" % bad
    # ③ 不得有模态弹窗（用户明令：别用弹出式模态窗口）
    #    ⚠️ 必须按**调用形态**判，不能搜字面名字：
    #       变异测试里用别名 `from tkinter import messagebox as _mb; _mb.askyesno(...)`
    #       就绕过了字符串检查。这里改成 AST：只看属性名，不看基座叫什么。
    MODAL = {"askyesno", "askokcancel", "askquestion", "askretrycancel",
             "askyesnocancel", "showerror", "showinfo", "showwarning"}
    modal_hits = []
    for n in ast.walk(ast.parse(body)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr in MODAL:
                modal_hits.append(ast.unparse(n.func))
            elif ast.unparse(n.func.value) in ("simpledialog", "messagebox"):
                modal_hits.append(ast.unparse(n.func))
    assert not modal_hits, "★ 面板用了模态弹窗：%s" % modal_hits

    # 反向确认这个判据真的在工作（含别名写法）
    probe = ("from tkinter import messagebox as _mb\n"
             "def h():\n"
             "    _mb.askyesno('x', 'y')\n")
    ph = [ast.unparse(n.func) for n in ast.walk(ast.parse(probe))
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
          and n.func.attr in MODAL]
    assert ph == ["_mb.askyesno"], "判据抓不到别名写法的模态弹窗：%s" % ph


# ══════════════════════════════════════════════════════════════
# N3：训练**跑着的时候**并发 decide，训练不受影响
# ══════════════════════════════════════════════════════════════
@case("【N3】训练进行中并发 decide：轮次照跑、控制状态不变、调用不阻塞")
def n3():
    import charter as C
    from train import Trainer, TrainingControl

    _clear_events()
    # 先造 24 张待批工单，供训练期间并发批准
    aids = []
    for i in range(24):
        aid = "A-NB-%02d" % i
        C.note_anomaly(aid, "mechanical", 5 + i, 30, "并发测试用证据", "反复")
        C.request_view(aid, "并发测试", ["CHARTER-01"], "")
        aids.append(aid)

    control = TrainingControl()
    trainer = Trainer(use_api=False, use_think=False, gate_perception=False)
    box: dict = {}

    def work():
        try:
            box["r"] = trainer.run(rounds=3, session_len=10, source="corpus",
                                   tutor=False, control=control)
        except Exception as e:                     # noqa: BLE001
            box["err"] = repr(e)

    before = _ledger_lines()
    th = threading.Thread(target=work, daemon=True)
    th.start()

    lats: list[float] = []
    decided = 0
    paused_seen, stopped_seen = [], []
    for aid in aids:
        if not th.is_alive():
            break
        t0 = time.time()
        C.decide_view(aid, approved=True, granted_ids=["CHARTER-01"], note="并发")
        lats.append(time.time() - t0)
        decided += 1
        paused_seen.append(control.paused)
        stopped_seen.append(control.stopped)
        time.sleep(0.03)

    th.join(timeout=180)
    assert not th.is_alive(), "训练线程没有结束 —— 可能被 decide 卡住了"

    # ① 训练照常跑完
    assert "err" not in box, "训练抛异常：%s" % box.get("err")
    added = _ledger_lines() - before
    assert added == 90, "训练轮次应为 3×3×10=90，实际 %d —— 并发 decide 干扰了训练" % added
    # ② 控制状态全程未变
    assert not any(paused_seen), "训练期间 control.paused 变成了 True"
    assert not any(stopped_seen), "训练期间 control.stopped 变成了 True"
    assert control.paused is False and control.stopped is False, "训练结束后控制状态被改"
    # ③ 每次 decide 都不阻塞
    assert decided >= 5, "并发样本太少（只做了 %d 次），证明力不足" % decided
    mx = max(lats)
    assert mx < 0.5, "★ 有一次 decide 耗时 %.3f 秒 —— 存在阻塞" % mx
    # ④ 事件真的写进去了
    evs = [json.loads(l) for l in io.open(C.ESCALATION, encoding="utf-8") if l.strip()]
    decs = [e for e in evs if e.get("ev") == "view_dec"]
    assert len(decs) == decided, \
        "写入的 view_dec 应为 %d 条，实际 %d" % (decided, len(decs))
    assert all(e.get("by") == "用户" for e in decs), "授权事件必须记为用户产生"


# ══════════════════════════════════════════════════════════════
def main() -> int:
    _setup_project()
    for name, fn in CASES:
        _run_one(name, fn)
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 78)
    print("待批面板：不阻塞训练的三层证明")
    print("=" * 78)
    for name, passed, msg in RESULTS:
        print("  [%s] %s" % ("PASS" if passed else "FAIL", name))
        if not passed:
            print("         %s" % msg)
    print("-" * 78)
    print("结果: %d 通过 / %d 失败 / 共 %d"
          % (ok, len(RESULTS) - ok, len(RESULTS)))
    shutil.rmtree(_TMP, ignore_errors=True)
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())

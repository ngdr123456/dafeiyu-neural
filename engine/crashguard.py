# -*- coding: utf-8 -*-
"""崩溃黑匣子：三处全局钩子 + 环形落盘（T23）。

用户裁定（2026-10-02）
────────────────────────────────────────────────────────────
> 「**三处钩子全覆盖（必须全部落地）**：
>    `sys.excepthook`（主线程）；`threading.excepthook`（后台训练线程）；
>    `Tk.report_callback_exception`（Tkinter 事件回调，最容易静默吞异常的重灾区）。
>  **守住界面铁律**：坚决不新增任何按钮或控件，崩溃感知仅在重启时通过已有
>    alert bar / 提示条进行**纯文本复用提示**；
>  **环形落盘与现场保留**：`state/crash/` 独立目录、单文件 JSON、**上限 50 条**
>    环形滚动、包含 traceback 与当时上下文（轮次、era 等）。
>  **纯净与零依赖**：严格使用 Python 标准库，不引入 logging 第三方框架；
>  **隐私合规**：崩溃快照台账摘要**严格剔除对话原文**。」

排查结论（为什么三处缺一不可）
────────────────────────────────────────────────────────────
    ① windowed exe 下未捕获异常 → **退出码 1，无弹窗、无输出、无痕迹**（实测）
    ② 训练跑在 `threading.Thread(daemon=True)` 里 ⇒ `sys.excepthook` **抓不到**
    ③ 子线程死了 ⇒ `_drain` 停止重排 ⇒ **界面静默卡死**（比闪退更隐蔽）
    ④ 全项目**零**钩子、**零** logging ⇒ 没有可复用设施，本模块自建

⚠️ 本模块**只写自己目录下的文件**，不 import 任何项目内业务模块。
"""
from __future__ import annotations

import io
import json
import os
import sys
import threading
import time
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)

KEEP = 50                    # ★ 环形上限（用户裁定）

#: 已装过就把原钩子留一份，**幂等**（重复 install 不叠钩子）
_ORIG = {}
_CTX = {}                    # 现场信息，由主程序喂（轮次 / era / 是否在跑）


#: ★ 进程内重定向（测试隔离用）。生产不设 → 写真实 state/crash/。
_OVERRIDE: str | None = None

#: ★ 隐私黑名单：这些键**不许**进崩溃日志（用户裁定「严格剔除对话原文」）。
#:   防线放在**入口**而不是靠调用方自觉 —— 实测中 `set_context(raw_input=...)`
#:   确实把对话原文带进去了（X3 抓到）。
_FORBIDDEN = ("raw_input", "output", "said", "text", "input", "reply",
              "markers", "marker_evidence", "transcript", "history")


def set_dir(path: str | None) -> None:
    """★ 重定向崩溃目录（**测试隔离的唯一入口**）。

    为什么需要它：三处钩子在生产里就该写真实 `state/crash/`，
    而测试要触发钩子、又不能碰真实目录 —— 没有这个入口，
    测试要么不测钩子（假绿），要么污染真实环境。
    """
    global _OVERRIDE
    _OVERRIDE = path


def crash_dir(root: str | None = None) -> str:
    if root:
        return os.path.join(root, "state", "crash")
    if _OVERRIDE:
        return _OVERRIDE
    if os.environ.get("EGO_CRASH_DIR"):
        return os.environ["EGO_CRASH_DIR"]
    return os.path.join(os.environ.get("EGO_ROOT") or _ROOT, "state", "crash")


def set_context(**kw) -> None:
    """登记现场（轮次 / topic_id / era / running 等）。

    ⚠️ **不许放对话原文** —— 崩溃日志可能被外发排查。
    """
    bad = [k for k in kw if k.lower() in _FORBIDDEN]
    if bad:
        raise ValueError(
            "★ 这些键不许进崩溃日志（可能含对话原文）：%s\n"
            "  用户裁定：「崩溃快照台账摘要**严格剔除对话原文**」—— "
            "防线放在入口，不靠调用方自觉。" % bad)
    _CTX.update(kw)


def _ledger_digest(n: int = 5) -> list:
    """最近 n 轮的**摘要**：只留 turn_id / channel / e。

    ★ 用户裁定：「台账摘要**严格剔除对话原文**」——
      所以这里**不读 raw_input / output / markers**，只读三个数值/短字段。
    """
    out = []
    for name in ("ledger.jsonl", os.path.join("train", "ledger.jsonl")):
        p = os.path.join(os.environ.get("EGO_ROOT") or _ROOT, "state", name)
        if not os.path.exists(p):
            continue
        try:
            lines = [l for l in io.open(p, encoding="utf-8") if l.strip()][-n:]
            for l in lines:
                r = json.loads(l)
                m = r.get("mech") or {}
                out.append({"turn_id": r.get("turn_id"), "channel": r.get("channel"),
                            "e": m.get("e"), "e_version": m.get("e_version")})
            break
        except Exception:                          # noqa: BLE001
            continue
    return out


def _record(exc_type, exc, tb, where: str, root: str | None = None) -> str | None:
    """写一份崩溃记录。返回文件路径（失败返回 None —— **绝不因记录失败再抛**）。"""
    try:
        d = crash_dir(root)
        os.makedirs(d, exist_ok=True)
        th = threading.current_thread()
        doc = {
            "_note": "崩溃黑匣子。台账摘要**已剔除对话原文**（隐私）。",
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "where": where,                     # main / thread:<name> / tk-callback / watchdog
            "exc_type": getattr(exc_type, "__name__", str(exc_type)),
            "exc_msg": str(exc)[:2000],
            "traceback": traceback.format_exception(exc_type, exc, tb),
            "thread": {"name": th.name, "ident": th.ident,
                       "is_main": th is threading.main_thread(),
                       "daemon": th.daemon},
            "context": dict(_CTX),
            "ledger_digest": _ledger_digest(),
            "env": {"python": sys.version.split()[0],
                    "frozen": bool(getattr(sys, "frozen", False)),
                    "executable": os.path.basename(sys.executable),
                    "platform": sys.platform},
        }
        fn = "crash_%s_%d.json" % (time.strftime("%Y%m%d_%H%M%S"), os.getpid())
        fp = os.path.join(d, fn)
        i = 1
        while os.path.exists(fp):               # 同秒多次崩溃不互相覆盖
            fp = os.path.join(d, fn[:-5] + "_%d.json" % i)
            i += 1
        # ★ 双保险：落盘前再扫一遍 context（防有人直接改 _CTX 绕过 set_context）
        leaked = [k for k in doc["context"] if k.lower() in _FORBIDDEN]
        if leaked:
            doc["context"] = {k: v for k, v in doc["context"].items()
                              if k.lower() not in _FORBIDDEN}
            doc["_privacy_stripped"] = leaked
        tmp = fp + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, fp)                     # ★ 原子
        _trim(d)
        return fp
    except Exception:                           # noqa: BLE001
        return None


def _trim(d: str) -> None:
    """环形：只留最近 KEEP 条。"""
    try:
        fs = sorted(x for x in os.listdir(d)
                    if x.startswith("crash_") and x.endswith(".json"))
        for x in fs[:-KEEP] if len(fs) > KEEP else []:
            try:
                os.remove(os.path.join(d, x))
            except Exception:                   # noqa: BLE001
                pass
    except Exception:                           # noqa: BLE001
        pass


# ── 三处钩子 ──────────────────────────────────────────────────
def _hook_main(exc_type, exc, tb) -> None:
    _record(exc_type, exc, tb, "main")
    if _ORIG.get("main"):
        try:
            _ORIG["main"](exc_type, exc, tb)
        except Exception:                       # noqa: BLE001
            pass


def _hook_thread(args) -> None:
    """★ 训练线程跑在这里 —— `sys.excepthook` **抓不到**子线程异常。"""
    _record(args.exc_type, args.exc_value, args.exc_traceback,
            "thread:%s" % getattr(args.thread, "name", "?"))
    # 记下"哪个线程死了"，供看门狗判断**是不是 hook 已经抓过**
    _CTX["_hook_threads"] = list(_CTX.get("_hook_threads", [])) + [
        getattr(args.thread, "name", "?")]
    if _ORIG.get("thread"):
        try:
            _ORIG["thread"](args)
        except Exception:                       # noqa: BLE001
            pass


def _hook_tk(self, exc_type, exc, tb) -> None:
    """★ Tk 事件回调（含 `after()` 回调）—— Tk 默认只打 stderr，
    windowed 下 stderr 是黑洞 ⇒ **最容易静默吞异常的地方**。"""
    _record(exc_type, exc, tb, "tk-callback")


def install(app=None) -> dict:
    """装上三处钩子。`app` = Tk 根窗口（给了才装第三处）。**幂等**。"""
    if not _ORIG:
        _ORIG["main"] = sys.excepthook
        _ORIG["thread"] = getattr(threading, "excepthook", None)
    sys.excepthook = _hook_main
    if hasattr(threading, "excepthook"):
        threading.excepthook = _hook_thread
    _ORIG["tk"] = app
    if app is not None:
        app.report_callback_exception = lambda *a: _hook_tk(app, *a)
    return {"main": True, "thread": hasattr(threading, "excepthook"),
            "tk": app is not None}


def hook_already_caught(thread_name: str | None = None) -> bool:
    """看门狗用：**这个线程的死是否已经被 hook 抓过？**

    用户裁定：「避免日志重复：子线程崩溃由 `threading.excepthook` 负责抓取并落盘；
    `_drain` 的第三分支聚焦于检测到异常中断后驱动 UI 告警展示，
    **若非 hook 触发的静默退出才兜底补写**，避免同一事故刷出两份日志。」
    """
    got = _CTX.get("_hook_threads") or []
    if thread_name is None:
        return bool(got)
    return thread_name in got


def latest(root: str | None = None) -> dict | None:
    """最近一份崩溃记录（供启动时在 alert bar 提示）。"""
    d = crash_dir(root)
    if not os.path.isdir(d):
        return None
    try:
        fs = sorted(x for x in os.listdir(d)
                    if x.startswith("crash_") and x.endswith(".json"))
        if not fs:
            return None
        p = os.path.join(d, fs[-1])
        return {"path": p, "name": fs[-1],
                "doc": json.load(io.open(p, encoding="utf-8"))}
    except Exception:                           # noqa: BLE001
        return None

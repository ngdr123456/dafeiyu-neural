# -*- coding: utf-8 -*-
"""验收循环：版本提交 → 管理员验收 → 冲突计数 → **超 2 次立即停止全部任务并报告**。

用户明令（本模块存在的唯一理由）
────────────────────────────────────────────────────────────
> 「管理员负责验收你上传的每个版本，如果你和管理员意见冲突并超过 2 次单循环，
>   那请及时停止所有任务告知我发生了什么。」

所以有三件事必须是真的，不能只是写着：
  ① **冲突要计数**，而且是**同一个循环内**累计
  ② **超过 2 次**（即第 3 次）→ 触发**硬停止**
  ③ 停止不是"记一笔"，而是**真的停下所有任务并把发生了什么报给用户**
     —— 停止标志落盘，后续任何动作先读它；已停就不许再动

为什么把它做成一个落盘的开关而不是我的自觉：
    自觉会在"我觉得这次不算冲突"的时候失效。落盘的开关不会。
    本项目已有教训：把纪律寄托在"记得"，不如寄托在"做不到"。
"""
from __future__ import annotations

import io
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包成 exe 后 `__file__` 指向解包出的临时目录 —— 于是 rules/corpus 找不到，
# 而且**台账会写进临时目录、退出就丢**。所以允许用 EGO_ROOT 指定项目根，
# 由启动器（exe）在导入任何引擎模块之前设置。
# 不设 EGO_ROOT 时行为与从前完全一致（源码运行时就是这个分支）。
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

STOP_DIR = os.path.join(_ROOT, "state", "review")
STOP_FLAG = os.path.join(STOP_DIR, "STOP.json")
LOG = os.path.join(STOP_DIR, "conflicts.jsonl")
VERSIONS = os.path.join(STOP_DIR, "versions.jsonl")

MAX_CONFLICTS = 2          # 用户明令：超过 2 次即停（第 3 次触发）


def _ensure() -> None:
    os.makedirs(STOP_DIR, exist_ok=True)


def _read_jsonl(p: str) -> list[dict]:
    out = []
    if not os.path.exists(p):
        return out
    for line in io.open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:                      # noqa: BLE001
                pass
    return out


# ------------------------------------------------------------------ 停止开关

def is_stopped() -> dict | None:
    """已停止则返回停止记录，否则 None。**任何任务开工前都该先问一次。**"""
    if not os.path.exists(STOP_FLAG):
        return None
    try:
        return json.load(io.open(STOP_FLAG, encoding="utf-8"))
    except Exception:                              # noqa: BLE001
        return {"reason": "停止标志存在但读不出内容"}


def _hard_stop(loop: str, conflicts: int, detail: list[dict]) -> dict:
    _ensure()
    rec = {"stopped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "loop": loop, "conflicts": conflicts, "limit": MAX_CONFLICTS,
           "reason": "同一循环内与管理员意见冲突 %d 次，超过上限 %d 次"
                     % (conflicts, MAX_CONFLICTS),
           "what_happened": detail[-3:],
           "instruction": "用户明令：立即停止全部任务并告知发生了什么。"
                          "解除需要用户本人明确指示。",
           "resume_requires": "user_explicit"}
    io.open(STOP_FLAG, "w", encoding="utf-8").write(
        json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
    return rec


def resume(user_said: str) -> dict:
    """解除停止。**只有用户本人能解除** —— 传入的必须是用户的原话。"""
    if not (user_said or "").strip():
        raise ValueError("解除停止必须记录用户的原话 —— 不写理由的解除，后人无法判断该不该解")
    rec = {"resumed_at": time.strftime("%Y-%m-%d %H:%M:%S"), "user_said": user_said}
    if os.path.exists(STOP_FLAG):
        os.remove(STOP_FLAG)
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "resume", **rec}, ensure_ascii=False) + "\n")
    return rec


# ------------------------------------------------------------------ 版本与冲突

def submit(version: str, summary: str, checks: dict,
           files: list[str] | None = None) -> dict:
    """我提交一个版本。**先查停止开关。**"""
    st = is_stopped()
    if st:
        return {"ok": False, "stopped": True, "stop": st,
                "msg": "已处于停止状态，不许提交新版本。需用户明确指示才能解除。"}
    _ensure()
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "version": version,
           "summary": summary, "checks": checks, "files": files or [],
           "loop": current_loop()}
    with io.open(VERSIONS, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"ok": True, **rec}


def current_loop() -> str:
    """当前循环编号。同一循环 = 一次提交到验收之间。"""
    vs = _read_jsonl(VERSIONS)
    return "L%d" % (len(vs) + 1)


def conflicts_in_loop(loop: str | None = None) -> int:
    lp = loop or ("L%d" % len(_read_jsonl(VERSIONS)))
    return sum(1 for c in _read_jsonl(LOG)
               if c.get("kind") == "conflict" and c.get("loop") == lp)


def record_conflict(loop: str, version: str, mine: str, admin: str,
                    resolution: str = "") -> dict:
    """记一次冲突。**冲突定义为：对同一件事，我与管理员结论相反且各自给了依据。**

    什么不算冲突（否则计数会虚高，然后我们会为了躲计数而假装同意）：
      · 管理员提意见、我采纳 → 那是协作，不是冲突
      · 我补充了它没看到的信息、它接受 → 也不是冲突
      · 单纯措辞不同、结论一致 → 不是冲突
    """
    _ensure()
    n = conflicts_in_loop(loop) + 1
    rec = {"kind": "conflict", "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
           "loop": loop, "version": version, "n_in_loop": n,
           "mine": mine[:300], "admin": admin[:300], "resolution": resolution[:200]}
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if n > MAX_CONFLICTS:
        stop = _hard_stop(loop, n, [c for c in _read_jsonl(LOG)
                                    if c.get("kind") == "conflict"])
        return {"recorded": rec, "STOPPED": True, "stop": stop}
    return {"recorded": rec, "n_in_loop": n,
            "remaining": max(0, MAX_CONFLICTS - n)}


def status() -> dict:
    st = is_stopped()
    vs = _read_jsonl(VERSIONS)
    loop = "L%d" % (len(vs) + 1)
    n = conflicts_in_loop(loop)
    return {"stopped": bool(st), "stop": st, "versions": len(vs),
            "loop": loop, "conflicts_in_loop": n,
            "limit": MAX_CONFLICTS,
            "remaining": max(0, MAX_CONFLICTS - n),
            "log_tail": _read_jsonl(LOG)[-6:]}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="验收循环与停止开关")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--resume", default=None, help="用户原话（只有用户能解除）")
    a = ap.parse_args()
    if a.resume is not None:
        print(json.dumps(resume(a.resume), ensure_ascii=False, indent=2))
        return 0
    s = status()
    print("=" * 70)
    print("验收循环状态")
    print("=" * 70)
    print("停止开关：%s" % ("**已停止**" if s["stopped"] else "未触发"))
    if s["stopped"]:
        print("  停止于：%s" % s["stop"].get("stopped_at"))
        print("  原因：%s" % s["stop"].get("reason"))
        print("  解除需要：用户本人明确指示")
    print("已提交版本：%d｜当前循环：%s" % (s["versions"], s["loop"]))
    print("本循环冲突：%d / %d（还能冲突 %d 次；第 %d 次即触发停止）"
          % (s["conflicts_in_loop"], s["limit"], s["remaining"], s["limit"] + 1))
    if s["log_tail"]:
        print("\n最近记录：")
        for r in s["log_tail"]:
            print("  · %s" % json.dumps(r, ensure_ascii=False)[:110])
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

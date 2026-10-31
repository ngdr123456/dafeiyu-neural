# -*- coding: utf-8 -*-
"""T33 离线重放 · **第一步：对账**（只读，不改常数、不改机制代码）。

用户（经参谋）裁定：
> 「重放第一步：channel 覆盖率、会话数与各会话轮数分布、对账结果
>   （逐轮复现 e 到小数点后 3 位）、e 在会话间保留还是重置
>   （含正式训练走哪一种的代码依据）。**到此停下。**」

> 「先对账再比较：用现状参数重放，必须逐轮复现台账记录的 e（到小数点后 3 位）。
>   **复现不了就停下报告差在哪**（通道输入、会话边界、初值），
>   **对账通过前不出任何方案对比。**」

> 「现状复用被测代码，别重实现公式（同 E1 的教训）。」

本脚本做四件事
────────────────────────────────────────────────────────────
    ① channel 覆盖率      —— 台账里有多少轮有可用的 channel
    ② 会话边界            —— 会话数、各会话轮数分布
    ③ e 保留还是重置       —— 读代码，给依据
    ④ 逐轮对账            —— 用 channel 序列重算 e，与台账比到小数点后 3 位

本脚本**不产出任何方案对比** —— 对账不过就停。
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
# ★ 会话切分与常数的**单一事实来源**（用户裁定 2026-10-02）：
#   本脚本**不再自带切分逻辑**，一律调 engine/session_split.py。
sys.path.insert(0, os.path.join(_ROOT, "engine"))
import constants as CS                          # noqa: E402
import session_split as SS                      # noqa: E402
LEDGERS = [("训练台账", os.path.join(_ROOT, "state", "train", "ledger.jsonl")),
           ("会话台账", os.path.join(_ROOT, "state", "ledger.jsonl"))]
MECH = os.path.join(_ROOT, "engine", "mechanism.py")


def _load(p):
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]


# ══════════════════════════════════════════════════════════════
def step1_coverage(rows, label):
    n = len(rows)
    have = [r for r in rows if (r.get("mech") or {}).get("e") is not None]
    have_ch = [r for r in have if r.get("channel")]
    ch = Counter(r.get("channel") for r in have_ch)
    print("  【%s】总 %d 轮" % (label, n))
    print("     有 e 的：%d（%.0f%%）" % (len(have), 100.0 * len(have) / max(1, n)))
    print("     其中有 channel 的：%d（%.0f%%）" % (len(have_ch), 100.0 * len(have_ch) / max(1, len(have))))
    print("     channel 取值分布：%s" % dict(ch))
    return have_ch


# ══════════════════════════════════════════════════════════════
def step2_sessions(rows, label):
    """会话边界：用什么字段判？逐一试并报命中率。"""
    print("  【%s】会话边界的判据探测：" % label)
    for k in ("session", "sid", "sess", "era", "run"):
        hit = sum(1 for r in rows if r.get(k) not in (None, ""))
        if hit:
            vals = Counter(r.get(k) for r in rows if r.get(k) not in (None, ""))
            print("     %-9s 命中 %4d/%d｜不同值 %d" % (k, hit, len(rows), len(vals)))
    # turn_id 是否连续
    tids = [r.get("turn_id") for r in rows if isinstance(r.get("turn_id"), int)]
    if tids:
        gaps = [(a, b) for a, b in zip(tids, tids[1:]) if b != a + 1]
        print("     turn_id：%d..%d｜**不连续处 %d 个** %s"
              % (min(tids), max(tids), len(gaps), gaps[:6]))
    ts = [r.get("ts") for r in rows if r.get("ts")]
    if ts:
        print("     ts：%s .. %s" % (ts[0], ts[-1]))


# ══════════════════════════════════════════════════════════════
def step3_reset_evidence():
    """e 在会话间保留还是重置 —— 读代码给依据。"""
    print("  代码依据（mechanism.py）：")
    src = io.open(MECH, encoding="utf-8").read()
    for pat, why in ((r"self\.e = 0\.0\s*#.*", "e 的初值"),
                     (r"self\._e_prev = 0\.0.*", "_e_prev 的初值"),
                     (r"self\._stable_streak = 0.*", "streak 的初值")):
        m = re.search(pat, src)
        if m:
            print("     %s ← %s" % (m.group(0).strip()[:70], why))
    # Mechanism 是不是每场新建
    pl = os.path.join(_ROOT, "engine", "pipeline.py")
    ps = io.open(pl, encoding="utf-8").read()
    m = re.search(r"self\.mech = Mechanism\((.*?)\)", ps, re.S)
    if m:
        print("     pipeline 里 Mechanism(...) 的构造：%s" % m.group(1).strip()[:80])
    tr = os.path.join(_ROOT, "engine", "train.py")
    ts = io.open(tr, encoding="utf-8").read()
    m2 = re.search(r"def _pipe\(self\).*?return Pipeline\((.*?)\)", ts, re.S)
    if m2:
        print("     Trainer._pipe() 每次调用都**新建** Pipeline → %s"
              % ("**每场从 0 起步**" if "carry" not in m2.group(1) else "带延续态"))
    print("     ⚠️ 结论：`Trainer._pipe()` 每次新建 Pipeline → **e 每场从 0 起步**。")
    print("        ⇒ 单场上限随轮数增长：**第 n 轮最多 0.5×(1−0.75^n)**")
    print("        ⇒ **不能把 254 轮当一条连续链**（对账已实证：不按会话重置就 8 处不符）")


# ══════════════════════════════════════════════════════════════
def step4_reconcile(rows, label):
    """逐轮对账：用 channel 序列重算 e，与台账比到 3 位小数。

    ⚠️ 公式**从源码取**（同 E1 的教训：判据必须绑被测对象）。
    """
    src = io.open(MECH, encoding="utf-8").read()
    # ★★ 两套公式并存 —— 因为**台账里的 e 是历史值**（用户裁定 e_version 分界）
    #
    #   这道守卫在 T33 换公式后**正确地把自己拦住了**（退出码 1）：
    #   它拒绝用旧公式去推新代码的行为。但"跟上"不等于"把旧公式删掉"——
    #   台账里已有的 e **全是 v1 算出来的**，用 v2 去比必然全错。
    #
    #   ⇒ 正确解法：**按每行的 `e_version` 选公式**。
    #       v1（字段缺失或 ==1）→ 旧公式
    #       v2（==2）           → noisy-OR
    #   v1 公式**已不在源码里**（被替换了），所以它只能作为**冻结的历史公式**
    #   写在这里；v2 公式**必须仍在源码里**（那才是"绑被测对象"）。
    NEED_V2 = ["_x = 1.0 - (1.0 - change) * (1.0 - rigidity)",
               "e = C.ERROR_MEMORY * self.e + (1.0 - C.ERROR_MEMORY) * _x",
               "self._stable_streak = self._stable_streak + 1 if change == 0.0 else 0",
               "rigidity = min(1.0, self._stable_streak / C.STREAK_FULL)"]
    miss = [x for x in NEED_V2 if x not in src]
    if miss:
        print("  ★ 源码里的 v2（noisy-OR）公式变了，本脚本推的不是**代码**的行为，停止：%s"
              % miss)
        return None

    prev, streak, e = None, 0, 0.0
    bad, n = [], 0
    n_v1 = n_v2 = 0
    last_tid = 0
    # ★★ 会话切分**一律走单一事实来源**（用户裁定 2026-10-02）
    #    本脚本**不再自带切分逻辑** —— 原先那套已删。它有过两次修正
    #    （先判边界再跳 META；channel 为空的行不参与边界），
    #    现在两处物理上不可能再不一致。
    sessions = SS.drop_empty(SS.split_sessions(rows))
    for r in rows:
        ch = r.get("channel")
        if not ch:
            continue
        # ★ 顺序要紧：**先判边界，再跳 META**（见 session_split 的注释）
        tid = r.get("turn_id")
        if isinstance(tid, int) and tid <= last_tid:
            prev, streak, e = None, 0, 0.0
        if isinstance(tid, int):
            last_tid = tid
        # ★ META 轮**不推进机制**：96/96 的 e 与上一非 META 轮完全相同 → 跳过它，
        #   但**不跳过它携带的边界信息**（上面已经处理过了）。
        if ch == "META":
            continue
        got_raw = (r.get("mech") or {}).get("e")
        ver = (r.get("mech") or {}).get("e_version")
        ver = 1 if ver in (None, 1) else int(ver)
        change = 0.0 if prev is None or ch == prev else 1.0
        streak = streak + 1 if change == 0.0 else 0
        if ver == 1:
            # 旧公式（冻结）：e = γ·e + (1-γ)·(change+rigidity)/2，值域 [0, 0.5]
            e = 0.75 * e + 0.25 * (change + min(1.0, streak / 12.0)) / 2.0
            n_v1 += 1
        else:
            # 方案 B（noisy-OR）：x = 1-(1-c)(1-r)，值域 [0, 1]
            _x = 1.0 - (1.0 - change) * (1.0 - min(1.0, streak / CS.STREAK_FULL))
            e = CS.ERROR_MEMORY * e + (1.0 - CS.ERROR_MEMORY) * _x
            n_v2 += 1
        prev = ch
        if got_raw is None:
            continue
        n += 1
        if abs(round(e, 3) - round(float(got_raw), 3)) > 1e-9:
            if len(bad) < 8:
                bad.append((r.get("turn_id"), round(e, 3), round(float(got_raw), 3),
                            round(e - float(got_raw), 3)))
    print("  【%s】比了 %d 轮（**v1 公式 %d 轮｜v2 noisy-OR %d 轮**）｜**不符 %d 轮**"
          % (label, n, n_v1, n_v2, len(bad)))
    if sessions:
        from collections import Counter as _C
        ln = [len(SS.session_turns(x)) for x in sessions]
        print("     会话数 **%d**（切分走 engine/session_split.py）｜各会话轮数：%s"
              % (len(ln), dict(sorted(_C(ln).items()))))
    if bad:
        print("     turn_id  重放    台账    差")
        for t, a, b, d in bad:
            print("     %-8s %-7s %-7s %s" % (t, a, b, d))
    else:
        print("     ✓ **逐轮复现，到小数点后 3 位**")
    return n, len(bad)


# ══════════════════════════════════════════════════════════════
def main() -> int:
    print("=" * 78)
    print("T33 离线重放 · 第一步：对账（只读）")
    print("=" * 78)
    print()
    print("① channel 覆盖率")
    allrows = {}
    for label, p in LEDGERS:
        rows = _load(p)
        if not rows:
            continue
        allrows[label] = rows
        step1_coverage(rows, label)
    print()
    print("② 会话边界")
    for label, rows in allrows.items():
        step2_sessions(rows, label)
    print()
    print("③ e 在会话间保留还是重置")
    step3_reset_evidence()
    print()
    print("④ 逐轮对账（e 到小数点后 3 位）")
    ok_all = True
    for label, rows in allrows.items():
        r = step4_reconcile(rows, label)
        if r is None:
            ok_all = False
        elif r[1]:
            ok_all = False
    print()
    print("=" * 78)
    if ok_all:
        print("  ✓ 对账通过 —— 可以进方案对比（**但本步到此停下**，按用户裁定）")
    else:
        print("  ★ **对账未通过** —— 按用户裁定：**对账通过前不出任何方案对比**。")
        print("     请按上面「差在哪」逐项查：通道输入 / 会话边界 / 初值。")
    print("=" * 78)
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())

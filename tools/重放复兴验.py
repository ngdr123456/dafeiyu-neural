# -*- coding: utf-8 -*-
"""T33 第二阶段 · 第 6 步：**R1 重放复兴验**（只读真实台账）。

目的
────────────────────────────────────────────────────────────
方案 B（noisy-OR）把 e 的上确界从 0.50 抬到 1.00。本脚本回答：

    在**真实会话序列**下，生长链到底活没活？
    失效几次？平衡化几次？not_grown 几次？折合升几级？

纪律
────────────────────────────────────────────────────────────
    · **只读**：不写任何 state、不改常数
    · **复用被测代码**：e 用真实公式推、A5 判据用真实 `DevLevel`
      （同 E1 的教训：判据必须绑被测对象，不许自己重实现一遍）
    · **按真实会话边界**：turn_id 回退即重置；META 轮不推进机制
      （这两条已由 `tools/重放对账.py` 对账到小数点后 3 位，100% 复现）
    · 训练台账 / 会话台账**分开**，demo **单列**
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import constants as C                          # noqa: E402
import devlevel as D                           # noqa: E402

LEDGERS = [("训练", os.path.join(_ROOT, "state", "train", "ledger.jsonl")),
           ("会话", os.path.join(_ROOT, "state", "ledger.jsonl")),
           ("demo", os.path.join(_ROOT, "state", "ledger_demo.jsonl"))]
MECH = os.path.join(_ROOT, "engine", "mechanism.py")
OUT_JSON = os.path.join(_ROOT, "spec", "重放复兴验.jsonl")


def _formula_ok() -> list:
    """★ 与源码对账 —— 判据绑被测对象，不绑我自己的复述（E1 的教训）。"""
    src = io.open(MECH, encoding="utf-8").read()
    need = ["_x = 1.0 - (1.0 - change) * (1.0 - rigidity)",
            "e = C.ERROR_MEMORY * self.e + (1.0 - C.ERROR_MEMORY) * _x",
            "self._stable_streak = self._stable_streak + 1 if change == 0.0 else 0",
            "rigidity = min(1.0, self._stable_streak / C.STREAK_FULL)"]
    return [x for x in need if x not in src]


def replay(path: str):
    """按真实会话边界重放一条台账，返回统计。"""
    rows = [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]
    # ★ 复用**真实的 DevLevel**（A5 判据、升级逻辑都用它）
    tmpd = tempfile.mkdtemp(prefix="ego_replay_")
    dl = D.DevLevel(os.path.join(tmpd, "devlevel.json"))

    prev, streak, e = None, 0, 0.0
    last_tid = 0
    # ★ 两个分母必须分开报（用户点名的"76 vs 86"）：
    #     「重放轮」= 有 channel 的轮（重放跑得动）
    #     「可比对轮」= 其中**台账记了 e** 的轮（重放对账脚本比的是这个）
    #   差额 = 台账没记 e 的 B 轮。**不是切分差异，是分母差异。**
    st = {"轮": 0, "可比对轮": 0, "会话": 0, "失效": 0, "平衡化": 0, "not_grown": 0,
          "e_max": 0.0, "fail_tension_max": 0.0, "越0.60的轮": 0}
    for r in rows:
        ch = r.get("channel")
        m = r.get("mech") or {}
        tid = r.get("turn_id")
        # ① 会话边界：turn_id 回退 → 重置（**顺序要紧：先判边界再跳 META**）
        if isinstance(tid, int) and tid <= last_tid:
            prev, streak, e = None, 0, 0.0
            st["会话"] += 1
        if isinstance(tid, int):
            last_tid = tid
        # ② META 轮不推进机制
        if ch == "META" or not ch:
            continue
        st["轮"] += 1
        if m.get("e") is not None:
            st["可比对轮"] += 1
        # ③ 真实公式推 e
        change = 0.0 if prev is None or ch == prev else 1.0
        streak = streak + 1 if change == 0.0 else 0
        rigidity = min(1.0, streak / C.STREAK_FULL)
        _x = 1.0 - (1.0 - change) * (1.0 - rigidity)
        e = C.ERROR_MEMORY * e + (1.0 - C.ERROR_MEMORY) * _x
        prev = ch
        st["e_max"] = max(st["e_max"], e)
        if e >= C.ERROR_HIGH:
            st["越0.60的轮"] += 1
        # ④ 交给**真实 DevLevel** 走 A5 判据（张力用台账实测值）
        t = float(m.get("tension") or 0.0) if m.get("tension_measured") else None
        g = dl.update({"e": e, "tension": (t if t is not None else 0.0),
                       "tension_measured": m.get("tension_measured", False)})
        ev = g.get("event") or ""
        if "结构失效" in ev:
            st["失效"] += 1
            st["fail_tension_max"] = max(st["fail_tension_max"], float(t or 0.0))
        if "平衡化完成" in ev:
            st["平衡化"] += 1
        if "不计入生长" in ev:
            st["not_grown"] += 1
    st["终级"] = dl.level
    st["折合升级"] = D.IDX.get(dl.level, 0) - D.IDX.get(D.START_LEVEL, 0)
    import shutil
    shutil.rmtree(tmpd, ignore_errors=True)
    return st


def main() -> int:
    miss = _formula_ok()
    if miss:
        print("★ 源码公式与本脚本不一致 —— 停止（判据没绑在代码上）：%s" % miss)
        return 2
    print("=" * 88)
    print("★ R1 重放复兴验（只读）｜方案 B 公式｜上确界 %.2f｜门槛 %.2f"
          % (C.E_UPPER_BOUND, C.ERROR_HIGH))
    print("=" * 88)
    print("  ⚠️ demo 是固定脚本跑出来的，**单列，不计入真实分布**")
    out = []
    for label, p in LEDGERS:
        if not os.path.exists(p):
            continue
        st = replay(p)
        tag = "【%s】" % label + ("（demo，单列）" if label == "demo" else "")
        print()
        print("  %s" % tag)
        print("     重放轮 **%d**｜可比对轮 **%d**（台账记了 e 的）｜会话 %d"
              % (st["轮"], st["可比对轮"], st["会话"]))
        print("     |e| 最大 **%.3f**（门槛 %.2f）｜越过门槛的轮 **%d**"
              % (st["e_max"], C.ERROR_HIGH, st["越0.60的轮"]))
        print("     结构失效 **%d** 次｜平衡化 **%d** 次｜not_grown **%d** 次"
              % (st["失效"], st["平衡化"], st["not_grown"]))
        print("     终级 **%s**｜折合升级 **%d** 级" % (st["终级"], st["折合升级"]))
        out.append({"台账": label, **st, "demo单列": label == "demo"})
    io.open(OUT_JSON, "w", encoding="utf-8").write(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out))
    print()
    print("=" * 88)
    real = [x for x in out if not x["demo单列"]]
    if real:
        print("  真实台账合计：重放轮 %d｜可比对轮 %d｜失效 %d｜平衡化 %d｜not_grown %d｜升级 %d 级"
              % (sum(x["轮"] for x in real), sum(x["可比对轮"] for x in real),
                 sum(x["失效"] for x in real),
                 sum(x["平衡化"] for x in real), sum(x["not_grown"] for x in real),
                 sum(x["折合升级"] for x in real)))
    print("=" * 88)
    print("已写出：%s" % OUT_JSON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

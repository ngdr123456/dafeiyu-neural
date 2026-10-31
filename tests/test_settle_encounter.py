# -*- coding: utf-8 -*-
"""P1-P6：Stage 2 结算真的会跑（2026-10-30，修差一位后）。

★ 为什么需要这组测试：
  第一版 `_settle_previous_encounter(t-1, ...)` **差一位** ——
  第 t 轮时台账只有 t-1 条（索引 0..t-2），传 `t-1` 正好 `>= len(ents)` ⇒ 立即返回。
  ⇒ 30+ 轮实测里 `boldness` **纹丝不动**（停在 0.50），
     而我当时以为是"没有 BOLD 所以没遭遇"。**离线重算显示应该有 7 次 CONFIRMED。**
  ⇒ 这组测试用**假 reader** 绕开 API，把这条路径钉死。
"""
import io
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

OK = 0
FAIL = 0


def case(name, cond, why=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("  [PASS] 【%s】" % name)
    else:
        FAIL += 1
        print("  [FAIL] 【%s】%s" % (name, why))


print("=" * 78)
print("  Stage 2 结算（P1-P6）")
print("=" * 78)

from pipeline import Pipeline  # noqa: E402

SRC = io.open(os.path.join(_ROOT, "engine", "pipeline.py"), encoding="utf-8").read()


def mk():
    d = tempfile.mkdtemp()
    p = Pipeline(ledger_path=os.path.join(d, "state", "ledger.jsonl"),
                 character_path=os.path.join(d, "state", "character.json"),
                 devlevel_path=os.path.join(d, "state/devlevel_verified.json"),
                 carry_root=d, gate_perception=True, auto_audit=False,
                 use_api=False, use_think=False, use_cognition=True)
    p._input_origin = None
    return p


def C(kind, text, start=0, subject=""):
    return {"kind": kind, "text": text, "start": start,
            "end": start + len(text), "subject": subject}


# ── P1 ★ 源码断言：不再传 `t - 1`
case("P1 ★★ `_settle_previous_encounter` 不再传 `t - 1`（差一位已修）",
     "_settle_previous_encounter(t - 1" not in SRC
     and "_prev_i = len(self.ledger.effective_entries) - 1" in SRC)

# ── P2 直接调 settle：用台账里真实的上一条
p = mk()
# 第 1 轮：她 BOLD（有 Thought + 说了出来）
p.turn("我很难受，这件事一直压着我。")
e0 = p.ledger.effective_entries[-1]
e0.action_observation = {"actual": "QUESTION", "thought_level": "STRONG",
                         "focus_level": "STRONG", "focus_origin": "input"}
e0.cognition = {"op": "DILEMMA", "claims": [C("WANT_MUST", "想说出来", 0)]}
prev_i = len(p.ledger.effective_entries) - 1
# 第 2 轮：他端出了新 claim、够长、没收尾 ⇒ 应 CONFIRMED
p._settle_previous_encounter(prev_i, "行吧被你逮着了，其实那天我戴着看了好几回，我爸到现在都不知道。",
                             None, [C("ACTION", "看了好几回", 0)])
case("P2 ★ settle 真的跑到了（留痕非空）",
     bool(p._settle_traces), "%r" % (p._settle_traces,))
case("P3 ★ 判定为 CONFIRMED 且 boldness 上升",
     p._last_encounter == "CONFIRMED" and (p._settled_boldness or 0) > 0.50,
     "%r / %r" % (p._last_encounter, p._settled_boldness))

# ── P4 幂等：同一 prev_index 不重复结算
_before = p._settled_boldness
p._settle_previous_encounter(prev_i, "又一句很长的话，端出了新东西，说了很多很多。", None,
                             [C("ACTION", "另一件事", 0)])
case("P4 ★ 同一 prev_index 不重复结算（幂等）",
     p._settled_boldness == _before, "%r → %r" % (_before, p._settled_boldness))

# ── P5 REBUFFED 会让 boldness 下降（且降幅 > 升幅）
p2 = mk()
p2.turn("我很难受，这件事一直压着我。")
e = p2.ledger.effective_entries[-1]
e.action_observation = {"actual": "QUESTION", "focus_level": "STRONG"}
e.cognition = {"op": "DILEMMA", "claims": [C("WANT_MUST", "想说出来", 0)]}
up = p2._settled_boldness
p2._settle_previous_encounter(len(p2.ledger.effective_entries) - 1, "嗯。", None, [])
case("P5 ★ REBUFFED 让 boldness 下降（骤短 + 零新 claim）",
     p2._last_encounter == "REBUFFED" and (p2._settled_boldness or 1) < 0.50,
     "%r / %r" % (p2._last_encounter, p2._settled_boldness))

# ── P6 不是 BOLD ⇒ 不结算
p3 = mk()
p3.turn("随便说说。")
e = p3.ledger.effective_entries[-1]
e.action_observation = {"actual": "REFLECT"}
e.cognition = {"op": "", "claims": []}
p3._settle_previous_encounter(len(p3.ledger.effective_entries) - 1,
                              "很长的一段话，端出了很多新东西。", None,
                              [C("ACTION", "某事", 0)])
case("P6 ★ 不是 BOLD ⇒ 不结算（留痕为空、boldness 不动）",
     not p3._settle_traces and p3._settled_boldness is None,
     "%r / %r" % (p3._settle_traces, p3._settled_boldness))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 把 prev_index 改回 t-1                → P1/P2")
print("  MUT-B 去掉幂等挡板                          → P4")
print("  MUT-C 把 settle 移到 cognition 块之外        → P2（无 claims 判不了）")
sys.exit(1 if FAIL else 0)

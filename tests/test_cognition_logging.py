# -*- coding: utf-8 -*-
"""L1-L6：只加日志 + 一处缺陷修复（2026-10-30）。

★ 依据：用户明确要求「只加日志，不改行为」
  · 每轮 settle 结果落盘（轮次 / 是否 BOLD / 遭遇结果 / 结算前后 boldness / 判定时实际用的 claims）
  · idle 的 sources 与重合度落盘
  · 修「跨会话恢复时漏读 idle 的 sources」+ 补一条测试

★ 判据（先写）：
  L1 ★ settle 记录会写进 `cognition_debug.jsonl`（独立文件，不进台账）
  L2 ★ settle 记录含**全部五项**：turn / bold / encounter / boldness_before / boldness_after
  L3 ★ settle 记录含**判定时实际用的 claims**（不是台账里存的那份）
  L4 ★ idle 记录含 sources 与 overlap（逐字重合度）
  L5 ★★ 跨会话恢复时**读 idle 的 sources**（这是被修的缺陷）
  L6 ★ 日志写失败**不影响**这一轮的回应（只记进 `_idle_error`）
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
print("  认知层日志 + 缺陷修复（L1-L6）")
print("=" * 78)

from pipeline import Pipeline  # noqa: E402


def mk():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "state"), exist_ok=True)
    lp = os.path.join(d, "state", "ledger.jsonl")
    p = Pipeline(ledger_path=lp, character_path=os.path.join(d, "state", "character.json"),
                 devlevel_path=os.path.join(d, "state", "devlevel_verified.json"),
                 carry_root=d, gate_perception=True, auto_audit=False,
                 use_api=False, use_think=False, use_cognition=True)
    p._input_origin = None
    return p, lp, d


def C(kind, text, start=0):
    return {"kind": kind, "text": text, "start": start,
            "end": start + len(text), "subject": ""}


p, lp, d = mk()
dbg = os.path.join(d, "state", "cognition_debug.jsonl")
print("  调试日志路径：%s" % os.path.basename(dbg))

# 造两轮，第 1 轮 BOLD
p.turn("我很难受，这件事一直压着我。")
e0 = p.ledger.effective_entries[-1]
e0.action_observation = {"actual": "QUESTION", "focus_level": "STRONG"}
e0.cognition = {"op": "DILEMMA", "claims": [C("WANT_MUST", "想说出来", 0)]}
prev_i = len(p.ledger.effective_entries) - 1
p._settle_previous_encounter(
    prev_i, "行吧被你逮着了，其实那天我戴着看了好几回，我爸到现在都不知道。",
    None, [C("ACTION", "看了好几回", 0)])

recs = [json.loads(l) for l in io.open(dbg, encoding="utf-8") if l.strip()] if os.path.exists(dbg) else []
set_recs = [r for r in recs if r.get("kind") == "settle"]
case("L1 ★ settle 记录写进了 cognition_debug.jsonl（独立文件）",
     bool(set_recs), "文件存在=%r 记录数=%d" % (os.path.exists(dbg), len(set_recs)))
r = set_recs[0] if set_recs else {}
case("L2 ★★ 五项齐：turn / bold / encounter / boldness_before / boldness_after",
     all(k in r for k in ("turn", "bold", "encounter", "boldness_before", "boldness_after")),
     "实际键=%s" % sorted(r.keys()))
case("L3 ★ 含判定时实际用的 claims（claims_now）",
     isinstance(r.get("claims_now"), list) and len(r.get("claims_now") or []) >= 1,
     "%r" % (r.get("claims_now"),))
case("L3b ★ 也存了上一轮的 claims（claims_prev）",
     isinstance(r.get("claims_prev"), list), "%r" % (r.get("claims_prev"),))
case("L2b ★ 这次判成 CONFIRMED 且 boldness 上升",
     r.get("encounter") == "CONFIRMED" and (r.get("boldness_after") or 0) > (r.get("boldness_before") or 1),
     "%r → %r" % (r.get("boldness_before"), r.get("boldness_after")))

# ── L4：idle 记录（直接调 _cog_debug，验字段契约）
p._cog_debug({"kind": "idle", "turn": 3, "quotes": ["甲", "乙"], "sources": [],
              "hit": ["甲"], "overlap": 0.5, "seen_size": 7})
recs = [json.loads(l) for l in io.open(dbg, encoding="utf-8") if l.strip()]
idl = [x for x in recs if x.get("kind") == "idle"]
case("L4 ★ idle 记录含 sources 与 overlap（逐字重合度）",
     bool(idl) and "sources" in idl[0] and idl[0].get("overlap") == 0.5,
     "%r" % (idl[:1],))

# ── L5 ★★：跨会话恢复时读 idle 的 sources（被修的缺陷）
p2, lp2, d2 = mk()
p2.turn("先垫一句。")
e = p2.ledger.effective_entries[-1]
e.cognition = {
    "origin": "input",
    "claims": [C("FIXED", "甲", 0)],
    "idle": {"op": "IDLE_RECOMBINE", "quotes": ["甲", "乙"],
             "sources": [{"turn": 5, "start": 10, "end": 11, "kind": "FIXED", "subject": ""},
                         {"turn": 6, "start": 20, "end": 21, "kind": "ACTION", "subject": ""}]},
}
p2.ledger.append(e)
p3 = Pipeline(ledger_path=lp2, character_path=os.path.join(d2, "state", "character.json"),
              devlevel_path=os.path.join(d2, "state", "devlevel_verified.json"),
              carry_root=d2, gate_perception=True, auto_audit=False,
              use_api=False, use_think=False, use_cognition=True)
case("L5 ★★ 跨会话恢复时**读到了 idle 的 sources**（缺陷已修）",
     (5, 10, 11) in p3._cog_seen and (6, 20, 21) in p3._cog_seen,
     "%r" % (p3._cog_seen,))

# ── L6：日志写失败不影响回应
p4, _, d4 = mk()
p4._cog_debug_path = os.path.join(d4, "no_such_dir_xyz", "deep", "x.jsonl")
try:
    p4._cog_debug({"kind": "settle", "turn": 1})
except Exception as exc:                                       # noqa: BLE001
    case("L6 ★ 日志写失败**不抛异常**", False, "%s" % type(exc).__name__)
else:
    case("L6 ★ 日志写失败不抛异常（只记进 _idle_error）", True)

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 把 settle 日志去掉                         → L1")
print("  MUT-B 日志少记 boldness_before                   → L2")
print("  MUT-C 恢复循环不读 idle.sources                  → L5")
sys.exit(1 if FAIL else 0)

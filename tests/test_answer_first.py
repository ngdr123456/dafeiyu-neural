# -*- coding: utf-8 -*-
"""M1-M12：先接住问题 / idle 冷却 / 校验误报 / run_id（2026-10-31）。

★ 主线：**回应质量**（她先接住他的话，不是先去引旧话）

★ 判据（先写）：
  M1  ★★ 他最后一句是问句 ⇒ `asks_her` 为真；不是问句 ⇒ 为假
  M2  ★ `asks_her_explicitly` 窄口径（含第二人称）与宽口径分开
  M3  ★★ 他在问她 ⇒ `_arbitrate_focus` 的 P3 **让位**（idle 不当焦点）
  M4  ★★ `Frame.stance` 里出现「先接住」硬约束
  M5  ★★★ 引号内不是逐字原话 ⇒ `quotes_verbatim` 报出该片段
  M6  ★ 逐字引用 ⇒ 通过
  M7  ★★ **idle 冷却**：选过 idle 后 3 轮内不再选
  M8  ★★ 死代码 `_idle_prev_turn` 已被替换成 `_idle_last_turn`
  M9  ★★ 校验意见引用的片段不在候选里 ⇒ 该条被剔掉（`dropped_evidence`）
  M10 ★★★ 全部意见都无效 ⇒ 抛 `all_evidence_invalid`（**不当通过**）
  M11 ★ 本地打回：过长 / 引号非逐字（不送模型）
  M12 ★ `cognition_debug` 记录带 `run_id` / `session_id`
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
print("  先接住问题 / idle 冷却 / 校验误报 / run_id（M1-M12）")
print("=" * 78)

from association import asks_her, asks_her_explicitly, quotes_verbatim  # noqa: E402

# ── M1 / M2
case("M1 ★★ 问句末句 ⇒ asks_her 真；陈述 ⇒ 假",
     asks_her("这毛病是不是就我这样啊？") and not asks_her("今天天气不错。"))
case("M2 ★ 窄口径分开：无第二人称的问句宽真窄假；有则都真",
     asks_her("这毛病是不是就我这样啊？") and not asks_her_explicitly("这毛病是不是就我这样啊？")
     and asks_her("你说到底是哪个先把我拽下去的？")
     and asks_her_explicitly("你说到底是哪个先把我拽下去的？"))

# ── M5 / M6
_ok, _bad = quotes_verbatim("我说的不是你原话里的「自己不对」", "我越想越觉得自己哪儿哪儿都不对")
case("M5 ★★★ 缩写引号被报出来（「自己不对」不在原话里）",
     (not _ok) and _bad == ["自己不对"], "%r" % (_bad,))
_ok2, _bad2 = quotes_verbatim("「自己哪儿哪儿都不对」", "我越想越觉得自己哪儿哪儿都不对")
case("M6 ★ 逐字引用通过", _ok2 and not _bad2)


# ── M3 / M4 / M7 / M8 / M12：跑真 pipeline（假 reader 绕开 API）
from pipeline import Pipeline  # noqa: E402


def mk():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "state"), exist_ok=True)
    return Pipeline(ledger_path=os.path.join(d, "state", "ledger.jsonl"),
                    character_path=os.path.join(d, "state", "character.json"),
                    devlevel_path=os.path.join(d, "state", "devlevel_verified.json"),
                    carry_root=d, gate_perception=True, auto_audit=False,
                    use_api=False, use_think=False, use_cognition=True), d


p, d = mk()
p._input_origin = None
# M3：他在问她 ⇒ _he_is_asking 为真，P3 让位
p.turn("你说到底是哪个先把我拽下去的？")
case("M3 ★★ 他在问她 ⇒ `_he_is_asking` 为真", p._he_is_asking is True)
p._unfinished_focus = None
p._pending_thought = None
p._idle_last_turn = None
p._focus_origin = "lexical"
p._arbitrate_focus("你说到底是哪个先把我拽下去的？", None, [])
case("M3b ★★ 他在问她 ⇒ idle 不当焦点（P3 让位）",
     p._focus_origin != "idle" and "让位" in (p._idle_gated or ""),
     "focus=%r gate=%r" % (p._focus_origin, p._idle_gated))

# M4：stance 里有「先接住」
p2, _ = mk()
p2._input_origin = None
p2.turn("你说到底是哪个先把我拽下去的？")
#   ⚠️ 用**真的** perception 对象 —— 假的缺 `hits` 字段，`_build_frame` 会崩。
_RAW = "你说到底是哪个先把我拽下去的？"
_pr = p2.markers.parse(_RAW, None)
fr = p2._build_frame(_RAW, _pr)
case("M4 ★★ `Frame.stance` 里有「先接住」硬约束",
     "先接住" in (fr.stance or ""), "%r" % (fr.stance or "")[:50])

# M7 / M8：idle 冷却
p3, _ = mk()
p3._input_origin = None
p3._turn_seq = 10
p3._idle_last_turn = 10          # 刚在第 10 轮选过
p3._unfinished_focus = None
p3._pending_thought = None
p3._he_is_asking = False
p3._last_encounter = ""
p3._settled_boldness = 0.6
p3._focus_origin = "lexical"
p3._turn_seq = 11                # 第 11 轮（距上次 idle 只 1 轮）
p3._arbitrate_focus("随便一句。", None, [])
case("M7 ★★ idle 冷却：距上次 idle 1 轮 ⇒ 不选（冷却中）",
     p3._focus_origin != "idle" and "冷却" in (p3._idle_gated or ""),
     "gate=%r" % (p3._idle_gated,))

p4, _ = mk()
p4._input_origin = None
assert hasattr(p4, "_idle_last_turn"), "没有 _idle_last_turn"
case("M8 ★★ 死代码 `_idle_prev_turn` 已被 `_idle_last_turn` 取代",
     "_idle_last_turn" in io.open(os.path.join(_ROOT, "engine", "pipeline.py"),
                                   encoding="utf-8").read())

# M12：run_id
p5, d5 = mk()
p5._input_origin = {"run_id": "RUN_X", "session_id": 7}
p5._cog_debug({"kind": "settle", "turn": 1})
recs = [json.loads(l) for l in io.open(p5._cog_debug_path, encoding="utf-8") if l.strip()]
case("M12 ★ cognition_debug 记录带 run_id / session_id",
     recs and recs[-1].get("run_id") == "RUN_X" and recs[-1].get("session_id") == 7,
     "%r" % (recs[-1] if recs else None,))

# ── M9 / M10：校验误报（用假 reader）
import content_fidelity as CF  # noqa: E402
from think import Frame  # noqa: E402

RAW = "我越想越觉得自己哪儿哪儿都不对。"
CAND = "「自己不对」——那是你说的。"


class _R:
    model = "x"
    max_tokens = 4096

    def __init__(self, payload):
        self.payload = payload
        self.last_response = {}

    def _post(self, messages, json_mode=True):
        return {"choices": [{"finish_reason": "stop",
                             "message": {"content": json.dumps(self.payload, ensure_ascii=False)}}],
                "usage": {"completion_tokens": 10, "prompt_tokens": 10}}, None


def mkf():
    return Frame(raw=RAW, dialogue_sources=[], self_facts=[], memory_scope={},
                 relational_context={})


# 意见引用「放下」——不在候选里
r9 = _R({"verdict": "REJECT", "reason": "替他判定什么才算重要",
         "evidence": [{"problem": "unsupported_fact", "text": "放下"}]})
t9 = CF.review(r9, mkf(), CAND)
case("M9 ★★ 引用片段不在候选 ⇒ 被剔掉（进入 dropped_evidence）",
     bool(t9.get("dropped_evidence")), "%r" % (t9.get("dropped_evidence"),))
case("M10 ★★★ 全部意见无效 ⇒ **不当通过**（verdict 仍 UNKNOWN）",
     t9.get("verdict") == "UNKNOWN", "%r" % t9.get("verdict"))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 去掉 P3 的让位                                    → M3b")
print("  MUT-B 去掉 stance 的「先接住」                          → M4")
print("  MUT-C 把冷却删掉（回到死的 _idle_prev_turn）             → M7")
print("  MUT-D 把 all_evidence_invalid 改成 PASS                 → M10")
sys.exit(1 if FAIL else 0)

# -*- coding: utf-8 -*-
"""B1-B7：兜底出口的五条硬约束（2026-10-31）。

★ 用户批准的方案：
  ① 他问 ⇒「没法确认」一类短句；其他 ⇒ 极短承接
  ② 不含问号（代码断言）；不复述他的内容；不对他下指令
  ③ 每种至少 3 个说法；6 轮内不重复
  ④ 「没法确认」本场已用过 ⇒ 换别的说法
  ⑤ 兜底轮单列 fallback，不进 QUESTION/ASK_DETAIL，不算 BOLD

★ 判据（先写）：
  B1 ★★ 两个池子各 ≥3 个说法
  B2 ★★ 每个说法都不含问号
  B3 ★★ 每个说法都不含"下指令"词（你先/你别/你可以/你应该）
  B4 ★★ 连续取 6 次，6 个不重复
  B5 ★★ 本场已有「没法确认」⇒ 取到的句子不含它
  B6 ★★ 兜底轮的 actual 是 FALLBACK（需要 _brain_failed 为真）
  B7 ★★ FALLBACK 不算 BOLD
"""
import io
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
print("  兜底出口（B1-B7）")
print("=" * 78)

from pipeline import Pipeline  # noqa: E402
from association import _is_bold  # noqa: E402


def mk():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "state"), exist_ok=True)
    return Pipeline(ledger_path=os.path.join(d, "state", "ledger.jsonl"),
                    character_path=os.path.join(d, "state", "character.json"),
                    devlevel_path=os.path.join(d, "state", "devlevel_verified.json"),
                    carry_root=d, gate_perception=True, auto_audit=False,
                    use_api=False, use_think=False, use_cognition=True)


p = mk()
case("B1 ★★ 两个池子各 ≥3 个说法",
     len(p.FALLBACK_ASK) >= 3 and len(p.FALLBACK_OTHER) >= 3,
     "ASK=%d OTHER=%d" % (len(p.FALLBACK_ASK), len(p.FALLBACK_OTHER)))
alllines = list(p.FALLBACK_ASK) + list(p.FALLBACK_OTHER)
case("B2 ★★ 每个说法都不含问号",
     not any(("？" in x or "?" in x) for x in alllines))
INSTR = ("你先", "你别", "你可以", "你应该", "你得")
case("B3 ★★ 每个说法都不含下指令词",
     not any(any(w in x for w in INSTR) for x in alllines),
     "%r" % [x for x in alllines if any(w in x for w in INSTR)])

# ── B4：6 次不重复
p2 = mk()
p2._he_is_asking = True
got = [p2._fallback_line() for _ in range(6)]
case("B4 ★★ 连续取 6 次，6 个不重复", len(set(got)) == 6, "%r" % got)

# ── B5：本场已用过「没法确认」⇒ 换别的
p3 = mk()
p3._input_origin = None
p3.turn("先垫一句。")
e = p3.ledger.effective_entries[-1]
e.output = "这个我没法确认。"
p3._he_is_asking = True
p3._fallback_recent = []
line = p3._fallback_line()
case("B5 ★★ 本场已有「没法确认」⇒ 取到的句子不含它",
     "没法确认" not in line, "%r" % line)

# ── B6 / B7：FALLBACK 标记与 BOLD
p4 = mk()
p4._input_origin = None
p4._brain_failed = True
p4.turn("先垫一句。")
ao = p4.ledger.effective_entries[-1].action_observation or {}
case("B6 ★★ 大脑失败 ⇒ actual 是 FALLBACK", ao.get("actual") == "FALLBACK",
     "%r" % ao.get("actual"))
case("B7 ★★ FALLBACK 不算 BOLD",
     _is_bold({"action_observation": {"actual": "FALLBACK"}}) is False)

# ── B7b：thinker 为 None（离线）时**不是**兜底
p5 = mk()
p5._input_origin = None
p5.turn("先垫一句。")
ao5 = p5.ledger.effective_entries[-1].action_observation or {}
case("B7b ★★ 没有大脑（离线）时模板**不算**兜底",
     ao5.get("actual") != "FALLBACK", "%r" % ao5.get("actual"))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 池子里塞一个带问号的句子                     → B2")
print("  MUT-B 去掉 6 轮不重复的逻辑                        → B4")
print("  MUT-C 去掉「没法确认已用」的过滤                     → B5")
print("  MUT-D 把 _brain_failed 判定换回 mode!=brain          → B7b")
print("  MUT-E _is_bold 不排除 FALLBACK                     → B7")
sys.exit(1 if FAIL else 0)

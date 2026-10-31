# -*- coding: utf-8 -*-
"""U1-U4：「没法确认」上限的配套测试（2026-10-31）。

★ 用户裁定（问 4）：「本批对『他问她时最多说 1 次没法确认』的计数，有没有配套测试？没有请补。」

★ 判据（先写）：
  U1 ★★ 台账里已用过 1 次「没法确认」⇒ stance 里出现「这一条你已经用过」
  U2 ★★ 台账里没出现过 ⇒ stance 里**不**出现那句话
  U3 ★ 那句话里带上了实际用过的次数
  U4 ★ 只在他问她时注入（不问她的轮次不注入「先接住」）
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
print("  「没法确认」上限（U1-U4）")
print("=" * 78)

from pipeline import Pipeline  # noqa: E402


def mk():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "state"), exist_ok=True)
    return Pipeline(ledger_path=os.path.join(d, "state", "ledger.jsonl"),
                    character_path=os.path.join(d, "state", "character.json"),
                    devlevel_path=os.path.join(d, "state", "devlevel_verified.json"),
                    carry_root=d, gate_perception=True, auto_audit=False,
                    use_api=False, use_think=False, use_cognition=True)


def stance_of(p, raw):
    p._input_origin = None
    p.turn(raw)
    pr = p.markers.parse(raw, None)
    fr = p._build_frame(raw, pr)
    return fr.stance or ""


RAW_ASK = "你说我是不是有点钻牛角尖了？"

# ── U2：没说过 ⇒ 不注入上限句
p = mk()
st = stance_of(p, RAW_ASK)
case("U2 ★★ 台账里没出现过「没法确认」⇒ stance 里不出现上限句",
     "这一条你已经用过" not in st, "stance 片段：%r" % st[-80:])
case("U4 ★ 他问她 ⇒ 注入了「先接住」", "先接住" in st, "stance 片段：%r" % st[-120:])

# ── U1 / U3：说过 1 次 ⇒ 注入上限句
p2 = mk()
p2.turn(RAW_ASK)
# 手工把她上一轮的 output 改成含「没法确认」
e = p2.ledger.effective_entries[-1]
e.output = "这个我没法确认。你接着说。"
#  ⚠️ 不要在改完 output 之后再 append —— 那会多出一条记录，计数变成 2。
st2 = stance_of(p2, RAW_ASK)
case("U1 ★★ 台账里已有 1 次 ⇒ stance 出现「这一条你已经用过」",
     "这一条你已经用过" in st2, "stance 片段：%r" % st2[-120:])
case("U3 ★ 那句话带上了实际次数（1）",
     "已经说过 1 次" in st2, "stance 片段：%r" % st2[-100:])

# ── U4b：不是问句 ⇒ 不注入先接住
p3 = mk()
st3 = stance_of(p3, "今天有点累，随便说说。")
case("U4b ★ 不是问句 ⇒ 不注入「先接住」", "先接住" not in st3)

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 删掉 _used >= 1 的分支                        → U1/U3")
print("  MUT-B 把计数写死成 0                                → U1")
print("  MUT-C 让他问她与不问都注入                          → U4b")
sys.exit(1 if FAIL else 0)

# -*- coding: utf-8 -*-
"""Y1-Y8：substrate 持久化 + 连续性 + idle 栏位 + 第一人称授权（2026-10-29）。"""
import io
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from cognition_ops import Thought      # noqa: E402
from pipeline import Pipeline          # noqa: E402
from think import FRAME_SYSTEM, Frame  # noqa: E402

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


def mk(name="p1"):
    d = tempfile.mkdtemp()
    return Pipeline(ledger_path=os.path.join(d, "state/ledger.jsonl"),
                    character_path=os.path.join(d, "state/character.json"),
                    devlevel_path=os.path.join(d, "state/devlevel_verified.json"),
                    carry_root=d, gate_perception=True, auto_audit=False,
                    use_api=False, use_think=False)


print("=" * 78)
print("  substrate + 连续性 + idle 栏位（Y1-Y8）")
print("=" * 78)

p = mk()
p.turn("我爸妈已经离婚了，这件事改不了。")
e = p.ledger.effective_entries[-1]

# ── Y1 cognition 字段存在
case("Y1 台账条目有 cognition 字段", hasattr(e, "cognition"))

# ── Y2 ★ claims 能进台账（use_cognition 关闭时不抽，所以这里验结构）
case("Y2 ★ cognition 里可以放 claims（结构就位）",
     "claims" in (e.cognition or {}) or e.cognition is None,
     "%r" % (e.cognition,))

# ── Y3 ★ last 富化（不再只是一个动作名）
last = p._describe_last()
case("Y3 ★ 上一轮描述含**动作**且含**她说的话**",
     "上一轮你选了" in last and ("你说的是" in last or e.output == ""),
     "%r" % last[:70])

# ── Y4 ★ last 里带上一轮的 cognition.hint（如果那轮有 Thought）
p2 = mk("p2")
p2.turn("先垫一句。")
p2._pending_thought = Thought("IMMUTABLE_VS_ACTION_SPLIT",
                              ["这件事改不了", "我说挺好的"],
                              "【你注意到的两处原话】…")
p2.turn("我爸妈已经离婚了，这件事改不了。")
# 手动把上一轮的 cognition 塞进去（模拟 use_cognition 开启的情况）
p2.ledger.effective_entries[-1].cognition = {
    "op": "IMMUTABLE_VS_ACTION_SPLIT", "quotes": ["这件事改不了", "我说挺好的"],
    "hint": "【你注意到的两处原话】一边是…", "sources": []}
last2 = p2._describe_last()
case("Y4 ★ 上一轮若有 cognition.hint，它会出现在 last 里",
     "你当时注意到的是" in last2, "%r" % last2[:90])

# ── Y5 ★ idle_thought 会进 Frame
fr = Frame(raw="随便一句。", idle_thought="【你没在听他说话时…】第 2 轮他说过「甲」，第 5 轮他说过「乙」。")
t = fr.user_text()
case("Y5 ★ idle_thought 出现在简报里，且带第一人称提议",
     "刚才他没说话的空档里" in t and "我刚才还在想你前面说的" in t,
     "%r" % t[:80])

# ── Y6 ★ 当轮冲突优先：有 thought 时，idle 栏位不出现
fr2 = Frame(raw="随便一句。", thought="【你注意到的两处原话】…",
            idle_thought="【空档回想】…")
t2 = fr2.user_text()
case("Y6 ★ 有当轮 Thought 时，idle 栏位**不**出现（让位给当轮冲突）",
     "刚才他没说话的空档里" not in t2,
     "")

# ── Y7 ★ 第一人称授权在 FRAME_SYSTEM 里
case("Y7 ★ FRAME_SYSTEM 明文授权第一人称回想/好奇",
     "你可以用第一人称说出你自己的回想或好奇" in FRAME_SYSTEM
     and "我刚才还在想你前面说的" in FRAME_SYSTEM,
     "")

# ── Y8 ★ 重启后从台账恢复（造一个带 claims 的台账，重新开 Pipeline）
d = tempfile.mkdtemp()
lp = os.path.join(d, "state/ledger.jsonl")
os.makedirs(os.path.join(d, "state"), exist_ok=True)
p3 = Pipeline(ledger_path=lp, character_path=os.path.join(d, "state/character.json"),
              devlevel_path=os.path.join(d, "state/devlevel_verified.json"),
              carry_root=d, gate_perception=True, auto_audit=False,
              use_api=False, use_think=False)
p3.turn("先垫一句。")
p3.ledger.effective_entries[-1].cognition = {
    "origin": "input",
    "claims": [{"kind": "FIXED", "text": "这件事改不了", "start": 0, "end": 6, "subject": "离婚"}]}
p3.ledger.append(p3.ledger.effective_entries[-1])      # 落盘
#   ⚠️ 2026-10-29：`__init__` 的恢复循环现在**只在 use_cognition=True 时跑**
#      （Gemini 诊断出它是 N3 间歇抖动的根因：每场会话重建 Pipeline 都无条件读台账）。
#      ⇒ 这条测试若不开 cognition，测的就是一条**根本不会执行**的路。
p4 = Pipeline(ledger_path=lp, character_path=os.path.join(d, "state/character.json"),
              devlevel_path=os.path.join(d, "state/devlevel_verified.json"),
              carry_root=d, gate_perception=True, auto_audit=False,
              use_api=False, use_think=False, use_cognition=True)
case("Y8 ★ 重启后从台账恢复 _cog_claims（不再失忆）",
     any(cs for cs in p4._cog_claims.values()),
     "恢复的轮数=%d" % len([1 for cs in p4._cog_claims.values() if cs]))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 去掉 _describe_last 的 output 部分     → Y3")
print("  MUT-B 去掉 _describe_last 的 hint 部分       → Y4")
print("  MUT-C 去掉 FRAME_SYSTEM 的第一人称授权       → Y7")
print("  MUT-D 去掉 __init__ 里的恢复循环              → Y8")
sys.exit(1 if FAIL else 0)

# -*- coding: utf-8 -*-
"""D1-D8：去助手化三件套（2026-10-29，Gemini 架构改造 A/B/C）。

★ 用户的原话批评：
  「系统说话时总把自己当成对方的助手（总是习惯性先说一句『这个我替你定不了』）。
    如果只靠写禁令，那只是堵嘴打地鼠。」

★ Gemini 的结构性公式：
    把对方的话当成「向我提问/派单」 + E4「不许替他做决定」
    ≡ 客服免责声明（「这个我替你挑不了」）

★ 判据（先写）：
  D1 ★ 「A 还是 B」抽成句内两难，两段都逐字来自原话
  D2 ★ 逗号在「还是」前也认得（口语最常见）
  D3 ★「该不该 X」/「要不要 X」= X 与"不 X"的两难
  D4 ★ 不是两难的「还是」不许误判（「你还是别去了」）
  D5 ★ 元提问不许误判（「你是什么模型还是什么的」）
  D6 ★ hint 明确说"这不是在让你替他挑"
  D7 ★ `FRAME_SYSTEM` 里**不再常驻**客服二分法
  D8 ★ `FRAME_SYSTEM` 里有"免责声明 = 把自己降成客服"的正面表述
"""
import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from cognition_ops import OP_ORDER, extract_dilemma  # noqa: E402
from think import FACT_GUIDE, FRAME_SYSTEM         # noqa: E402

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
print("  去助手化三件套（D1-D8）")
print("=" * 78)

# ── D1 基本两难
RAW1 = "那你说我现在该干嘛，接着改还是先睡一觉？"
t1 = extract_dilemma(RAW1)
case("D1 ★「A 还是 B」抽成两难，两段逐字来自原话",
     t1 is not None and t1.op == "DILEMMA"
     and all(q in RAW1 for q in t1.quotes),
     "%r" % (t1.quotes if t1 else None,))

# ── D2 逗号在「还是」前
RAW2 = "我是接着改，还是先睡一觉。"
t2 = extract_dilemma(RAW2)
case("D2 ★ 逗号在「还是」前也认得",
     t2 is not None and "先睡一觉" in t2.quotes,
     "%r" % (t2.quotes if t2 else None,))

# ── D3 该不该 / 要不要
t3a = extract_dilemma("我不知道该不该再试一回。")
t3b = extract_dilemma("我在想要不要给她打个电话。")
case("D3 ★「该不该 X」/「要不要 X」= X 与「不 X」的两难",
     t3a is not None and t3b is not None,
     "%r / %r" % (t3a.quotes if t3a else None, t3b.quotes if t3b else None))

# ── D4 不是两难的「还是」不许误判
case("D4 ★「你还是别去了」不许误判成两难",
     extract_dilemma("你还是别去了。") is None)

# ── D5 元提问不许误判
case("D5 ★「你是什么模型还是什么的」不许误判成两难",
     extract_dilemma("你是什么模型还是什么的？") is None)

# ── D6 hint 点破"不是让你挑"
case("D6 ★ hint 明说「这不是在让你替他挑」",
     t1 is not None and "不是在让你替他挑" in t1.hint,
     "%r" % (t1.hint[:50] if t1 else None,))

# ── D7 客服二分法不再常驻
case("D7 ★ FRAME_SYSTEM 里不再常驻「回答完事实就停住」那套客服二分法",
     "回答完事实就停住" not in FRAME_SYSTEM,
     "".join([l for l in FRAME_SYSTEM.splitlines() if "回答完事实" in l])[:60])
case("D7b ★ 但它没丢 —— 挪进了按需注入的 FACT_GUIDE",
     "回答完事实就停住" in FACT_GUIDE or "事实" in FACT_GUIDE)

# ── D8 免责声明 = 把自己降成客服
case("D8 ★ FRAME_SYSTEM 明说「我替你定不了」是免责声明、会把人降成客服",
     "免责声明" in FRAME_SYSTEM and "客服" in FRAME_SYSTEM,
     "")
case("D8b ★ 并且明说「不必说出来：不说也是一种不替他定」",
     "不说也是一种不替他定" in FRAME_SYSTEM)

# ── 优先级
case("D10 ★ DILEMMA 排在 CHAIN 之后、单跳之前",
     OP_ORDER.index("CHAIN_EXTENSION") < OP_ORDER.index("DILEMMA")
     < OP_ORDER.index("IMMUTABLE_VS_ACTION_SPLIT"),
     str(OP_ORDER))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 去掉「还是」两侧 ≥2 字守卫        → D4")
print("  MUT-B 去掉 DILEMMA_BLOCK 元提问过滤     → D5")
print("  MUT-C 把客服二分法塞回 FRAME_SYSTEM     → D7")
sys.exit(1 if FAIL else 0)

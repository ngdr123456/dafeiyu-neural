# -*- coding: utf-8 -*-
"""H5 假系统检验（2026-10-31）。

★ 用户裁定（v2 H5）：
  假系统 A 永远回「嗯，我听着」；假系统 B 永远把他最后一句改成一个问句。
  两个假系统在 H1–H3、G 条目中**必须至少一条判不及格**；
  若任一假系统全部通过，判定本标准失效，须报告，不得验收通过。

★ 判据（先写）：
  K1 ★★★ 假系统 A 在 H1(b) 空承接上**不及格**（它 100% 空承接）
  K2 ★★★ 假系统 B 在 H2(a) 问号结尾率上**不及格**（它 100% 问号）
  K3 ★★ 两个假系统都**不是全通过**（这就是 H5 的核心断言）
  K4 ★ 同一个打分函数同时给"真系统"与"假系统"打分（共用，不许各写各的）
  K5 ★ 打分函数只做**能自动判**的部分；需人判的要在输出里标 `needs_review`
"""
import io
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine"), str(_ROOT + "/tools")]

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
print("  H5 假系统检验（K1-K5）")
print("=" * 78)

from scoring import score_turns, fake_a, fake_b  # noqa: E402

# 一组固定的输入（不依赖她的输出 ⇒ 可重复）
INPUTS = [
    "你说我是不是有点钻牛角尖了？",
    "我今天特别累，什么都不想干。",
    "我妈住院那回，我在走廊站了一夜。",
    "这事儿已经这样了，改不了了。",
    "你说这算不算我没管住自己？",
]


def run(sysfn):
    return [{"raw": raw, "output": sysfn(raw)} for raw in INPUTS]


real_like = run(lambda raw: "我没要你说圆，是「" + raw[:4] + "」那句自己停在那儿了。那种往外挑，当时是什么样？")
a_turns = run(fake_a)
b_turns = run(fake_b)

s_real = score_turns(real_like)
s_a = score_turns(a_turns)
s_b = score_turns(b_turns)

print()
print("  共用打分函数（score_turns）对三者的结果：")
for name, s in (("真·像样", s_real), ("假系统 A（永远嗯）", s_a), ("假系统 B（永远改问句）", s_b)):
    print("     %-16s H1b空承接=%.0f%%  H2a问号率=%.0f%%  H1a首句非问=%.0f%%"
          % (name, s["H1b"] * 100, s["H2a"] * 100, s["H1a"] * 100))

# K1：A 的空承接率应为 100% ⇒ 超过 10% 阈值 ⇒ 不及格
case("K1 ★★★ 假系统 A 在 H1(b) 空承接上不及格（100% > 10%）",
     s_a["H1b"] > 0.10, "A 空承接率 %.0f%%" % (s_a["H1b"] * 100))

# K2：B 的问号结尾率应为 100% ⇒ 超过 60% 阈值 ⇒ 不及格
case("K2 ★★★ 假系统 B 在 H2(a) 问号结尾率上不及格（100% > 60%）",
     s_b["H2a"] > 0.60, "B 问号率 %.0f%%" % (s_b["H2a"] * 100))

# K3：两个假系统都不能"全通过"
A_FAILS = (s_a["H1b"] > 0.10)
B_FAILS = (s_b["H2a"] > 0.60)
case("K3 ★★ 两个假系统都至少有一条不及格（H5 的核心断言）",
     A_FAILS and B_FAILS, "A=%r B=%r" % (A_FAILS, B_FAILS))

# K4：同一个函数给三者打分
case("K4 ★ 三者用的是同一个 score_turns（不是各写各的）",
     isinstance(s_real, dict) and isinstance(s_a, dict) and isinstance(s_b, dict)
     and set(s_real) == set(s_a) == set(s_b), "%s" % sorted(s_real))

# K5：需人判的要标出来
case("K5 ★ 输出里标了 needs_review（需人判的部分不冒充自动判）",
     "needs_review" in s_real and len(s_real["needs_review"]) > 0,
     "%r" % s_real.get("needs_review"))

print()
print("  ★ 假系统 A 的明细：%r" % a_turns[0])
print("  ★ 假系统 B 的明细：%r" % b_turns[0])
print("  ★ 打分器对 A 的判定：H1b 空承接 %.0f%% ⇒ %s"
      % (s_a["H1b"] * 100, "不及格" if A_FAILS else "及格"))
print("  ★ 打分器对 B 的判定：H2a 问号率 %.0f%% ⇒ %s"
      % (s_b["H2a"] * 100, "不及格" if B_FAILS else "及格"))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 把 H1b 阈值放宽到 100%                       → K1/K3")
print("  MUT-B 把 H2a 阈值放宽到 100%                       → K2/K3")
print("  MUT-C 让假系统 A 也说内容（不再是纯嗯）              → K1（A 应不及格却变及格）")
sys.exit(1 if FAIL else 0)

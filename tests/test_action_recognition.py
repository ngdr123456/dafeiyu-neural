# -*- coding: utf-8 -*-
"""O1-O9：改动 ③ —— 三个动作的纯字面识别（2026-10-28，用户已批）。

★ 病灶（Gemini 第三封发现 1，我逐条核对过）：
    `QUESTION` 原判据要求"全文不许有句号" ⇒ 两句式追问被误杀（13 条误命中里 5 条）；
    `REPORT_OWN_STATE` / `ACKNOWLEDGE` 没有分支 ⇒ 8 条真·好回应落进 UNCLASSIFIED。
    ⇒ 训练里 83% 的轮次说不清做了什么，经验层学不到东西。

★ 判据（先写）：
  O1 两句式追问算 QUESTION
  O2 陈述句不算 QUESTION（不许把陈述误判成问句）
  O3 超长问句（>60 字）不算 QUESTION
  O4 自身状态句算 REPORT_OWN_STATE
  O5 ★ 20 字以内、引号外无 ≥4 字原话重合 ⇒ ACKNOWLEDGE
  O6 ★ 不打引号抄他 ≥4 字实词 ⇒ 不算 ACKNOWLEDGE（防暗中复述）
  O7 带引号且引号外很短 ⇒ ACKNOWLEDGE（允许引用原话点穴）
  O8 模板路径仍原样返回 planned
  O9 ★ 编造类输出仍必须是 UNCLASSIFIED（不许被新分支放行）
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from action_observation import SILENCE_TOKEN, observe  # noqa: E402

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


def act(text, raw="", planned="REFLECT", mode="brain", goal=None):
    return observe(text, planned, mode, goal_result=goal, raw=raw)["actual"]


print("=" * 78)
print("  三个动作的纯字面识别（O1-O9）")
print("=" * 78)

# ── O1 ★ 两句式追问
case("O1 ★ 两句式追问算 QUESTION",
     act("我没说听天由命。你眼下那堆烂摊子，是什么？") == "QUESTION",
     act("我没说听天由命。你眼下那堆烂摊子，是什么？"))

# ── O2 陈述句不算问句
case("O2 陈述句不算 QUESTION",
     act("你妈念叨的是邻居家孩子留在这儿。") == "UNCLASSIFIED"
     or act("你妈念叨的是邻居家孩子留在这儿。") == "ACKNOWLEDGE",
     act("你妈念叨的是邻居家孩子留在这儿。"))

# ── O3 超长问句
long_q = "你" * 70 + "？"
case("O3 超长问句（>60 字）不算 QUESTION",
     act(long_q) != "QUESTION", act(long_q))

# ── O4 自身状态
case("O4 自身状态句算 REPORT_OWN_STATE",
     act("我这边没有能翻出来、也没有能扔的东西。") == "REPORT_OWN_STATE",
     act("我这边没有能翻出来、也没有能扔的东西。"))

# ── O5 ★ 短承认（带引号点穴）算 ACKNOWLEDGE
raw5 = "可我一想起每天走同一条路上班，就觉得这辈子好像已经看到头了。"
case("O5 ★ 带引号的短承认算 ACKNOWLEDGE",
     act("「看到头了」——这四个字很重。", raw=raw5) == "ACKNOWLEDGE",
     act("「看到头了」——这四个字很重。", raw=raw5))

# ── O5b ★ 无引号的短句**不算**承认（因为分不清承认与编造）
case("O5b ★ 无引号的短句不算 ACKNOWLEDGE（宁可诚实）",
     act("这件事一直在你那儿。", raw=raw5) != "ACKNOWLEDGE",
     act("这件事一直在你那儿。", raw=raw5))

# ── O5c ★ 引号里的字必须真的在他原话里
case("O5c ★ 引号里的字不在原话里 ⇒ 不算 ACKNOWLEDGE",
     act("「你爸又骂你了」——这四个字很重。", raw=raw5) != "ACKNOWLEDGE",
     act("「你爸又骂你了」——这四个字很重。", raw=raw5))

# ── O6 ★ 不打引号抄实词 ⇒ 不算
case("O6 ★ 不打引号抄他 ≥4 字实词 ⇒ 不算 ACKNOWLEDGE",
     act("每天走同一条路，你已经看到头了。", raw=raw5) != "ACKNOWLEDGE",
     act("每天走同一条路，你已经看到头了。", raw=raw5))

# ── O6b ★ 引号外也抄了 ≥4 字 ⇒ 不算（这条才真正测到 LCS 守卫）
#   没有这条用例的话，LCS 检查是死代码（变异测试证明删掉它不会有失败）。
raw6 = "每天走同一条路上班，觉得看到头了。"
case("O6b ★ 引号外也抄了 ≥4 字 ⇒ 不算 ACKNOWLEDGE",
     act("「看到头了」——同一条路上班。", raw=raw6) != "ACKNOWLEDGE",
     act("「看到头了」——同一条路上班。", raw=raw6))

# ── O7 带引号点穴
case("O7 带引号且引号外很短 ⇒ ACKNOWLEDGE",
     act("「看到头了」——这四个字很重。", raw=raw5) == "ACKNOWLEDGE",
     act("「看到头了」——这四个字很重。", raw=raw5))

# ── O8 模板路径
case("O8 模板路径仍原样返回 planned",
     act("随便一句", planned="JUXTAPOSE", mode="template") == "JUXTAPOSE",
     act("随便一句", planned="JUXTAPOSE", mode="template"))

# ── O9 ★ 编造仍必须 UNCLASSIFIED
case("O9 ★ 长句无引号新内容仍是 UNCLASSIFIED",
     act("你爸一定又骂你了，你从小就怕他。", raw="我爸昨天来了。") == "UNCLASSIFIED",
     act("你爸一定又骂你了，你从小就怕他。", raw="我爸昨天来了。"))

# ── 附：沉默记号仍走 SILENCE
case("附 沉默记号仍识别为 SILENCE",
     act(SILENCE_TOKEN) == "SILENCE", act(SILENCE_TOKEN))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 恢复旧 QUESTION 判据（全文无句号）   → O1")
print("  MUT-B 去掉 ACKNOWLEDGE 的 LCS<4 检查      → O6")
print("  MUT-C 去掉 ACKNOWLEDGE 的长度上限          → O9")
sys.exit(1 if FAIL else 0)

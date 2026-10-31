# -*- coding: utf-8 -*-
"""T1-T10：跨轮思考算子层（2026-10-29，C3）。

★ 病灶（第一次离线跑的实测教训）：
  · 39 条 `IMMUTABLE_VS_ACTION_SPLIT` 里大量是同一句话的两个**重叠片段**：
      「我当初怎么就没多问一句呢」 vs 「没多问一句」
  · 我加 `_too_similar` 时**误把跨轮也做区间检查** ⇒ `CROSS_TURN_CONTRADICTION` 从 2 变 0
  · 单字 subject 若一刀切清空，会杀掉「她」15 次 /「他」9 次（Gemini 的防坑提醒）

★ 判据（先写）：
  T1 单字人物 subject 保留；单字死物清空
  T2 subjects_match：完全相同 ✓｜多字互为子串 ✓｜单字 vs 多字 ✗（"他" ≠ "他们"）
  T3 ★ 同一句的重叠片段不算"两条"（_too_similar）
  T4 ★ 跨轮**不**做区间检查（否则算子 1 永远不触发）
  T5 算子 4：重叠片段 ⇒ 不产出
  T6 算子 4：两条独立 ⇒ 产出，且两条 quote 都是逐字原话
  T7 算子 1：同 subject 跨轮 ⇒ 产出
  T8 算子 1：不同 subject ⇒ 不产出
  T9 算子 3：signature_key 连续 3 次 ⇒ 产出（纯事实计数，不评价）
  T10 ★ 优先级：同时触发时只返回一个，且被让位的记进 yielded
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from cognition_ops import (PERSON_SINGLE, _spans_overlap,  # noqa: E402
                           _too_similar, normalize_subject,
                           session_spans, subjects_match, think)

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


def C(kind, text, start=0, end=None, subject=""):
    return {"kind": kind, "text": text, "start": start,
            "end": end if end is not None else start + len(text), "subject": subject}


print("=" * 78)
print("  跨轮思考算子层（T1-T10）")
print("=" * 78)

# ── T1 单字 subject
case("T1 单字人物保留（她/他/妈），单字死物清空（饭/水）",
     normalize_subject("她") == "她" and normalize_subject("他") == "他"
     and normalize_subject("妈") == "妈"
     and normalize_subject("饭") == "" and normalize_subject("水") == "",
     "她=%r 饭=%r" % (normalize_subject("她"), normalize_subject("饭")))

# ── T2 subjects_match
case("T2 相同 ✓｜多字互为子串 ✓｜单字 vs 多字 ✗",
     subjects_match("我妈", "我妈") and subjects_match("我妈", "我妈的电话")
     and not subjects_match("他", "他们") and not subjects_match("她", "我妈"),
     "他vs他们=%r" % subjects_match("他", "他们"))

# ── T3 / T4 重叠判定
a = C("FIXED", "我当初怎么就没多问一句呢", 0)
b = C("ACTION", "没多问一句", 6)
case("T3 ★ 同一句的重叠片段 ⇒ 判为 too_similar", _too_similar(a, b, same_turn=True), "a=%r b=%r" % (a, b))
c = C("ACTION", "挂了电话", 0)
d = C("WANT_MUST", "我连个offer都拿不到", 0)
case("T4 ★ 跨轮不做区间检查（两轮区间都从 0 起，字面不同 ⇒ 不算相似）",
     not _too_similar(c, d, same_turn=False),
     "same_turn=False → %r" % _too_similar(c, d, same_turn=False))

# ── T5 / T6 算子 4
rows = [{"input": "我当初怎么就没多问一句呢，去了也就那样。", "ts": "2026-10-03 10:00:00"},
        {"input": "我当初怎么就没多问一句呢，去了也就那样。", "ts": "2026-10-03 10:00:30"}]
claims5 = {0: [C("FIXED", "我当初怎么就没多问一句呢", 0),
               C("ACTION", "没多问一句", 6)]}
t5 = think(0, claims5, rows, {}, [(0, 2)])
case("T5 ★ 算子 4：重叠片段 ⇒ 不产出", t5 is None, "t5=%r" % (t5,))

claims6 = {0: [C("FIXED", "去了也就那样", 13),
               C("ACTION", "我就站那儿", 0)]}
rows6 = [{"input": "我就站那儿，去了也就那样。", "ts": "2026-10-03 10:00:00"},
         {"input": "占位", "ts": "2026-10-03 10:00:30"}]
t6 = think(0, claims6, rows6, {}, [(0, 2)])
case("T6 ★ 算子 4：两条独立 ⇒ 产出，且 quote 都是逐字原话",
     t6 is not None and t6.op == "IMMUTABLE_VS_ACTION_SPLIT"
     and all(q in rows6[0]["input"] for q in t6.quotes),
     "%r" % (t6.as_dict() if t6 else None))

# ── T7 / T8 算子 1
rows7 = [{"input": "我想把那封辞职信删了。", "ts": "2026-10-03 10:00:00"},
         {"input": "我把辞职信删了。", "ts": "2026-10-03 10:00:30"}]
claims7 = {0: [C("WANT_MUST", "把那封辞职信删了", 3, subject="辞职信")],
           1: [C("ACTION", "把辞职信删了", 1, subject="辞职信")]}
rows7[0]["_signature_key"] = "sig-a"
rows7[1]["_signature_key"] = "sig-b"
t7 = think(1, claims7, rows7, {}, [(0, 2)])
case("T7 ★ 算子 1：同 subject 跨轮 ⇒ 产出",
     t7 is not None and t7.op == "CROSS_TURN_CONTRADICTION",
     "%r" % (t7.as_dict() if t7 else None))

claims8 = {0: [C("WANT_MUST", "把那封辞职信删了", 3, subject="辞职信")],
           1: [C("ACTION", "把手机扔了", 1, subject="手机")]}
rows8 = [{"input": "我想把那封辞职信删了。", "ts": "2026-10-03 10:00:00"},
         {"input": "我把手机扔了。", "ts": "2026-10-03 10:00:30"}]
t8 = think(1, claims8, rows8, {}, [(0, 2)])
case("T8 算子 1：同轮无 FIXED/ACTION 对、subject 不同 ⇒ 不产出",
     t8 is None, "%r" % (t8.as_dict() if t8 else None))

# ── T9 算子 3（纯事实计数，不评价）
rows9 = [{"input": "还是那件事。", "ts": "2026-10-03 10:00:00", "_signature_key": "sig-x"},
         {"input": "还是那件事。", "ts": "2026-10-03 10:00:30", "_signature_key": "sig-x"},
         {"input": "还是那件事。", "ts": "2026-10-03 10:01:00", "_signature_key": "sig-x"}]
claims9 = {i: [C("COST_FEEL", "还是那件事", 0)] for i in range(3)}
t9 = think(2, claims9, rows9, {}, [(0, 3)])
case("T9 算子 3：signature_key 连续 3 次 ⇒ 产出，且是纯事实计数",
     t9 is not None and t9.op == "HABITUATION_LOOP_BREAK"
     and "第 3 次" in t9.hint and "转圈" not in t9.hint and "兜圈" not in t9.hint,
     "%r" % (t9.as_dict() if t9 else None))

# ── T10 优先级与让位
rows10 = [{"input": "辞职信删了，但这事已经定了。", "ts": "2026-10-03 10:00:00",
           "_signature_key": "s"},
          {"input": "辞职信删了，但这事已经定了。", "ts": "2026-10-03 10:00:30",
           "_signature_key": "s"},
          {"input": "辞职信删了，但这事已经定了。", "ts": "2026-10-03 10:01:00",
           "_signature_key": "s"}]
claims10 = {i: [C("FIXED", "这事已经定了", 9),
                C("ACTION", "辞职信删了", 0)] for i in range(3)}
t10 = think(2, claims10, rows10, {}, [(0, 3)])
case("T10 ★ 同时触发时只返回一个，被让位的记进 yielded",
     t10 is not None and t10.op == "HABITUATION_LOOP_BREAK"
     and "IMMUTABLE_VS_ACTION_SPLIT" in t10.yielded,
     "%r" % (t10.as_dict() if t10 else None))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 单字 subject 一刀切清空            → T1")
print("  MUT-B 去掉 _too_similar 的重叠检查        → T5")
print("  MUT-C 跨轮也做区间检查                    → T7")
print("  MUT-D 算子 3 的 hint 改回「你在兜圈子」      → T9")
sys.exit(1 if FAIL else 0)

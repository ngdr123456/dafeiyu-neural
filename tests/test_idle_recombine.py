# -*- coding: utf-8 -*-
"""R1-R9：自发想的算子 `idle_recombine`（2026-10-29）。

★ 为什么需要它：**现有五个算子都不能在"没有新输入"时触发**
  （算子 1/2/4 都要"本轮有 X"；算子 3 要同一轮内 signature_key 连续重复）。
  ⇒ "她自己想"不能靠重跑算子，得有一个**只吃历史**的算子。

★ 人闲着时在干什么：不是重新观察，是**用已经有的材料换一个配对**。

★ 判据（先写）：
  R1 ★ 两段来自**不同轮**才配（同轮的在算子 2/4 里已经配过）
  R2 ★ 配过的对**不再配**（seen_pairs）
  R3 ★ 找不到就返回 None —— **不硬凑**
  R4 ★ subject 不同且都不为空 ⇒ 不配
  R5 ★ 都为空时只允许 FIXED+ACTION 这一对
  R6 ★ 产出 Thought 的两段 quotes 必须逐字出现在各自那轮的原话里
  R7 ★ op 必须是 `IDLE_RECOMBINE`（与"被触发"的四算子区分开）
  R8 hint 必须说明"你没在听他说话，自己又想到的"（否则会被误读成对她说话）
  R9 ★ 优先想最近的（最近的轮次先想）
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from cognition_ops import (idle_recombine, normalize_subject,  # noqa: E402
                           session_spans)

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


def C(kind, text, start=0, subject=""):
    return {"kind": kind, "text": text, "start": start,
            "end": start + len(text), "subject": subject}


ROWS = [{"input": "我爸妈已经离婚了，这件事改不了。", "ts": "2026-10-03 10:00:00"},
        {"input": "我说挺好的，其实那碗面泡烂在桌上。", "ts": "2026-10-03 10:01:00"},
        {"input": "我妈昨天打电话问我吃饭没。", "ts": "2026-10-03 10:02:00"}]
SPANS = [(0, 3)]

print("=" * 78)
print("  自发想的算子（R1-R9）")
print("=" * 78)

# ── 基线构造：轮 0 有 FIXED，轮 1 有 ACTION
CLAIMS = {
    0: [C("FIXED", "这件事改不了", 11, subject="离婚")],
    1: [C("ACTION", "我说挺好的", 0, subject="吃饭")],
}

# ── R4 subject 不同且都不空 ⇒ 不配
t = idle_recombine(CLAIMS, ROWS, set(), SPANS)
case("R4 ★ subject 不同（离婚 vs 吃饭）⇒ 不配", t is None,
     "%r" % (t.as_dict() if t else None,))

# ── 同 subject ⇒ 配
CLAIMS_SAME = {
    0: [C("FIXED", "这件事改不了", 11, subject="离婚")],
    1: [C("ACTION", "我没敢再问", 0, subject="离婚")],
}
ROWS_SAME = [{"input": "我爸妈已经离婚了，这件事改不了。", "ts": "2026-10-03 10:00:00"},
             {"input": "我没敢再问，怕他难受。", "ts": "2026-10-03 10:01:00"}]
t1 = idle_recombine(CLAIMS_SAME, ROWS_SAME, set(), [(0, 2)])
case("R1 ★ 同 subject 且跨轮 ⇒ 产出", t1 is not None,
     "%r" % (t1.as_dict() if t1 else None))

# ── R6 逐字
if t1:
    ok_lit = all(q in ROWS_SAME[0]["input"] or q in ROWS_SAME[1]["input"] for q in t1.quotes)
else:
    ok_lit = False
case("R6 ★ 两段 quotes 都逐字出现在各自那轮原话里", ok_lit,
     "%r" % (t1.quotes if t1 else None,))

# ── R7 op
case("R7 ★ op 是 IDLE_RECOMBINE（与被触发的四算子区分）",
     t1 is not None and t1.op == "IDLE_RECOMBINE",
     "%r" % (t1.op if t1 else None,))

# ── R8 hint 说明"你没在听他说话"
case("R8 hint 写明「你没在听他说话，自己又想到的」",
     t1 is not None and "没在听他说话" in t1.hint,
     "%r" % (t1.hint[:40] if t1 else None,))

# ── R2 配过的不再配
#
#   ★ Q5.2（Gemini 拍板）：`seen` 不再存字符串对，存 `(turn, start, end)` 三元组 ——
#     因为「这件事改不了」(raw[10:16]) 与「改不了」(raw[13:16]) 字符串不同，
#     但区间重叠，是**原话里同一处**。用区间去重，换十种切法也认得出。
if t1:
    seen = [(ta, ca["start"], ca["end"]) for ta in (0,) for ca in CLAIMS_SAME[ta]]
    seen += [(tb, cb["start"], cb["end"]) for tb in (1,) for cb in CLAIMS_SAME[tb]]
    t2 = idle_recombine(CLAIMS_SAME, ROWS_SAME, seen, [(0, 2)])
else:
    t2 = "no-baseline"
case("R2 ★ 配过的对不再配（seen_pairs 生效）",
     t2 is None, "%r" % (t2 if t2 == "no-baseline" else (t2.as_dict() if t2 else None),))

# ── R3 找不到就不硬凑
case("R3 ★ 空台账 ⇒ 返回 None（不硬凑）",
     idle_recombine({}, ROWS, set(), SPANS) is None)

# ── R1 同轮不配
SAME_TURN = {0: [C("FIXED", "这件事改不了", 11, subject="离婚"),
                 C("ACTION", "我没敢再问", 0, subject="离婚")]}
case("R1b ★ 同一轮内的两条不配（那是算子 4 的活）",
     idle_recombine(SAME_TURN, ROWS, set(), [(0, 1)]) is None)

# ── R5 都为空时只允许 FIXED+ACTION
EMPTY_SUBJ = {
    0: [C("FIXED", "这件事改不了", 11)],
    1: [C("COST_FEEL", "那碗面泡烂在桌上", 8)],
}
ROWS2 = [{"input": "我爸妈已经离婚了，这件事改不了。", "ts": "2026-10-03 10:00:00"},
         {"input": "我说挺好的，其实那碗面泡烂在桌上。", "ts": "2026-10-03 10:01:00"}]
t5 = idle_recombine(EMPTY_SUBJ, ROWS2, set(), [(0, 2)])
case("R5 ★ 都为空且不是 FIXED+ACTION ⇒ 不配", t5 is None,
     "%r" % (t5.as_dict() if t5 else None,))

# ── R9 最近的先想
MULTI = {
    0: [C("FIXED", "这件事改不了", 11, subject="离婚")],
    1: [C("ACTION", "我没敢再问", 0, subject="离婚")],
    2: [C("ACTION", "我又想问了", 0, subject="离婚")],
}
ROWS3 = [{"input": "我爸妈已经离婚了，这件事改不了。", "ts": "2026-10-03 10:00:00"},
         {"input": "我没敢再问。", "ts": "2026-10-03 10:01:00"},
         {"input": "我又想问了。", "ts": "2026-10-03 10:02:00"}]
t9 = idle_recombine(MULTI, ROWS3, set(), [(0, 3)])
case("R9 ★ 最近的那一轮优先被想到",
     t9 is not None and "第 3 轮" in t9.hint,
     "%r" % (t9.hint[:60] if t9 else None,))

# ── R10 ★ 换个切法但同一处 ⇒ 仍算配过（区间去重，不是字符串去重）
#
#   构造：轮 0 的 FIXED 是 raw[10:16]「改不了」，seen 里存 raw[11:16]（更短的切法）
#   ⇒ 字符串不同，但区间重叠 ⇒ 必须被认出来，不许再配一次。
CLIP = {0: [{"kind": "FIXED", "text": "改不了", "start": 12, "end": 15, "subject": "离婚"}],
        1: [{"kind": "ACTION", "text": "我没敢再问", "start": 0, "end": 5, "subject": "离婚"}]}
ROWS_CLIP = [{"input": "这件事已经定了，改不了。", "ts": "2026-10-03 10:00:00"},
             {"input": "我没敢再问，怕他难受。", "ts": "2026-10-03 10:01:00"}]
seen_clip = [(0, 13, 15)]          # 同一处的更短区间
t10 = idle_recombine(CLIP, ROWS_CLIP, seen_clip, [(0, 2)])
case("R10 ★ 换切法但区间重叠 ⇒ 仍算配过（不许重新配）",
     t10 is None, "%r" % (t10.as_dict() if t10 else None,))

# ── R11 ★ 两个字有 40% 以上重合 ⇒ 视为同义复述，不配
SAME_MEANING = {0: [{"kind": "FIXED", "text": "办离婚手续", "start": 0, "end": 5, "subject": "离婚"}],
                1: [{"kind": "ACTION", "text": "办离婚手续", "start": 3, "end": 8, "subject": "离婚"}]}
ROWS_SM = [{"input": "办离婚手续那天，风很大。", "ts": "2026-10-03 10:00:00"},
           {"input": "那天去办离婚手续，排了两小时。", "ts": "2026-10-03 10:01:00"}]
t11 = idle_recombine(SAME_MEANING, ROWS_SM, [], [(0, 2)])
case("R11 ★ 重合率 ≥0.40 ⇒ 同义复述，不配", t11 is None,
     "%r" % (t11.as_dict() if t11 else None,))

# ── R12 ★ 不同会话 ⇒ 不配（第 3 轮 vs 第 20 轮不许硬凑）
FAR = {0: [{"kind": "FIXED", "text": "这件事改不了", "start": 11, "end": 17, "subject": "离婚"}],
       19: [{"kind": "ACTION", "text": "我没敢再问", "start": 0, "end": 5, "subject": "离婚"}]}
ROWS_FAR = [{"input": "我爸妈已经离婚了，这件事改不了。", "ts": "2026-10-03 10:00:00"}] + \
           [{"input": "占位。", "ts": "2026-10-03 11:%02d:00" % i} for i in range(1, 19)] + \
           [{"input": "我没敢再问。", "ts": "2026-10-03 12:00:00"}]
t12 = idle_recombine(FAR, ROWS_FAR, [], session_spans(ROWS_FAR))
case("R12 ★ 不同会话（隔了两小时）⇒ 不配", t12 is None,
     "%r" % (t12.as_dict() if t12 else None,))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 去掉跨轮判定（ta == tb 也允许）        → R1b")
print("  MUT-B 去掉 seen_pairs 去重                    → R2")
print("  MUT-C 去掉 subject 匹配（任意两条都配）        → R4")
print("  MUT-D 去掉「都为空只许 FIXED+ACTION」        → R5")
print("  MUT-E 去掉区间去重（改回字符串全等）           → R10")
print("  MUT-F 去掉重合率守卫                          → R11")
print("  MUT-G 去掉同会话守卫                          → R12")
sys.exit(1 if FAIL else 0)

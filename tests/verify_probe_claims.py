# -*- coding: utf-8 -*-
"""复核 probe_synonyms 的断言：成对比较，看词表写法与用户写法是否**分叉**。

方法论（为什么不用"我写期望值"）
────────────────────────────────────────────────────────────
第一版让每条用例写一个"期望"，结果我自己的期望就写错了两条
（把元提问的响应 id 当标记比对，冤枉了「别重复」「有什么用」）。
**用主观期望当判据，等于把我的判断当真相。**

改成成对比较：
    左 = 词表里已有的写法（系统一定有反应，这是基准）
    右 = 用户实际会写的同义写法（探针报的候选缺口）
两者**行为分叉**才算真问题，且分叉本身就是证据，不需要我判。
两者的行为一致 → 探针报的那条是假警报（说明别处已经接住了）。

注意：分叉只说明"两种写法待遇不同"，**不自动说明右边是错的** ——
「不重复」单独出现本来就歧义，分叉是合理的。所以结论要逐条看，
但**分叉列表本身是客观的**。
"""
from __future__ import annotations

import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pipeline import Pipeline          # noqa: E402


def fresh() -> Pipeline:
    d = tempfile.mkdtemp(prefix="ego_syn_")
    return Pipeline(ledger_path=os.path.join(d, "ledger.jsonl"), auto_audit=False)


# (类别, 词表写法, 用户写法, 这一对在验证什么)
PAIRS = [
    ("疑问代词",   "干嘛呢",     "干嘛",       "「在干嘛」族修过一次，单说「干嘛」是否同等对待"),
    ("疑问代词",   "有什么用",   "有啥用",     "什么→啥"),
    ("疑问代词",   "怎么答",     "咋答",       "怎么→咋"),
    ("主语脱落",   "你有情绪",   "有情绪",     "口语里主语常常不写"),
    ("主语脱落",   "你会难过吗", "会难过吗",   "同上（疑问句）"),
    ("体助词",     "改不了了",   "改不了",     "用户少打一个句尾「了」"),
    ("体助词",     "回不去了",   "回不去",     "同上"),
    ("可能补语",   "睡不好",     "没睡好",     "历史缺口①：V不C ↔ 没VC"),
    ("可能补语",   "控制不了",   "没控制住",   "同上另一方向"),
    ("被动语态",   "我不由自主", "让我很难受", "「让我…」是典型被动句，[E] 归因方向"),
    ("被动语态",   "我控制住了", "我做的",     "主动侧：语态标记是否认得"),
    ("否定",       "别重复",     "不重复",     "否定词互换"),
    ("否定",       "别管我",     "不要管我",   "否定词互换"),
    ("语气词",     "做什么呢",   "做什么",     "用户不写句尾语气词"),
    ("元提问",     "在干嘛",     "干嘛",       "闸门与元提问库是否同步覆盖"),
    ("元提问对照", "你在干什么", "你在干嘛",   "两条都被遮蔽时，用户看到的答复是否相同"),
]


def sig(r) -> tuple:
    """判据只看**意图 + 标记 + 行为类别**。

    第一版把输出原文也算进来，于是每一对都"分叉" ——
    因为元回应和复述句必然**引用用户原话**（「你刚才说的是：『让我很难受』」），
    原文不同是应该的，不是分叉。把必然不同的东西放进判据，等于判据失效。
    """
    return (r.intent, tuple(r.markers), r.behavior)


# 甲案（整句精确匹配）的**反例**。这一组必须全部"不是 META"。
#
# 为什么这组比正例更重要：甲案是一个新机制，它放宽了「指向系统闸门」。
# 而那道闸当初就是为了修一个范畴错误才立的 ——
# 若这些句子被误判成"在问系统"，系统会对着用户的自我陈述回一句元答复，
# 就是把已修好的错换回来。所以**反例全过才算甲案可用**。
NEGATIVES = [
    ("我在想干嘛", "用户在说自己（想什么），不是问系统在做什么"),
    ("我不知道要干什么", "同上"),
    ("我今天特别累，什么都不想干", "历史事故原句：曾被误判成 META"),
    ("我在想有啥用", "带第一人称，用户在自问"),
    ("他会难过吗", "问的是第三者，不是系统"),
    ("我这样做什么都不对", "含「做什么」子串，但整句是陈述"),
    ("有情绪", "非疑问句，甲案不管（这也是它该有的边界）"),
]


def check_negatives() -> int:
    print("\n" + "=" * 84)
    print("甲案反例 —— 这些**必须不判 META**（判错就等于把已修的范畴错误换回来）")
    print("=" * 84)
    bad = 0
    for text, why in NEGATIVES:
        r = fresh().turn(text, None)
        ok = r.intent != "META"
        if not ok:
            bad += 1
        print("%s 「%s」 → intent=%s  行为=%s" % ("[PASS]" if ok else "[FAIL]", text, r.intent, r.behavior))
        print("        理由：%s" % why)
    print("\n反例 %d/%d 通过。" % (len(NEGATIVES) - bad, len(NEGATIVES)))
    return bad


def main() -> int:
    print("=" * 84)
    print("探针断言复核 —— 成对比较（词表写法 vs 用户写法）")
    print("=" * 84)
    # ★ 每一对必须用**各自独立**的管线。
    #   第一版所有用例共用一条管线，于是前一例通过固化（S 通道）、tension、
    #   水平判定影响后一例 —— 实测改一处词表，分叉数从 13 变成 14，
    #   而其中一例的变化根本不是这次改动引起的，是**上下文串味**。
    #   判据必须互相独立，否则测的是历史累积，不是这条输入本身。
    diverged = 0
    for kind, base, variant, why in PAIRS:
        a = fresh().turn(base, None)
        b = fresh().turn(variant, None)
        sa, sb = sig(a), sig(b)
        same = sa == sb
        if not same:
            diverged += 1
        print("\n【%s】%s" % (kind, why))
        print("   词表写法「%s」: intent=%s 标记=%s 行为=%s" % (base, a.intent, a.markers or "无", a.behavior))
        print("        输出：%s" % (a.output or "（空）").replace("\n", " ⏎ "))
        print("   用户写法「%s」: intent=%s 标记=%s 行为=%s" % (variant, b.intent, b.markers or "无", b.behavior))
        print("        输出：%s" % (b.output or "（空）").replace("\n", " ⏎ "))
        print("   → %s" % ("※ 分叉" if not same else "一致（探针那条是假警报）"))

    print("\n" + "=" * 84)
    print("分叉 %d / %d 对。" % (diverged, len(PAIRS)))
    print("分叉只说明两种写法待遇不同，**不自动说明右边错** —— 需逐条看理由。")
    bad = check_negatives()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

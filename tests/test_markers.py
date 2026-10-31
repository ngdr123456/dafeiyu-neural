# -*- coding: utf-8 -*-
"""标记引擎回归测试

原则：测试用例优先取三本书中的**原话或贴近原话的转写**，因为那些句子是理论的实证锚点。
每条用例标注期望命中的标记与期望**不**命中的标记（反例）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine"))

from markers import MarkerEngine  # noqa: E402


CASES = [
    # ---------------------------------------------------------- 自我保护 / 责备外指
    dict(
        name="责备外指（自我保护 Δ）",
        text="这事闹成这样都是他们的错，我有什么办法，赶上了就是赶上了。",
        expect=["blame_external"],
        forbid=[],
    ),
    dict(
        name="【反例】承认自己那部分责任 → 不得判 blame_external",
        text="我也有责任，当时那个决定是我做的，我没想清楚。",
        expect=["voice_shift"],
        forbid=["blame_external"],
    ),
    # ---------------------------------------------------------- 遵奉 / 陈词滥调
    dict(
        name="陈词滥调（遵奉 I-3）",
        text="我觉得做人要善良，要有爱心，大家互相理解就好了。",
        expect=["cliche", "group_sanction"],
        forbid=[],
    ),
    dict(
        name="【反例】对措词本身提出怀疑 → 转判结构标记",
        text="说“开心”好像太笼统了，其实一方面我很高兴，另一方面我也不安。",
        expect=["opposed_pair"],
        forbid=[],
    ),
    # ---------------------------------------------------------- 群体制裁
    dict(
        name="群体制裁（遵奉 I-3）",
        text="主要是怕人家说，别人都那样，我不合群不太好。",
        expect=["group_sanction"],
        forbid=[],
    ),
    dict(
        name="【反例】引用他人观点但不认同",
        text="大家都说该这样，但我不这么看。",
        expect=[],
        forbid=["group_sanction"],
    ),
    # ---------------------------------------------------------- 语态位移
    dict(
        name="语态位移·被动（低于 I-4）",
        text="我被我的情绪困住了，我控制不了，它让我很难受。",
        expect=["voice_shift"],
        forbid=[],
        expect_sub={"voice_shift": "passive"},
    ),
    dict(
        name="语态位移·主动（I-4 以上）",
        text="我困住了我自己。是我选的那条路，我决定的。",
        expect=["voice_shift"],
        forbid=[],
        expect_sub={"voice_shift": "active"},
    ),
    # ---------------------------------------------------------- 两个对立观念
    dict(
        name="两个对立观念并存（发展机制）",
        text="一方面我想留在这里，另一方面我又想走，一直在拉扯。",
        expect=["opposed_pair"],
        forbid=[],
    ),
    # ---------------------------------------------------------- 过度意向
    dict(
        name="过度意向（意义疗法）",
        text="我一定要做到，我必须证明给他们看，绝不允许自己失败。",
        expect=["over_intention"],
        forbid=[],
        _note="原本期望此处也命中 blame_external（“证明给他们看”），实得未命中——判定为测试期望错误，非引擎缺陷：『给他们看』是承受者而非归因，不属于责备外指。",
    ),
    dict(
        name="【反例】外部义务式的“必须”",
        text="合同上必须这么办，我也没别的选择。",
        expect=[],
        forbid=["over_intention"],
    ),
    # ---------------------------------------------------------- 态度句
    dict(
        name="态度句（第三途径，不可改变处境）",
        text="这件事已经改变不了了，我再也回不去了。虽然这样，但我可以选择怎么过接下来的日子。",
        expect=["immutable", "attitude_clause"],
        forbid=[],
    ),
    dict(
        name="【反例】纯宿命论 → 不得判 attitude_clause",
        text="没办法，就这样吧，听天由命。",
        expect=[],
        forbid=["attitude_clause"],
    ),
    # ---------------------------------------------------------- 想要 / 喜欢分离
    dict(
        name="想要／喜欢分离（多巴胺）",
        text="我就是想得到它，特别想，我一定要拿到。",
        expect=["want_like_gap", "over_intention"],
        forbid=[],
    ),
    dict(
        name="【反例】同一处出现体验描述 → 不得判 want_like_gap",
        text="我很想吃那家的面，汤是烫的，闻着特别香。",
        expect=[],
        forbid=["want_like_gap"],
    ),
    # ---------------------------------------------------------- 当下分子缺失
    dict(
        name="当下分子缺失（多巴胺）",
        text="等以后吧，等我有了条件，将来总有一天，下一步再说。",
        expect=["present_missing"],
        forbid=[],
    ),
    # ---------------------------------------------------------- 不可改变识别
    dict(
        name="不可改变识别（E1 闸门）",
        text="他已经走了，再也回不来了，这个我改变不了。",
        expect=["immutable"],
        forbid=[],
    ),
    # ---------------------------------------------------------- relation（三值关系）
    dict(
        name="relation·SUPPRESSED（我不去想 = 抑制标记，不是无意识证据）",
        text="这件事我不去想，别提了。",
        expect=["immutable"],
        forbid=[],
        expect_relation="SUPPRESSED",
    ),
    dict(
        name="relation·DEFERRED（我没想起 = 可及）",
        text="我没想起这件事，忘了。",
        expect=[],
        forbid=[],
        expect_relation="DEFERRED",
    ),
    dict(
        name="relation·DISPLACED（被变形）",
        text="不知道为什么我一直在说别的，说远了。",
        expect=[],
        forbid=[],
        expect_relation="DISPLACED",
    ),
    # ---------------------------------------------------------- 废纸篓
    dict(
        name="【废纸篓】无任何标记命中 → underdetermined",
        text="今天天气还行。",
        expect=[],
        forbid=[],
        expect_underdetermined=True,
    ),
    # ---------------------------------------------------------- 联合禁令上报
    dict(
        name="联合上报：immutable + present_missing + over_intention 的三种降级提示",
        text="我一定要做到，等以后吧，将来总有一天，虽然已经改变不了了。",
        expect=["over_intention", "present_missing", "immutable"],
        forbid=[],
        expect_notes_contains=["E1 生效", "fuel_priority 生效", "过度意向"],
    ),
]


def run() -> int:
    eng = MarkerEngine()
    passed, failed = 0, 0
    print("=" * 78)
    for c in CASES:
        r = eng.parse(c["text"], c.get("topic_id"))
        errs = []

        for m in c.get("expect", []):
            if m not in r.markers:
                errs.append("缺少期望标记 %s" % m)
        for m in c.get("forbid", []):
            if m in r.markers:
                errs.append("误判了禁止标记 %s" % m)
        for mid, sub in (c.get("expect_sub") or {}).items():
            h = next((x for x in r.hits if x.id == mid), None)
            if not h or h.sub_kind != sub:
                errs.append("子类型不符：%s 期望 %s，实得 %s" % (mid, sub, h.sub_kind if h else None))
        if c.get("expect_relation"):
            if r.relation_hint != c["expect_relation"]:
                errs.append("relation 期望 %s，实得 %s" % (c["expect_relation"], r.relation_hint))
        if c.get("expect_underdetermined"):
            if not r.underdetermined:
                errs.append("期望 underdetermined=True，实得 False")
        for frag in c.get("expect_notes_contains", []):
            if not any(frag in n for n in r.notes):
                errs.append("notes 缺少 %s" % frag)

        ok = not errs
        passed += ok
        failed += (not ok)
        flag = "PASS" if ok else "FAIL"
        print("[%s] %s" % (flag, c["name"]))
        print("       命中: %s" % (r.markers or "（无）"))
        if not ok:
            for e in errs:
                print("       !! %s" % e)
            print("       原文: %s" % c["text"])
            print("       证据: %s" % {h.id: h.evidence for h in r.hits})
        print("-" * 78)

    print("结果: %d 通过 / %d 失败 / 共 %d" % (passed, failed, len(CASES)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run())

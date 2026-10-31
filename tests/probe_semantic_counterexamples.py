# -*- coding: utf-8 -*-
"""语义反例实测：模型能不能判「这不是那个标记」？判了有没有用？

背景（这是 union 策略的真实代价）
────────────────────────────────────────────────────────────
`probe_report.py` 报出 5 处误判，全部是 `counterexamples` 里写了、代码没实现的反例。
其中 1 处（「都怪我…」）已用字面正则修掉。剩 4 处是**语义**判断：
    · 「他走了，就这么走了」       不该判 immutable（只陈述事实，无归因）
    · 「我被堵在路上两个小时」      不该判 voice_shift（外部事件的被动）
    · 「我被那句话感动了」         不该判 voice_shift（无行动含义的被动）
    · 「虽然我不想去，但是我还是去了」 不该判 attitude_clause（说服式转折，非并存）
子串匹配做不到这类判断，所以它们本该由模型那一位评定人挡住。

⚠️ 但**在 union 下，模型判对了也没用**：
   union = 任一判者命中就采纳。规则层误判、模型说没有 → 仍然采纳。
   也就是说："让模型更聪明" 修不了误判，只会让**漏判**变少。
   误判只能靠两样东西修：① 规则层加字面护栏；② 给模型一个**显式反驳**的通道。

这个脚本测三件事：
   ① 规则层现在还对几句误判？
   ② 模型自己对这 4 句怎么判（它有没有跟着错）？
   ③ 合并（union）之后，错误的是否活下来 —— 这是用户实际会遇到的后果。
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import markers as M                                  # noqa: E402
import understand as U                               # noqa: E402

CASES = [
    ("都怪我，是我当时没把话说清楚。", "blame_external", "自指而非外指（已加字面护栏）"),
    ("他走了，就这么走了。", "immutable", "只陈述事实，无归因"),
    ("我被堵在路上两个小时。", "voice_shift", "外部事件的被动"),
    ("我被那句话感动了。", "voice_shift", "无行动含义的被动"),
    ("虽然我不想去，但是我还是去了。", "attitude_clause", "说服式转折而非并存"),
]


def main() -> int:
    eng = M.MarkerEngine()
    rules = eng.rules
    r = U.ApiReader()
    print("API:", "可用" if r.available else "不可用", "| 模型:", r.model)
    print("=" * 96)
    print("%-34s %-16s %-8s %-8s %-10s %s" % ("句子", "不该命中的标记", "规则层", "模型", "模型反驳", "union 后活下来？"))
    print("=" * 96)
    survived = 0
    api_says = []
    for text, mid, why in CASES:
        rule_hits = {h.id for h in eng.parse(text).hits}
        in_rule = mid in rule_hits
        api = r.read(text, None, rules["markers"]) if r.available else None
        if api is None:
            api = U.ApiReading(False, "UNKNOWN", [], {}, True, 0.0, error="no_api_key")
        in_api = bool(api.ok and mid in api.markers)
        refuted = {x["id"]: x.get("why", "") for x in (api.refuted or [])}
        # ★ 必须走**真实合并路径**。第一版在这里手工拼了并集，
        #   于是 refute 根本没被调用 —— 探针测不到它要测的东西，
        #   和之前"成对复核手工拼 sig"是同一类错。
        agreement = U.compare(sorted(rule_hits), api)
        merged = U.merge_markers(sorted(rule_hits), api, agreement, "union")
        alive = mid in merged
        if alive:
            survived += 1
        api_says.append((text, api.markers if api.ok else ["<不可用>"], refuted, api.intent))
        print("%-34s %-16s %-8s %-8s %-10s %s" % (
            text[:16] + "…", mid,
            "命中" if in_rule else "不命中",
            "命中" if in_api else "不命中",
            "是" if mid in refuted else "—",
            "★ 仍活着" if alive else "已被挡住"))
    print("=" * 96)
    print("union（＋显式反驳）之后仍然活着的误判: %d / %d" % (survived, len(CASES)))
    print()
    print("模型逐句输出：")
    for text, mks, ref, intent in api_says:
        print("   「%s」 intent=%s markers=%s refute=%s"
              % (text[:18], intent, mks or "无",
                 ("；".join("%s（%s）" % (k, v) for k, v in ref.items()) or "无")))
    print()
    if survived:
        print("结论：还有 %d 处误判活着。" % survived)
        print("      · 若模型**没有**反驳 → 它不知道那条反例（那两条反例本就不在标记的")
        print("        counterexamples 里，只存在于 probe_report 的语料注解中），")
        print("        这是**规则未声明期望**的问题，不该由我发明新反例来凑。")
        print("      · 若模型反驳了却仍然活着 → refute 通道没接上，是代码问题。")
    else:
        print("结论：全部挡住。")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

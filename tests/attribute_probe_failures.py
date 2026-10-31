# -*- coding: utf-8 -*-
"""归因实测：probe_report 报的 5 处误判，是我改出来的，还是本来就有？

为什么要专门做这一步
────────────────────────────────────────────────────────────
我刚改了 markers.json（补 immutable 的 5 条、voice_shift 的被动侧 7 条、
regex 加 `改不了了?`）。`probe_report.py` 随即报出「漏 4 ｜误判 5」。
**改完东西之后看到红，第一件事不是解释，是归因。**

没有 git 可比对（这个目录不是仓库），所以用**变量隔离**：
把规则表在内存里还原成我改之前的样子（删掉我加的条目），
拿同样这几句话再跑一遍。
    两次都命中 → 本来就有的缺陷，与我的改动无关
    只有现在命中 → 是我改出来的，必须改回去
"""
from __future__ import annotations

import copy
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import markers as M      # noqa: E402

# 我在本轮加进 markers.json 的条目（逐条列出，便于核对）
ADDED = {
    "immutable": ["回不去", "不可能", "没有办法", "改不了", "别提"],
    "voice_shift_passive": ["让我", "使我", "没办法控制", "不受我控制", "它自己", "它又来了"],
    "voice_shift_active": ["我做的"],
    "voice_shift_passive_2": ["控制不住", "没控制住"],
}

FALSE_POSITIVES = [
    ("都怪我，是我当时没把话说清楚。", "blame_external"),
    ("他走了，就这么走了。", "immutable"),
    ("我被堵在路上两个小时。", "voice_shift"),
    ("我被那句话感动了。", "voice_shift"),
    ("虽然我不想去，但是我还是去了。", "attitude_clause"),
]


def strip_my_additions(rules: dict) -> dict:
    r = copy.deepcopy(rules)
    for mk in r["markers"]:
        if mk["id"] == "immutable":
            for p in ADDED["immutable"]:
                if p in mk["patterns"]:
                    mk["patterns"].remove(p)
            mk["regex"] = "(改变不了)|(无法(挽回|改变))|(再也(不|没))|(回不去了)|(已经(发生|过去|是事实))"
        if mk["id"] == "voice_shift":
            sp = mk.get("sub_patterns") or {}
            for key, addkey in (("passive", "voice_shift_passive"),
                                ("active", "voice_shift_active"),
                                ("passive", "voice_shift_passive_2")):
                if key in sp:
                    for p in ADDED[addkey]:
                        if p in sp[key]["examples"]:
                            sp[key]["examples"].remove(p)
    return r


def main() -> int:
    cur = M.load_marker_rules()
    old = strip_my_additions(cur)

    print("=" * 76)
    print("归因实测：5 处误判是我改出来的，还是本来就有？")
    print("=" * 76)
    print("%-34s %-16s %-10s %-10s %s" % ("句子", "标记", "改后", "还原后", "归因"))
    print("-" * 76)
    mine = 0
    for sent, mid in FALSE_POSITIVES:
        now = mid in {h.id for h in M.MarkerEngine(cur).parse(sent).hits}
        before = mid in {h.id for h in M.MarkerEngine(old).parse(sent).hits}
        if now and before:
            verdict = "本来就有的缺陷（与我无关）"
        elif now and not before:
            verdict = "★ 是我改出来的 —— 必须改回"
            mine += 1
        else:
            verdict = "两次都不命中（已修）"
        print("%-34s %-16s %-10s %-10s %s" % (
            sent[:16] + ("…" if len(sent) > 16 else ""), mid,
            "命中" if now else "不命中", "命中" if before else "不命中", verdict))

    print()
    if mine == 0:
        print("结论：5 处误判**全部**在我改动之前就存在 —— 不是回归。")
        print("      它们是 voice_shift / blame_external 的 JSON 反例（写在 counterexamples 里）")
        print("      **从来没有被代码实现过**：`_is_negated_or_quoted` 只处理否定与引用，")
        print("      不处理『外部事件的被动』『无行动含义的被动』这类语义反例。")
        print("      所以它们一直红着，只是此前没人跑这个体检。")
    else:
        print("结论：有 %d 处是我改出来的，必须立刻收回。" % mine)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

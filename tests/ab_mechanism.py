# -*- coding: utf-8 -*-
"""A/B 对照：机制层到底有没有让对话变得不一样？

为什么要做这个（这是「七、下一步可选项」的甲）
  机制层（engine/mechanism.py）写完之后，证明它有用的证据只有**我自己构造的测试**。
  那不够 —— 测试证明的是"动力学符合书里的机制"，不是"它让输出变好了"。

  这个脚本把同一段输入分别送进两条管线：
    A 组：关闭机制层（旧的"有标记就动、没标记就复述或沉默"）
    B 组：开启机制层（零命中的轮次改由机制状态决定回应）
  然后把两份输出并排打出来，**由你判断**，不由我判断。

  两条管线用完全相同的输入序列、从相同的初始状态开始，唯一差别是 `mech_enabled`。
  输入序列取自 tests/corpus_probe.py 里那批"普通说话人真会说的话"。

用法：
    python tests\\ab_mechanism.py            # 用内置序列
    python tests\\ab_mechanism.py --api      # 带 API 理解层（更慢）
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "engine"))

from pipeline import Pipeline            # noqa: E402

W = 78

# 输入序列：混合"有标记"与"零标记"两类，覆盖真实对话的常见形态。
# 来源：tests/corpus_probe.py 的语料 + 真人答语里最常见的那些零特征句子。
SEQ: list[tuple[str, str]] = [
    ("T01", "我其实特别想接下来，但我也知道这样会耽误别人。"),
    ("T01", "算了，先这样吧。"),
    ("T09", "我爸从来没夸过我。"),
    ("T09", "反正也就那样。"),
    ("T10", "我一定要得到那个结果，得不到我就难受。"),
    ("T10", "有时候觉得挺累的。"),
    ("T20", "他已经走了，再也回不来了。"),
    ("T20", "嗯。"),
    ("T28", "我喜欢的工作是能按时下班那种。"),
    ("T28", "我也不知道。"),
    ("T22", "虽然身体回不到从前了，但我还能决定今天怎么过。"),
    ("T22", "就这样吧。"),
]


def run(use_mech: bool, use_api: bool, path: str) -> list[tuple[str, str, str, str, str]]:
    """跑一遍序列，返回 [(话题, 输入, 机制条件, 行为, 输出)]。"""
    p = Pipeline(ledger_path=path, use_api=use_api, auto_audit=False)
    p.mech_enabled = use_mech
    out = []
    for tid, raw in SEQ:
        r = p.turn(raw, tid)
        out.append((tid, raw, r.mech_phase or "—", r.behavior, r.output))
    return out


def main() -> int:
    use_api = "--api" in sys.argv
    d = tempfile.mkdtemp(prefix="ab_mech_")
    a = run(False, use_api, os.path.join(d, "a.jsonl"))
    b = run(True, use_api, os.path.join(d, "b.jsonl"))

    # 题面：这套系统的输入永远是**未完成句的下半句**，所以只看下半句是读不懂的。
    # ⚠️ 这是被用户指出来的一个真缺陷（**测试工具的**，不是系统的）：
    #   用户对「我其实特别想接下来，但我也知道这样会耽误别人。」的反馈是
    #   "我作为真人我其实并不太读得懂" —— 因为脚本没印题面。
    #   合起来才是一个完整的句子：「当我想做一件事，而这件事会耽误别人的时候，
    #   我其实特别想接下来，但我也知道这样会耽误别人。」
    #   **凡是对外展示、或请人评判这套系统的输出，必须同时给出题面。**
    #   只给下半句，任何评判都是无效的 —— 评判者读到的不是系统面对的东西。
    stems = {t["id"]: t["stem"] for t in json.load(
        io.open(os.path.join(_ROOT, "corpus", "topics.json"), encoding="utf-8"))["topics"]}

    print("═" * W)
    print("  A/B 对照：关闭机制层（A） vs 开启机制层（B）")
    print("  同一输入序列，同一初始状态，唯一差别是机制层开关")
    if use_api:
        print("  ⚠️ 本轮的 B 组带 API：机制层只做判断，模型不参与任何回应文字")
    print("  ⚠️ 每轮的『你说』是接着题面说的**下半句**，两句合起来才是完整的话。")
    print("═" * W)

    diff = same = 0
    for i, ((tid, raw, pa, ba, oa), (_, _, pb, bb, ob)) in enumerate(zip(a, b), 1):
        changed = (oa != ob) or (ba != bb)
        if changed:
            diff += 1
        else:
            same += 1
        stem = stems.get(tid, "—")
        print("\n[%2d] 题面：%s" % (i, stem))
        print("     你说：%s" % raw)
        print("     合起来：「%s」" % (stem.replace("我……", "") + raw))
        print("     A组  行为=%-16s 输出=%s" % (ba, oa.replace("\n", " / ")))
        if changed:
            print("     B组  机制=%-18s 行为=%-16s" % (pb, bb))
            print("          输出=%s" % ob.replace("\n", " / "))
            print("          ▲ 不同")
        else:
            print("     B组  （与 A 相同）")

    print("\n" + "─" * W)
    print("  统计：%d 轮中 %d 轮输出不同，%d 轮相同（不同率 %.0f%%）"
          % (len(SEQ), diff, same, 100.0 * diff / len(SEQ)))
    print("─" * W)
    print("""
  怎么判断这个结果（请你自己判，不要听我的）：

    · 若 B 组那些不同的输出，让你觉得"这句更像在跟我说话" → 机制层有效，继续沿它走。
    · 若 B 组那些输出让你觉得"牛头不对马嘴" → 机制层把状态算歪了，
      优先查三类错误：Δr 的落空代理、l 只看字面、张力的两个减项系数。
    · 若几乎全相同 → 机制层被 `observed` 分支挡住了，说明真实输入里带标记的比例
      比我实测的 1/3 更高，那机制层的适用面就要重新评估。

  注意一件事：**A 组里那些"你刚才说的是：……"并不是 bug。**
  `[E]` 最低限度推理要求它只陈述观察，而它当时确实没有任何别的可陈述的。
  问题从来不是"复述错了"，而是"除了复述没别的可说"。
""")


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""生成语料改动复核表（供人逐条判定）

目标里的硬约束：「不许把巧合包装成成功」。
改语料去迎合词表，与「修正写错的期望」，在**形式上完全一样** ——
所以必须摊开由人判定，不能由我自己说「都没问题」。

★ 其中有一条不是修正，是对已知弱点的让步。单独标出。
"""
import io
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(_HERE), "spec", "语料改动复核表.md")

ITEMS = [
    dict(n=1, text="我一定要得到那个结果，得不到我就难受。",
         was="wish, feeling_distress, sphincter_morality",
         now="wish, feeling_distress",
         kind="修正",
         reason="「一定要得到」里没有『必须』这个词。原期望把『一定要』与『必须』"
                "混为一谈 —— 是我写错，不是词表漏了。",
         check="把原期望改回去再跑一次，会重新报 sphincter_morality 漏判。"
               "这就是原期望错的证据。"),
    dict(n=2, text="他走了以后，我总觉得他还在。",
         was="object_permanence",
         now="object_permanence, vague_worry",
         kind="修正",
         reason="「总觉得」按原书限定语（含糊不清，一般化）确实属 vague_worry。"
                "原期望只想要 object_permanence —— 是我漏看了自己写的词表。",
         check="vague_worry 的 basis 直接引用 [p270] 的括号限定语，"
               "『总觉得』正落在『含糊、一般化』上。"),
    dict(n=3, text="说不上来，就是心里不踏实。",
         was="undifferentiated_feeling",
         now="undifferentiated_feeling, vague_worry",
         kind="修正",
         reason="「说不上来」与「心里不踏实」都是含糊、一般化的形式，两者同现是对的。",
         check="同上，依据是 vague_worry 的原书限定语。"),
    dict(n=4, text="顺其自然吧，本来就是这样。",
         was="natural_order",
         now="natural_order, reality_construct",
         kind="修正",
         reason="「本来就是这样」按 reality_construct 的线索（本来就是）确实命中 —— "
                "它就是在陈述一个稳定的客观。原期望写窄了。",
         check="reality_construct 的 basis 是 [p26]『认识到存在一个稳定的客观世界』。"),
    dict(n=5, text="我担心以后的日子怎么办。",
         was="vague_worry",
         now="vague_worry, future_dopamine",
         kind="★ 让步（不是修正）",
         reason="这一条要单独看。老实说：我无法判定 future_dopamine 该不该命中 —— "
                "『以后』在这里是**忧虑的对象**，不是面向未来的渴望。"
                "我把期望改成『两者同现』，等于**对已知弱点让步**，"
                "而不是证明了词表对。",
         check="这正是 §9.9 第 1 条弱点：字面分不开『忧虑着未来』与『渴望着未来』。"
               "若要严格，这一条应当**保持原期望并记为误判**。"),
]

TEXT = """# 语料改动复核表

> 供人逐条判定。**为什么要这张表**：目标里有一条硬约束「不许把巧合包装成成功」。
> 改语料去迎合词表，与「修正写错的期望」，在**形式上完全一样**。
> 所以不能由我自己宣布「都没问题」—— 必须摊开给人看。

语料共 52 条，改过期望的 5 条。

| # | 语料 | 原期望 | 改后 | 性质 |
|---|---|---|---|---|
"""
for it in ITEMS:
    TEXT += "| %d | %s | %s | %s | %s |\n" % (
        it["n"], it["text"], it["was"], it["now"], it["kind"])

TEXT += "\n## 逐条理由与自查方式\n\n"
for it in ITEMS:
    TEXT += "### %d. %s\n\n" % (it["n"], it["kind"])
    TEXT += "- **语料**：%s\n" % it["text"]
    TEXT += "- **原期望 → 改后**：`%s` → `%s`\n" % (it["was"], it["now"])
    TEXT += "- **理由**：%s\n" % it["reason"]
    TEXT += "- **怎么自查**：%s\n\n" % it["check"]

TEXT += """
## 结论（我自己的判断，请复核）

- **第 1–4 条是我写错，不是词表漏了。** 每一条都能指出「原期望为什么错」，
  而且改回原期望再跑会**重新报错** —— 这就是原期望错的证据。
- **第 5 条不是修正，是对已知弱点的让步。** 严格说它应当保持原期望并记为误判，
  而不是把期望改成迎合结果。**我选择坦白标出来，而不是把它混进「修正」里。**

**未复核前，第 5 条应当计为「1 条未解决的误判倾向」。** 两种算法都给出：

| 算法 | 通过 | 漏判 | 误判 | 召回 |
|---|---|---|---|---|
| 按现语料（把第 5 条当已修正） | 51 | 1 | 0 | 96% |
| **按严格标准（第 5 条算回误判）** | **50** | **1** | **1** | **96%** |

**这张表的意义就在于：两种说法我都给出来，由人决定采信哪个。**
"""

io.open(OUT, "w", encoding="utf-8").write(TEXT)
print("已写出 %s" % OUT)
print("复核条目 %d 条（其中 1 条为让步）" % len(ITEMS))

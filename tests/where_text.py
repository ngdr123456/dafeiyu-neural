# -*- coding: utf-8 -*-
"""清点：现在这套系统里，"文字"到底从哪来

用户的问题：模型不生成文字，那文字从哪来？
本脚本不回答，只把事实摆出来 —— 每一句可能被说出来的话，源头在哪。
"""
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(p):
    return json.load(io.open(os.path.join(ROOT, p), encoding="utf-8"))


print("═" * 78)
print("  事实：现在所有可能被说出来的话，源头清单")
print("═" * 78)

b = load("rules/behaviors.json")
print()
print("  ① 言语行为模板（决定「说什么样的话」）")
tot = 0
for x in b["behaviors"]:
    tot += len(x["templates"])
    print("     %-20s %d 条" % (x["id"], len(x["templates"])))
print("     合计 %d 条完整句子模板" % tot)

m = load("rules/meta_responses.json")
n2 = len(m["responses"]) + len(m["states"])
print()
print("  ② 元提问／状态固定回应　%d 条" % n2)
for x in m["responses"]:
    print("     %-20s %s" % (x["id"], x["text"].split("\n")[0][:30]))
for x in m["states"]:
    print("     %-20s %s" % (x["id"], x["text"].split("\n")[0][:30]))

# 槽位：哪些是"动态填入"的
print()
print("  ③ 槽位（唯一动态的部分）—— 填进去的都是**用户原话或用户原话的片段**")
print("     {echo} / {echo2}   用户原话的逐字片段（由 respond.py 切分）")
print("     {must}            从「必须」类表达里取的片段")
print("     {immutable_part}  不可改变那半句")
print("     {ask_detail}      锚点句（引用用户原话里的词）")
print()
print("  ⚠️ 所以：系统说出的每个字，要么来自**上面那些预先写好的模板**，")
print("     要么来自**用户自己说过的话**。它没有第三个来源。")

print()
print("═" * 78)
print("  这意味着什么（诚实的推论）")
print("═" * 78)
print("""
  推论 1：它说不出模板里没有的话。
     模板 %d 条 + 元回应 %d 条。这就是它的全部词汇量（句子层面）。

  推论 2：性格只能**选**模板，不能**造**模板。
     关联矩阵算出"此刻该承认"，而"承认"这个动作的措辞是那 4 条里的一条。
     所以经历能改变"它在什么场合说什么行为"，
     **但改不了"承认"这句话本身长什么样**。

  推论 3：所以现在的架构能到的地方，上限是：
     「在各种场合说出各种预先写好的人话」
     而不是
     「像人一样说话」

  这两句差别很大，而后者才是用户要的。
""" % (tot, n2))
print("═" * 78)

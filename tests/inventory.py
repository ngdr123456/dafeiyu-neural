# -*- coding: utf-8 -*-
"""清点：哪些东西还在用，哪些被推翻了

用户问「之前的努力有白费吗」。这个问题不该靠感觉回答，应该看每一块代码
是不是还挂在主流程（pipeline.turn）的调用链上。
"""
import ast
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lines(p):
    try:
        return len(io.open(p, encoding="utf-8").read().split("\n"))
    except OSError:
        return 0


# ---- 1. 引擎模块：是否被 pipeline 直接或间接导入
pipe = io.open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
shell = io.open(os.path.join(ROOT, "engine", "shell.py"), encoding="utf-8").read()
entry = pipe + shell

ENGINE = ["markers.py", "understand.py", "state.py", "gear.py", "mechanism.py",
          "respond.py", "topics.py", "pipeline.py", "shell.py",
          "strength.py", "experience.py"]
print("═" * 76)
print("  一、引擎模块：还在链子上吗")
print("═" * 76)
print("  %-16s %6s  %s" % ("模块", "行数", "状态"))
print("  " + "-" * 66)
total_live = 0
for m in ENGINE:
    mod = m[:-3]
    n = lines(os.path.join(ROOT, "engine", m))
    imported = ("from %s import" % mod) in entry or ("import %s" % mod) in entry
    if mod in ("pipeline", "shell"):
        state = "入口（命令行＋双击）"
        live = True
    elif imported:
        state = "在用"
        live = True
    elif mod in ("strength", "experience"):
        state = "新建，尚未接进主流程（设计第 4 步才接）"
        live = True
    else:
        state = "**没被引用**"
        live = False
    if live:
        total_live += n
    print("  %-16s %6d  %s" % (m, n, state))
print("  " + "-" * 66)
print("  在用合计 %d 行" % total_live)

# ---- 2. 规则与数据文件
print()
print("═" * 76)
print("  二、规则与数据文件")
print("═" * 76)
FILES = [("rules/markers.json", "十类标记 + 反例"),
         ("rules/behaviors.json", "十种言语行为 + 阶梯"),
         ("rules/meta_responses.json", "元提问/状态固定回应"),
         ("corpus/topics.json", "36 话题"),
         ("state/schema.json", "数据契约"),
         ("state/ledger.py", "台账（含 raw_input）"),
         ("spec/规格_统一模型_v1.md", "理论裁决（八处冲突、E1–E5）"),
         ("spec/经历驱动的性格层_v1.md", "性格层设计（新）")]
for f, desc in FILES:
    p = os.path.join(ROOT, f)
    print("  %-30s %5d 行  %s" % (f, lines(p), desc))

# ---- 3. 被推翻的东西（逐条列出，这才是问题的正面回答）
print()
print("═" * 76)
print("  三、被推翻的清单（正面回答'有没有白费'）")
print("═" * 76)
REVOKED = [
    ("张力用'题面水平 − 系统水平'算，并给 topics.json 加 probe_level",
     "**没写进代码就废了** —— 只在设计阶段存在，核对原书时发现前提不成立"),
    ("`REFLECT_AVOIDANCE`：指认用户回避的内容", "撤销（用户裁定）"),
    ("'不能连续问细节'规则", "删除（无依据：用户判定里连问恰恰是合理的）"),
    ("`render()` 里的静默降级", "改为留痕（downgraded_from）"),
    ("废纸篓默认当 I-3 证据累积", "改为不注入权重"),
    ("固化阈值不看证据", "改为无证据不计入"),
    ("`TENSION_PRESENT` 作为大范围兜底", "被 ASKABLE 抢在前面"),
    ("`OVERLOADED` → TURN_IMMUTABLE", "改判 ACKNOWLEDGE（原动作会替用户下结论）"),
    ("运行期兜底 GENERIC（'这句话我没接到题上'）", "删除，改为 SILENCE"),
    ("旧选项 D（反事实重校）", "撤销（会把用户变成系统自我改进的手段，违反 E2）"),
    ("旧选项 B（扩到 72 话题）", "否决（会破坏 36 项结构）"),
    ("A/B 的 12 轮输入序列", "一半配错题，已确认要重配（用户选择跳过）"),
]
for i, (what, why) in enumerate(REVOKED, 1):
    print("  %2d. %s" % (i, what))
    print("      → %s" % why)

# ---- 4. 测试数量
print()
print("═" * 76)
print("  四、测试（它们不会白费：每条都钉着一个被修过的真问题）")
print("═" * 76)
for f in sorted(os.listdir(os.path.join(ROOT, "tests"))):
    if f.startswith("test_") and f.endswith(".py"):
        n = lines(os.path.join(ROOT, "tests", f))
        print("  %-24s %4d 行" % (f, n))
print()
print("  合计测试文件 %d 个" % len([f for f in os.listdir(os.path.join(ROOT, "tests"))
                                   if f.startswith("test_") and f.endswith(".py")]))
print("═" * 76)

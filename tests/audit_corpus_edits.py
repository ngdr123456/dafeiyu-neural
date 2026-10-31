# -*- coding: utf-8 -*-
"""反向核查：语料里有多少条被改过期望？改动是否都写明了理由？

目标里有一条硬约束：「不许把巧合包装成成功」。
上一轮我把几条语料期望改成了实际结果，理由写在注释里。
**这个动作本身有风险** —— 如果理由不成立，就变成了"改题去迎合答案"。

本脚本把这类改动全部列出来，供人复核。按行扫，不用正则匹配嵌套元组
（第一版用正则，匹配到 0 条 —— 审计工具自己先错了，这里记下）。
"""
from __future__ import annotations

import io
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(_HERE, "corpus_atoms.py")
lines = io.open(P, encoding="utf-8").read().split("\n")

print("═" * 78)
print("  反向核查：语料里被改过期望的条目")
print("═" * 78)

# 找所有提及"期望改正"或"原期望"的注释行，及其后的第一条数据行
marks = []
for i, l in enumerate(lines):
    st = l.strip()
    if st.startswith("#") and ("期望改正" in st or "原期望" in st or "是我写错" in st
                               or "是我漏看" in st):
        marks.append(i)

print()
print("  找到 %d 处改动说明" % len(marks))
for i in marks:
    print()
    print("  ── 行 %d" % (i + 1))
    j = i
    while j < len(lines) and not lines[j].strip().startswith("#"):
        j += 1
    for k in range(i, min(j, i + 4)):
        if lines[k].strip().startswith("#"):
            print("     理由：%s" % lines[k].strip().lstrip("# ")[:92])
    # 数据行
    k = i
    while k < len(lines) and (lines[k].strip().startswith("#") or not lines[k].strip()):
        k += 1
    if k < len(lines):
        print("     改后：%s" % lines[k].strip()[:92])
        if k + 1 < len(lines):
            print("           %s" % lines[k + 1].strip()[:92])

# 语料条数：数形如 (\"...\" 开始的数据行
total = sum(1 for l in lines if l.strip().startswith('("'))
print()
print("  ── 比例")
print("     语料条目 %d 条，改过期望的 %d 条（约 %.0f%%）"
      % (total, len(marks), 100.0 * len(marks) / total if total else 0))
print()
print("  ⚠️ 这一列必须由人复核：改语料去迎合词表，与「修正写错的期望」，")
print("     在**形式**上完全一样，区别只在理由站不站得住。")
print("═" * 78)

# -*- coding: utf-8 -*-
"""改完就跑：全项目语法 + 中文串里的 ASCII 引号自检。

为什么单独写成文件
────────────────────────────────────────────────────────────
"在中文串里误用 ASCII 双引号" 这个错我在同一轮对话里犯了**六次**，
每次都是改完立刻报 SyntaxError，每次都要重新跑一次检查才发现。

靠记性是没用的 —— 六次已经证明了。所以把它做成一条命令：
**改完任何 .py，先跑这个。** 一秒钟，比第六次踩同一个坑便宜得多。

它查一类：**语法错误**（ast.parse）。

⚠️ 我原本还想顺手查"中文串里混了 ASCII 引号"的可疑行，**但那个检查废掉了**：
   53 个文件报了 225 处，逐条看下来**全是误报**（都在 docstring 或注释里）。
   一个 225 报 225 的检查不是检查，是噪声 —— 而噪声会把真问题埋掉。
   所以只留语法检查：它精确、零误报，而且**六次里六次都正是它抓到的**。
"""
from __future__ import annotations

import ast
import glob
import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

PATTERNS = ("engine/*.py", "tests/*.py", "state/*.py", "tools/*.py", "*.py")


def main() -> int:
    files: list[str] = []
    for pat in PATTERNS:
        files += glob.glob(os.path.join(_ROOT, pat))
    files = sorted(set(f for f in files
                       if os.path.isfile(f) and "__pycache__" not in f))
    bad = 0
    for f in files:
        src = io.open(f, encoding="utf-8", errors="ignore").read()
        try:
            ast.parse(src)
        except SyntaxError as e:
            bad += 1
            print("✗ 语法错误 %s:%d" % (os.path.relpath(f, _ROOT), e.lineno))
            print("     %s" % (e.text or "").strip()[:90])
            print("     ^ 常见原因：中文串里混了 ASCII 双引号 —— 换成「」")
    print("=" * 62)
    print("检查 %d 个文件｜语法错误 %d" % (len(files), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""Q1-Q5：可核对序列**默认不进训练主池**（2026-10-28，Gemini 第四封第 2 条指令）。

★ 事由：`corpus/sequences.json` 的 5 条全是「甲项目押金由李老师收着／丙项目资料放在北楼三层」
  这类"记账"三段式。它有两个后果，实测都发生了：
    ① `session_len == 3` 时 `picks` 一上来就被填满（`while 3 < 3` 一次都不执行）
       ⇒ 100% 抽到 S01–S05 ⇒ **训练池被彻底污染**（那 9 轮全部是 S05）
    ② 会把系统往「查押金、背资料放几楼」的记账员方向训
       ⇒ 与「造一个像人一样思考的系统」背道而驰

★ 判据（先写）：
  Q1 默认 `Trainer()` 的 `use_sequences` 为 False
  Q2 显式 `use_sequences=True` 时才为 True
  Q3 ★ 默认路径下，`run()` 不会加载序列（`sequences` 为空 ⇒ `picks` 全来自 pool）
  Q4 命令行 `--sequences` 开关存在且默认为 False
  Q5 ★ 序列池仍在、仍可被回归测试加载（不是删掉，是**移出主池**）
"""
import argparse
import io
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

import train as T  # noqa: E402

OK = 0
FAIL = 0


def case(name, cond, why=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("  [PASS] 【%s】" % name)
    else:
        FAIL += 1
        print("  [FAIL] 【%s】%s" % (name, why))


print("=" * 78)
print("  可核对序列默认不进训练主池（Q1-Q5）")
print("=" * 78)

# ── Q1 / Q2
#   ★ 显式传 gate_perception：项目有一条 G12 规则 —— test_*.py 里每个构造点都必须显式传，
#     否则环境变量（EGO_GATE_PERCEPTION）一 setx，测试会静默切形态。
t_def = T.Trainer(gate_perception=False, use_api=False)
t_on = T.Trainer(gate_perception=False, use_api=False, use_sequences=True)
case("Q1 默认 use_sequences 为 False", t_def.use_sequences is False,
     "use_sequences=%r" % t_def.use_sequences)
case("Q2 显式 use_sequences=True 才为 True", t_on.use_sequences is True)

# ── Q3 ★ 默认路径不加载序列（查源码里的守卫，不跑真训练）
src = io.open(os.path.join(_ROOT, "engine", "train.py"), encoding="utf-8").read()
case("Q3 ★ run() 里加载序列被 `use_sequences` 守卫住",
     bool(re.search(r"if getattr\(self, \"use_sequences\", False\) and source in "
                    r"\(\"topics\", \"all\"\):", src)))

# ── Q4 命令行开关
m = re.search(r'ap\.add_argument\("--sequences".*?\)\n', src, re.S)
case("Q4 命令行有 --sequences 开关（默认关闭）", bool(m) and "action=\"store_true\"" in (m.group(0) if m else ""))

# ── Q5 ★ 序列池仍在、仍可加载
seqs = T.load_sequences()
case("Q5 ★ 序列池仍在、仍可加载（移出主池，不是删掉）",
     isinstance(seqs, list) and len(seqs) >= 1,
     "load_sequences() → %d 条" % (len(seqs) if isinstance(seqs, list) else -1))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 把默认值改回 True                → Q1")
print("  MUT-B 删掉 run() 里的 use_sequences 守卫 → Q3")
print("  MUT-C 删掉 --sequences 开关             → Q4")
sys.exit(1 if FAIL else 0)

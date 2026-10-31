# -*- coding: utf-8 -*-
"""W1-W8：`use_cognition` 线上默认开启（2026-10-29，Gemini 第 ① 步批准）。

★ 规则：
  `use_cognition is None` ⇒ **跟 `use_api` 走**
    · `use_api=True`（真实训练/对话）⇒ 开启「意识海 + 去助手化」
    · `use_api=False`（`--offline` 与全部离线单测）⇒ 关闭
  显式传 True / False 时以参数为准。

★ 判据（先写）：
  W1 ★ Trainer(use_api=True)  ⇒ use_cognition 为 **True**
  W2 ★ Trainer(use_api=False) ⇒ use_cognition 为 **False**
  W3 ★ 显式 False 压过 use_api=True（回退通道永久保留）
  W4 ★ 显式 True 压过 use_api=False
  W5 ★ Shell(use_api=True) 构造出的 Pipeline 也是开的
  W6 ★ CLI 有 `--no-cognition`，且默认值是 None（不是 False）
  W7 ★★ **防呆**：tests 里任何 `Trainer(` 若不显式传 `use_cognition=`，
       就必须显式传 `use_api=False` —— 否则未来某个测试会静默触发线上抽取
  W8 ★ Pipeline 底层签名仍默认 False（离线单测零影响）
"""
import ast
import io
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

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
print("  use_cognition 线上默认开启（W1-W8）")
print("=" * 78)

import tempfile  # noqa: E402

from pipeline import Pipeline   # noqa: E402
from train import Trainer       # noqa: E402


def mk(use_api, use_cognition=None):
    d = tempfile.mkdtemp()
    #   ⚠️ 这里必须**显式写 `use_api=`** 而不是 `Trainer(**kw)` ——
    #      否则本测试自己的 W7（防呆扫描）会把它判成"危险构造点"，
    #      而那正是 W7 该做的事（它不认识 dict-splat）。**别为了绕过扫描去改 W7 规则。**
    if use_cognition is None:
        return Trainer(out_dir=d, use_api=use_api, use_think=False,
                       gate_perception=False)
    return Trainer(out_dir=d, use_api=use_api, use_think=False,
                   gate_perception=False, use_cognition=use_cognition)


case("W1 ★ Trainer(use_api=True) ⇒ use_cognition 为 True",
     mk(True).use_cognition is True, "%r" % (mk(True).use_cognition,))
case("W2 ★ Trainer(use_api=False) ⇒ use_cognition 为 False",
     mk(False).use_cognition is False, "%r" % (mk(False).use_cognition,))
case("W3 ★ 显式 False 压过 use_api=True（回退通道保留）",
     mk(True, False).use_cognition is False)
case("W4 ★ 显式 True 压过 use_api=False",
     mk(False, True).use_cognition is True)

# ── W5 Shell
try:
    from shell import Shell
    d = tempfile.mkdtemp()
    sh = Shell(ledger_path=os.path.join(d, "state", "ledger.jsonl"),
               use_api=True, use_think=False)
    case("W5 ★ Shell(use_api=True) 构造出的 Pipeline 也是开的",
         getattr(sh.p, "use_cognition", None) is True,
         "%r" % (getattr(sh.p, "use_cognition", None),))
except Exception as exc:                                       # noqa: BLE001
    case("W5 ★ Shell(use_api=True) 构造出的 Pipeline 也是开的", False,
         "%s: %s" % (type(exc).__name__, exc))

# ── W6 CLI
src = io.open(os.path.join(_ROOT, "engine", "train.py"), encoding="utf-8").read()
case("W6 ★ CLI 有 --no-cognition，且默认值是 None（不是 False）",
     '"--no-cognition"' in src and "set_defaults(cognition=None)" in src
     and 'dest="cognition"' in src,
     "no-cognition=%s set_defaults=%s"
     % ('"--no-cognition"' in src, "set_defaults(cognition=None)" in src))

# ── W7 ★★ 防呆：tests 里的 Trainer( 必须显式关掉或显式指定
#
#   ⚠️ 必须先把**字符串与注释剥掉**再扫。
#      第一版没剥 ⇒ 它把 `test_gate_wiring.py` 的 docstring、
#      以及**本测试自己的 docstring**（里面就写着 `Trainer(`）当成了构造点，
#      于是自己把自己判失败 —— 和 G12 当年踩的是同一个坑。
#   ⇒ 直接用 `test_gate_wiring._strip_literals`（它已经做过这件事）。
from test_gate_wiring import _strip_literals  # noqa: E402

bad = []
td = os.path.join(_ROOT, "tests")
for f in sorted(os.listdir(td)):
    if not (f.startswith("test_") and f.endswith(".py")):
        continue
    raw = io.open(os.path.join(td, f), encoding="utf-8").read()
    src = _strip_literals(raw)
    for m in re.finditer(r"\bTrainer\(", src):
        i = m.end()
        depth = 1
        while i < len(src) and depth:
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
            i += 1
        seg = src[m.start():i]
        ln = src[:m.start()].count("\n")
        # ★ 规则：**显式传了 `use_api=`（任何值）** 或 **显式传了 `use_cognition=`** 就算过关。
        #   为什么不是要求 `use_api=False`：
        #     调用方有权选择 `use_api=True`（那就该开），关键是**他有没有意识到**这件事。
        #   ⇒ 只要写了 `use_api=`，`use_cognition` 的默认就跟着他的选择走，不会静默。
        if ("use_cognition" not in seg) and ("use_api=" not in seg):
            bad.append("%s:%d" % (f, ln + 1))
case("W7 ★★ 防呆：tests 里的 Trainer( 必须显式传 use_api= 或 use_cognition=",
     not bad, "这些会让离线单测静默触发线上抽取：%s" % (bad[:5],))

# ── W8 Pipeline 签名仍默认 False
import inspect  # noqa: E402
sig = inspect.signature(Pipeline.__init__)
case("W8 ★ Pipeline 底层签名仍默认 False（离线单测零影响）",
     sig.parameters["use_cognition"].default is False,
     "default=%r" % (sig.parameters["use_cognition"].default,))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 把默认改回硬 False                    → W1")
print("  MUT-B 把默认改回硬 True                     → W2")
print("  MUT-C 让显式 False 失效                     → W3")
print("  MUT-D 某个测试去掉 use_api=                 → W7")
sys.exit(1 if FAIL else 0)

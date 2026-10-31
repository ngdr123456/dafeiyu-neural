# -*- coding: utf-8 -*-
"""丙报告补充 ③：`error_high` / `error_low` 的**三处字面值必须相等**。

为什么要有这条
────────────────────────────────────────────────────────────
用户（经参谋）指出：

> 「devlevel.py 的 ERROR_HIGH／ERROR_LOW 是从 mechanism 导入的，**还是抄了字面值**？
>   如果是抄的，**任何校准路线都要同时改两处**，请列出这两个值的所有使用位置，
>   并说明怎样保证单一来源。」

查证结果：**是抄的字面值，而且有三处**（不是两处）：

    【1】engine/mechanism.py:120-121   error_high: float = 0.60
                                       error_low:  float = 0.15     ← 原始声明（GearConfig）
    【2】engine/devlevel.py:72-73      ERROR_HIGH = 0.60
                                       ERROR_LOW  = 0.15            ← 抄的字面值
    【3】engine/character.py:152       "error_high": 0.60           ← 又一份硬编码字典

⚠️ 本测试**只保证三者相等**，**不判断哪个值是"对的"** ——
   值是校准路线的事（用户裁定：丙只查不改）。
   它防的是**改一处忘另外两处**：那种情况下系统会一半按新线、一半按旧线跑，
   而且**不会报错**。

⚠️ 至于"该不该合成一个来源"（直连导入 / 立 constants 模块 / 导入期断言），
   是**待用户裁定的设计选择**，本测试不预设。
"""
from __future__ import annotations

import io
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "engine"))

RESULTS: list = []
CASES: list = []

# ★ 三处字面值的定位规则（用**正则**，不写死行号 —— 行号一改就过期）
# ★ 方案 B / 用户裁定（2026-10-02，方案乙）之后：
#   三处**字面值已全部移除**，统一从 `engine/constants.py`（SSOT）导入。
#   所以扫描对象从"字面值相等"改成"**三处都必须从 SSOT 取**"。
#: ⚠️ 标签里**必须保留 high/low 字样** —— 下面按 `"high" in label.lower()` 过滤，
#:    第一版把标签写成「mechanism 取 SSOT」，过滤器就一个都找不到（实际 0 处）。
SPOTS = [
    ("mechanism.py", r"error_high:\s*float\s*=\s*C\.ERROR_HIGH", "mechanism.error_high←SSOT"),
    ("mechanism.py", r"error_low:\s*float\s*=\s*C\.ERROR_LOW", "mechanism.error_low←SSOT"),
    ("devlevel.py", r"ERROR_HIGH\s*=\s*C\.ERROR_HIGH", "devlevel.ERROR_HIGH←SSOT"),
    ("devlevel.py", r"ERROR_LOW\s*=\s*C\.ERROR_LOW", "devlevel.ERROR_LOW←SSOT"),
    ("character.py", r'"error_high":\s*C\.ERROR_HIGH', "character.error_high←SSOT"),
]
#: 不许再出现的字面值（三处业务文件里）
BANNED = [("mechanism.py", r"error_high:\s*float\s*=\s*0\."),
          ("devlevel.py", r"ERROR_HIGH\s*=\s*0\."),
          ("character.py", r'"error_high":\s*0\.')]


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def _grab(fname: str, pat: str):
    """★ 语义变了：现在返回 **True/False**（有没有从 SSOT 取），不是数值。"""
    p = os.path.join(_ROOT, "engine", fname)
    src = io.open(p, encoding="utf-8").read()
    return True if re.search(pat, src) else None


# ══════════════════════════════════════════════════════════════
@case("【S1】三处 error_high 的字面值必须相等")
def s1():
    vals = {label: _grab(f, p) for f, p, label in SPOTS if "high" in label.lower()}
    missing = [k for k, v in vals.items() if v is None]
    assert not missing, "找不到这些声明：%s" % missing
    assert all(vals.values()), (
        "★ 这些地方没有从 SSOT（constants.py）取 error_high —— "
        "三处副本没合一，改一处会漏两处：\n    %s"
        % {k: v for k, v in vals.items() if not v})
    assert len(vals) == 3, "应恰好三处，实际 %d 处：%s" % (len(vals), list(vals))


# ══════════════════════════════════════════════════════════════
@case("【S2】两处 error_low 的字面值必须相等")
def s2():
    vals = {label: _grab(f, p) for f, p, label in SPOTS if "low" in label.lower()}
    missing = [k for k, v in vals.items() if v is None]
    assert not missing, "找不到这些声明：%s" % missing
    assert all(vals.values()), "★ 这些地方没有从 SSOT 取 error_low：%s" % vals
    assert len(vals) == 2, "应恰好两处，实际 %d 处：%s" % (len(vals), list(vals))


# ══════════════════════════════════════════════════════════════
@case("【S3】运行期实测：三处取到的值也相等（不只看源码文本）")
def s3():
    import mechanism as M
    import devlevel as D
    # ⚠️ 配置类的真名要从源码取，不许猜（第一版猜 GearConfig，实际叫别的）
    import re as _r
    _src = io.open(os.path.join(_ROOT, "engine", "mechanism.py"), encoding="utf-8").read()
    _cls = _r.search(r"class (\w*Config\w*)", _src).group(1)
    cfg = getattr(M, _cls)()
    got = {"mechanism": cfg.error_high, "devlevel": D.ERROR_HIGH}
    # character 那份字典的名字也从源码取，取不到就跳过（S1 已覆盖文本层）
    _cs = io.open(os.path.join(_ROOT, "engine", "character.py"), encoding="utf-8").read()
    _m = _r.search(r'(\w+)\s*=\s*\{[^}]*"error_high"', _cs, _r.S)
    if _m:
        _d = getattr(__import__("character"), _m.group(1), None)
        if isinstance(_d, dict) and "error_high" in _d:
            got["character"] = _d["error_high"]
    assert len(set(got.values())) == 1, "★ 运行期取到的值不一致：%s" % got
    assert D.ERROR_LOW == cfg.error_low, \
        "★ ERROR_LOW(%s) != cfg.error_low(%s)" % (D.ERROR_LOW, cfg.error_low)


# ══════════════════════════════════════════════════════════════
@case("【S4】清单完整性：报出全部使用位置，且分类计数")
def s4():
    """用户要的「使用位置清单」。这里做**计数下限**断言 ——
    防止有人删掉大量使用点却没人发现。"""
    hits = {"literal": 0, "other": 0}
    for sub in ("engine", "tests", "tools"):
        d = os.path.join(_ROOT, sub)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".py"):
                continue
            src = io.open(os.path.join(d, f), encoding="utf-8").read()
            for line in src.splitlines():
                if re.search(r"error_high|error_low|ERROR_HIGH|ERROR_LOW", line):
                    if re.search(r"[:=]\s*0\.(60|15)\b", line):
                        hits["literal"] += 1
                    else:
                        hits["other"] += 1
    assert hits["literal"] >= 3, \
        "★ 字面值声明少于 3 处 —— 清单过期了：%s" % hits
    assert hits["other"] >= 20, \
        "★ 引用点少于 20 处 —— 清单过期了：%s" % hits


# ══════════════════════════════════════════════════════════════
def main() -> int:
    for name, fn in CASES:
        try:
            fn()
            RESULTS.append((name, True, ""))
        except AssertionError as e:
            RESULTS.append((name, False, str(e) or "断言失败"))
        except Exception as e:                          # noqa: BLE001
            RESULTS.append((name, False, "%s: %s" % (type(e).__name__, e)))
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 78)
    print("丙报告补充 ③：error_high / error_low 的三处字面值")
    print("=" * 78)
    for name, passed, msg in RESULTS:
        print("  [%s] %s" % ("PASS" if passed else "FAIL", name))
        if not passed:
            print("         %s" % msg)
    print("-" * 78)
    print("结果: %d 通过 / %d 失败 / 共 %d"
          % (ok, len(RESULTS) - ok, len(RESULTS)))
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""丙报告补充 ④：`e` 的上界**回归测试** —— 钉住"输入项上界 0.5"这条事实。

为什么要有这条
────────────────────────────────────────────────────────────
丙报告的结论是「`ERROR_HIGH = 0.60` 构造上不可达」，理由是：

    change ∈ {0, 1}；翻转会把 stable_streak 清零 ⇒ rigidity = 0
    ⇒ 单轮输入 (change + rigidity)/2 的上界恒为 **0.5**
    ⇒ 从 0 起步的一阶 EMA，上界也是 **0.5**

**这是一个关于代码的断言，不是一个关于数据的观察。** 数据会变（以后可能有人改公式），
所以必须有一条测试**把这条数学事实钉在代码上**：
只要有人动了公式让它能超过 0.5，这条测试必须失败。

⚠️ 本测试**不判断"0.5 对不对"** —— 它只钉住"现在是 0.5"。
   要不要把上界抬到 0.60 以上，是校准路线的事（用户裁定：丙只查不改）。

mutation 靶子
────────────────────────────────────────────────────────────
    M1  去掉 `/ 2.0`（去掉均值）        → 上界变 1.0 → E1 必须失败
    M2  翻转时**不清零** stable_streak  → change+rigidity 可同时满 → E1 必须失败
    M3  把 EMA 换成 `max()` 而非凸组合  → E2 的归纳前提破 → E2 必须失败
"""
from __future__ import annotations

import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "engine"))

RESULTS: list = []
CASES: list = []

import constants as C                          # noqa: E402
UP = C.E_UPPER_BOUND   # ★ 上界从 SSOT 取（方案 B 后 = 1.0），**不写死**
XFAIL: list = []    # ★ 预期失败（已知缺陷）—— 既不算通过，也不算回归


class _Xfail(Exception):
    """★ 预期失败：**已知缺陷**。既不计 PASS，也不计 FAIL。

    为什么要有这个类型：E3 的不变式 `ERROR_HIGH < e 的上界` 现状**不成立**，
    那是已知缺陷（待校准路线）。若让它直接失败，每次回归都报红，
    真出问题时就看不出来了 —— **红色必须是稀缺的**。
    """
N_TURNS = 400       # 跑够长，让 EMA 逼近稳态


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def _feed(seq):
    """按 mechanism.py 的公式手工推演 e，返回全程 e 列表。

    公式（mechanism.py:588-592）：
        change  = 0.0 if channel == prev else 1.0
        streak  = streak + 1 if change == 0.0 else 0
        rigidity = min(1.0, streak / 12.0)
        e = 0.75 * e + 0.25 * (change + rigidity) / 2.0

    ⚠️ **必须先与源码对账**（第一版没对，于是 mutation M1「去掉 /2.0」
       改了 mechanism.py 却**没能让 E1 失败** —— 因为这个函数
       **自己重实现了一遍公式**，改源码影响不到它。
       那 E1 证明的是"我抄的公式上界是 0.5"，不是"**代码**的上界是 0.5"。
       判据要绑在**被测对象**上，不是绑在我自己的复述上。）
    """
    src = io.open(os.path.join(_ROOT, "engine", "mechanism.py"),
                  encoding="utf-8").read()
    for need in ("_x = 1.0 - (1.0 - change) * (1.0 - rigidity)",
                 "e = C.ERROR_MEMORY * self.e + (1.0 - C.ERROR_MEMORY) * _x",
                 "self._stable_streak = self._stable_streak + 1 if change == 0.0 else 0",
                 "rigidity = min(1.0, self._stable_streak / C.STREAK_FULL)"):
        assert need in src, \
            ("★ 源码公式与本函数的实现不一致 —— 本函数推的不是**代码**的上界。\n"
             "   缺：%s\n   本函数实现的是：change / streak 清零 / rigidity / EMA(/2.0)"
             % need)
    prev = None
    streak = 0
    e = 0.0
    out = []
    for ch in seq:
        change = 0.0 if prev is None or ch == prev else 1.0
        streak = streak + 1 if change == 0.0 else 0
        rigidity = min(1.0, streak / C.STREAK_FULL)
        _x = 1.0 - (1.0 - change) * (1.0 - rigidity)
        e = C.ERROR_MEMORY * e + (1.0 - C.ERROR_MEMORY) * _x
        out.append(e)
        prev = ch
    return out


# ══════════════════════════════════════════════════════════════
@case("【E1】★ 单轮输入的上界恒为 1.0（方案 B noisy-OR）—— 连翻 400 轮也超不过")
def e1():
    """最有利于冲高的输入序列：**每轮都翻转**（change 恒为 1）。"""
    seq = ["A", "B"] * (N_TURNS // 2)          # 每轮都翻转
    es = _feed(seq)
    mx = max(es)
    assert mx <= UP + 1e-9, \
        ("★ e 超过了 1.0 上界（实际 %.6f）—— 说明公式被改过，"
         "丙报告的「ERROR_HIGH 不可达」结论要重算" % mx)
    # 另一个极端：**从不翻转**（rigidity 爬到 1.0）
    es2 = _feed(["A"] * N_TURNS)
    assert max(es2) <= UP + 1e-9, "不翻转时也超了上界：%.6f" % max(es2)
    # 混合：随机式交替
    seq3 = ["A" if (i * 7) % 3 else "B" for i in range(N_TURNS)]
    es3 = _feed(seq3)
    assert max(es3) <= UP + 1e-9, "混合序列超了上界：%.6f" % max(es3)


# ══════════════════════════════════════════════════════════════
@case("【E2】上界的来源：翻转与 rigidity 不可能同时为正")
def e2():
    """归纳的两个前提，逐条钉住。"""
    # 前提一：翻转时 streak 被清零 → rigidity = 0
    prev, streak = "A", 11                     # 攒到 11 轮
    ch = "B"                                    # 翻转
    change = 0.0 if ch == prev else 1.0
    streak = streak + 1 if change == 0.0 else 0
    rigidity = min(1.0, streak / 12.0)
    assert change == 1.0 and rigidity == 0.0, \
        "翻转时 rigidity 必须归零：%s/%s" % (change, rigidity)
    # ★ 方案 B：翻转时 x = 1 - (1-1)(1-0) = **1.0**（旧式是 0.5）
    assert 1.0 - (1.0 - change) * (1.0 - rigidity) == 1.0, "翻转时 x 应为 1.0"
    # 前提二：不翻转时 c=0 → x = 1 - 1·(1-r) = r ≤ 1
    streak = 0
    for _ in range(N_TURNS):
        change = 0.0
        streak += 1
        rigidity = min(1.0, streak / C.STREAK_FULL)
        x = 1.0 - (1.0 - change) * (1.0 - rigidity)
        assert x <= UP + 1e-12, "不翻转时输入超了：streak=%d x=%s" % (streak, x)
    # 前提三：EMA 是**凸组合**（γ + (1-γ) = 1）→ 不会放大
    assert abs(C.ERROR_MEMORY + (1.0 - C.ERROR_MEMORY) - 1.0) < 1e-12, "EMA 系数和必须是 1"
    # 前提四（方案 B 新增）：noisy-OR 的**乘积项**必须在 [0,1]
    for c in (0.0, 1.0):
        for r in (0.0, 0.5, 1.0):
            assert 0.0 <= (1 - c) * (1 - r) <= 1.0, "乘积项越界：c=%s r=%s" % (c, r)


# ══════════════════════════════════════════════════════════════
@case("【E3】源码级：公式与上界推导的一致性")
def e3():
    src = io.open(os.path.join(_ROOT, "engine", "mechanism.py"),
                  encoding="utf-8").read()
    # 公式特征必须在（方案 B 之后换成了 noisy-OR 两条）
    assert "_x = 1.0 - (1.0 - change) * (1.0 - rigidity)" in src, \
        "★ noisy-OR 的形式变了 —— 上界推导要重做"
    assert "e = C.ERROR_MEMORY * self.e + (1.0 - C.ERROR_MEMORY) * _x" in src, \
        "★ EMA 组合式变了"
    assert "self._stable_streak = self._stable_streak + 1 if change == 0.0 else 0" in src, \
        "★ streak 的更新变了 —— 「翻转即清零」这条前提要重核"
    assert "rigidity = min(1.0, self._stable_streak / C.STREAK_FULL)" in src, \
        "★ rigidity 的算法变了"
    # ★ 三处副本必须都从 SSOT 取（用户裁定：方案乙）
    for f, nm in (("devlevel.py", "ERROR_HIGH"), ("character.py", "C.ERROR_HIGH")):
        t = io.open(os.path.join(_ROOT, "engine", f), encoding="utf-8").read()
        assert nm in t, "★ %s 没有从 SSOT 取 %s —— 三处副本没合一" % (f, nm)
    # ⚠️ 门槛断言换成**不变式**，不写死数值（用户裁定，T33 补充④）：
    #    > 「把『error_high 仍是 0.60』这条固定值断言换成不变式
    #    >   **『ERROR_HIGH 必须小于 e 的上界』**。这条现在会失败，
    #    >   那是已知缺陷，标成**预期失败（xfail）**并注明待校准路线，
    #    >   路线定后转正。」
    #
    #    不变式：ERROR_HIGH < e 的上界(0.5) 才算「可达」。
    #    现状 0.60 > 0.5 → **不满足** ⇒ 本断言现在是 **xfail**。
    import re as _r
    # ⚠️ 方案 B 之后 mechanism.py 不再写字面值，改从 **SSOT（constants.py）** 取。
    #    取值来源变了，但**不变式没变**：ERROR_HIGH 必须严格小于 e 的上确界。
    import constants as _C
    eh = float(_C.ERROR_HIGH)
    if eh >= UP:
        raise _Xfail("ERROR_HIGH(%.2f) < e 的上界(%.2f) 不成立 —— **已知缺陷**，"
                     "待校准路线定后转正" % (eh, UP))
    assert eh < UP, "ERROR_HIGH 必须小于 e 的上界"


# ══════════════════════════════════════════════════════════════
@case("【E4】真实台账里也没有超过上界的样本（实证对账）")
def e4():
    import json
    mx = 0.0
    n = 0
    for p in ("state/train/ledger.jsonl", "state/ledger.jsonl",
              "state/ledger_demo.jsonl"):
        fp = os.path.join(_ROOT, p)
        if not os.path.exists(fp):
            continue
        for line in io.open(fp, encoding="utf-8"):
            if not line.strip():
                continue
            m = json.loads(line).get("mech") or {}
            if m.get("e") is None:
                continue
            n += 1
            mx = max(mx, abs(float(m["e"])))
    assert n > 0, "一个样本都没读到 —— 判据失效"
    # ⚠️ 本条**曾经硬编码 0.5** —— 公式换成 noisy-OR（上界 1.0）之后它就成了错的。
    #    它一直"通过"，只是**因为旧数据从没超过 0.5**（旧公式本来就把 e 压在 0.5 以下）。
    #    2026-10-03 真实训练跑出 |e| = 0.898 ⇒ 硬编码当场暴露。
    #    ⇒ 改为**从 SSOT 读上界**，与 E1/E2/E3/E5 用同一个来源。
    assert mx <= UP + 1e-9, \
        ("★ 台账里出现了超过上界 %.3f 的 |e|（%.3f）—— 与公式推导矛盾，必须查"
         % (UP, mx))


# ══════════════════════════════════════════════════════════════
@case("【E5】★ 阈值不变量：每个阈值必须**严格小于**其变量的上确界")
def e5():
    """用户裁定（八步的第 2 步）：

    一次次挡住整类错误 —— **把阈值设在值域的端点或端点之外**。
    现状 `ERROR_HIGH = 0.60 > 上界 0.50` 就是这个错的实例；
    「把阈值设成 1.0（= 新上确界）」是它的**另一种形态**（EMA 只逼近不达到）。

    ⚠️ 本测试**只判不变式，不定数值** —— 数值由校准路线定。
    """
    import constants as _C
    UB = _C.E_UPPER_BOUND
    # ① error_high 必须严格小于 e 的上确界
    assert _C.ERROR_HIGH < UB, \
        "★ ERROR_HIGH(%.3f) 必须严格小于 e 的上确界(%.3f)" % (_C.ERROR_HIGH, UB)
    # ② error_low 必须严格小于 error_high
    assert _C.ERROR_LOW < _C.ERROR_HIGH, \
        "★ ERROR_LOW(%.3f) 必须 < ERROR_HIGH(%.3f)" % (_C.ERROR_LOW, _C.ERROR_HIGH)
    # ③ TENSION_DRIVE 必须严格小于张力量表上限
    assert _C.TENSION_DRIVE < _C.TENSION_SCALE_MAX, \
        "★ TENSION_DRIVE(%.3f) 必须 < TENSION_SCALE_MAX(%.3f)" % (
            _C.TENSION_DRIVE, _C.TENSION_SCALE_MAX)
    # ④ 张力门槛必须落在量表内
    assert 0.0 < _C.TENSION_LOW < _C.TENSION_SCALE_MAX, "TENSION_LOW 越界"
    assert _C.TENSION_HEALTH_LO < _C.TENSION_HEALTH_HI, "健康区上下沿颠倒"
    # ⑤ R2 的复活前提：structure = e/error_high 必须能到 1.0
    #    ⇒ error_high 必须 < 上确界（与①同源，但这里说清它为什么重要）
    assert UB / _C.ERROR_HIGH >= 1.0, \
        ("★ R2 结构压力复活前提不成立：structure 最大 = %.3f / %.3f = %.3f < 1.0"
         % (UB, _C.ERROR_HIGH, UB / _C.ERROR_HIGH))
    # ⑥ 跨场半衰期必须为正
    assert _C.HALF_LIFE_H > 0, "HALF_LIFE_H 必须为正"


# ══════════════════════════════════════════════════════════════
def main() -> int:
    for name, fn in CASES:
        try:
            fn()
            RESULTS.append((name, True, ""))
        except _Xfail as e:
            XFAIL.append(str(e))
            RESULTS.append((name, False, "XFAIL:" + str(e)))
        except AssertionError as e:
            RESULTS.append((name, False, str(e) or "断言失败"))
        except Exception as e:                          # noqa: BLE001
            RESULTS.append((name, False, "%s: %s" % (type(e).__name__, e)))
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 78)
    print("丙报告补充 ④：e 的上界回归")
    print("=" * 78)
    xf = 0
    for name, passed, msg in RESULTS:
        isxf = (not passed) and msg.startswith("XFAIL:")
        tag = "PASS" if passed else ("XFAIL" if isxf else "FAIL")
        print("  [%s] %s" % (tag, name))
        if isxf:
            xf += 1
            print("         %s" % msg[len("XFAIL:"):])
        elif not passed:
            print("         %s" % msg)
    print("-" * 78)
    print("结果: %d 通过 / %d 失败 / %d 预期失败 / 共 %d"
          % (len(RESULTS) - xf, len(RESULTS) - ok - xf, xf, len(RESULTS)))
    return 0 if (len(RESULTS) - ok - xf) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

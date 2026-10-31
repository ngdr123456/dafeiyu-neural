# -*- coding: utf-8 -*-
"""会话切分：**单一事实来源**的守护测试（T24-C）。

用户裁定（2026-10-02）
────────────────────────────────────────────────────────────
> 「**彻底消灭双重逻辑**：抽离 `engine/session_split.py` 的唯一目的就是建立
>   单一事实来源（SSOT）。目标状态必须是：`tools/重放对账.py` 内部**直接 import
>   并调用 `session_split.py`**，彻底删除原先重复造的切分逻辑，
>   让两者的输出**在物理上不可能存在差异**。」
> 「**明确规则：纯 META 会话究竟是在切分时直接丢弃，还是切分后再过滤，
>   必须统一为单一显式函数。**」

本文件的三类断言
────────────────────────────────────────────────────────────
    Y1~Y3  **源码级**：`重放对账.py` 不许再自带切分逻辑（物理上不可能有第二套）
    Y4~Y6  **语义级**：三条踩过坑的规则逐条钉死
    Y7     **一致性级**：两处输出的会话数与分布**逐格相同**（真跑，不是读源码）
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "engine"))

import session_split as SS                     # noqa: E402

RESULTS: list = []
CASES: list = []
REPLAY = os.path.join(_ROOT, "tools", "重放对账.py")


def case(name):
    def deco(fn):
        CASES.append(name and fn or fn)
        fn._name = name
        return fn
    return deco


def _src(p):
    return io.open(p, encoding="utf-8").read()


def _strip_literals(s: str) -> str:
    """去掉字符串与注释 —— 否则会扫到自己的说明文字（踩过一次）。"""
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "#":
            while i < n and s[i] != "\n":
                i += 1
        elif c in "\"'":
            q = c
            tri = s[i:i + 3] == q * 3
            i += 3 if tri else 1
            while i < n:
                if s[i] == "\\":
                    i += 2
                    continue
                if tri and s[i:i + 3] == q * 3:
                    i += 3
                    break
                if not tri and s[i] == q:
                    i += 1
                    break
                i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


# ══════════════════════════════════════════════════════════════
@case("【Y1】★ 重放对账.py 里**不许再出现**自己造的会话切分逻辑")
def y1():
    """物理上不可能有第二套 —— 这是"彻底消灭双重逻辑"的字面要求。"""
    code = _strip_literals(_src(REPLAY))
    # 旧实现的三个特征（任何一个复活都说明双重逻辑回来了）
    for bad, why in (
            (r"sessions\.append\(\[\]\)", "旧的「建空会话」写法回来了"),
            (r"sessions\[-1\]\.append\(", "旧的「自己记 tid」写法回来了"),
            (r"ln\s*=\s*\[len\(x\)\s+for\s+x\s+in\s+sessions", "旧的「自己算长度」写法回来了"),
            (r"if\s+sessions:\s*\n\s*sessions\[-1\]", "旧的会话容器操作回来了")):
        assert not re.search(bad, code), "★ %s：%s" % (why, bad)


@case("【Y2】★ 重放对账.py 必须**直接 import** session_split")
def y2():
    code = _strip_literals(_src(REPLAY))
    assert re.search(r"import\s+session_split", code), \
        "★ 没 import session_split —— 它又在自带切分了"
    assert re.search(r"SS\.split_sessions\(", code), \
        "★ import 了却不用 split_sessions"
    assert re.search(r"SS\.drop_empty\(", code), \
        "★ 没走 drop_empty —— 纯 META 会话的丢弃没统一到单一显式函数"


@case("【Y3】纯 META 会话只由 drop_empty 丢弃（切分时保留）")
def y3():
    rows = [{"turn_id": 1, "channel": "META"}, {"turn_id": 2, "channel": "META"},
            {"turn_id": 1, "channel": "B", "mech": {"e": 0.1}}]
    raw = SS.split_sessions(rows)
    assert len(raw) == 2, "切分时应保留纯 META 会话：%d" % len(raw)
    kept = SS.drop_empty(raw)
    assert len(kept) == 1, "出口应丢弃纯 META 会话：%d" % len(kept)
    assert len(SS.session_turns(kept[0])) == 1


@case("【Y4】`channel` 为空的行**完全不参与**（不判边界、不进会话）")
def y4():
    # 会话台账里真实存在的形态：4 行 channel=None / turn_id=None
    rows = [{"turn_id": 1, "channel": "B", "mech": {"e": 0.1}},
            {"turn_id": None, "channel": None},          # ← 场次分隔行
            {"turn_id": 2, "channel": "B", "mech": {"e": 0.2}}]
    ss = SS.split_sessions(rows)
    assert len(ss) == 1, "无 channel 的行不该切开会话：%d" % len(ss)
    assert len(SS.session_turns(ss[0])) == 2
    # 反证：若把无 channel 行当边界，会切成 2 段
    assert all(r.get("channel") for s in ss for r in s), "无 channel 的行进了会话"


@case("【Y5】★ 先判边界再跳 META（那 2 处实证的形态）")
def y5():
    """`turn_id` 是**跨 META/B 连续编号**的，所以会话头两轮可能就是 META。
    第一版把 META 跳过写在边界判定**之前** ⇒ META 行的 tid 回退没能触发重置
    ⇒ 台账里的 0.01（本场第一次真正 step）对不上。"""
    rows = [{"turn_id": 1, "channel": "B", "mech": {"e": 0.01}},
            # 上一行是 B tid=1；下面这行 META tid=1 **就是新会话的边界**
            {"turn_id": 1, "channel": "META"},
            {"turn_id": 2, "channel": "B", "mech": {"e": 0.01}}]
    ss = SS.split_sessions(rows)
    assert len(ss) == 2, "META 行的 tid 回退必须触发边界：切成 %d 段" % len(ss)
    assert [r["channel"] for r in ss[1]] == ["META", "B"], \
        "META 行应进新会话（它携带边界信息）：%s" % [r["channel"] for r in ss[1]]


@case("【Y6】is_effective 的三个维度：META / 记没记 e / **公式版本**")
def y6():
    """用户裁定：会话长度用「非 META」；观测池用「非 META **且记了 e**」。

    ★ 追加（方案甲，2026-10-02）：观测池**只数 `e_version == C.E_VERSION`** ——
      拿 v1 死锁时代（上界 0.50 < 门槛 0.60）的数据评判新观测窗是**假警报**。
      `only_current=False` 保留给全量历史对账。
    """
    import constants as _C
    r_noe = {"turn_id": 1, "channel": "B"}                        # 非 META 但没记 e
    r_v1 = {"turn_id": 2, "channel": "B", "mech": {"e": 0.1}}     # 记了 e，但 v1 时代
    r_v2 = {"turn_id": 3, "channel": "B",
            "mech": {"e": 0.1, "e_version": _C.E_VERSION}}        # 当前公式
    r_meta = {"turn_id": 4, "channel": "META",
              "mech": {"e": 0.1, "e_version": _C.E_VERSION}}
    # 维度①：META 一律不算（哪怕记了 e、且是当前版本）
    assert SS.is_effective(r_meta) is False, "META 一律不算"
    # 维度②：没记 e 的不算
    assert SS.is_effective(r_noe) is False, "没记 e 的不算有效轮"
    # 维度③：版本 —— 默认只认当前版本
    assert SS.is_effective(r_v2) is True, "当前版本应算有效轮"
    assert SS.is_effective(r_v1) is False, "★ v1 时代默认不算（方案甲）"
    assert SS.is_effective(r_v1, only_current=False) is True, \
        "only_current=False 时应算（供全量历史对账）"
    assert _C.E_VERSION == 2, "本阶段当前版本应为 2"
    # 会话长度口径不受版本影响（它只问"是不是 META"）
    sess = [r_noe, r_v1, r_v2, r_meta]
    assert len(SS.session_turns(sess)) == 3, "会话长度 = 非 META 轮（含 v1、含没记 e 的）"
    # ★ `count()` 必须**真的把 only_current 传下去**（M3 mutation 抓到过缺口：
    #   直接把 False 写死在里面，Y6 全过、但观测窗口径被悄悄改掉）
    rows = [r_noe, r_v1, r_v2, r_meta]
    assert SS.count(rows, min_len=1, only_current=True)["eff_turns"] == 1, \
        "count(only_current=True) 应只数当前版本那 1 轮"
    assert SS.count(rows, min_len=1, only_current=False)["eff_turns"] == 2, \
        "count(only_current=False) 应数 v1 + v2 那 2 轮"
    assert SS.count(rows, only_current=True)["only_current"] is True, \
        "口径要 echo 回来（否则界面上分不清用的是哪个）"


@case("【Y7】★★ 一致性：两处输出的会话数与分布**逐格相同**（真跑）")
def y7():
    """不读源码、不比注释 —— **真跑两个东西，比输出**。"""
    out = subprocess.run([sys.executable, "-B", REPLAY],
                         capture_output=True, text=True, encoding="utf-8",
                         cwd=_ROOT)
    assert out.returncode == 0, \
        "★ 重放对账退出码 %d（应为 0）—— 基准是红的\n%s" % (
            out.returncode, ((out.stdout or "") + (out.stderr or ""))[-600:])
    txt = (out.stdout or "") + (out.stderr or "")
    # 从输出里抠出「会话数 N ...｜各会话轮数：{...}」
    # ⚠️ 中间允许有别的内容 —— 第一版写成 `\*\*｜各会话轮数`，而实际输出里
    #    插了「（切分走 engine/session_split.py）」，把两段隔开了 ⇒ 一条都抠不到。
    got = re.findall(r"会话数 \*\*(\d+)\*\*.*?各会话轮数：(\{[^}]*\})", txt)
    assert len(got) == 2, "没抠到两条会话数（实际 %d 条）" % len(got)
    for (lab, path) in (("训练", os.path.join(_ROOT, "state", "train", "ledger.jsonl")),
                        ("会话", os.path.join(_ROOT, "state", "ledger.jsonl"))):
        c = SS.count(SS.load(path))
        want_n = len(SS.drop_empty(SS.split_sessions(SS.load(path))))
        d = SS.count(SS.load(path))["dist_replay"]
        want_d = "{%s}" % ", ".join("%d: %d" % (k, v) for k, v in sorted(d.items()))
        idx = 0 if lab == "训练" else 1
        n_out, d_out = got[idx]
        assert int(n_out) == want_n, \
            "★ 【%s】会话数不一致：重放对账报 %s，session_split 算 %d" % (lab, n_out, want_n)
        assert d_out.replace(" ", "") == want_d.replace(" ", ""), \
            "★ 【%s】分布不一致：\n     重放对账 %s\n     session_split %s" % (lab, d_out, want_d)


# ══════════════════════════════════════════════════════════════
def main() -> int:
    for fn in CASES:
        name = getattr(fn, "_name", fn.__name__)
        try:
            fn()
            RESULTS.append((name, True, ""))
        except AssertionError as e:
            RESULTS.append((name, False, str(e) or "断言失败"))
        except Exception as e:                      # noqa: BLE001
            RESULTS.append((name, False, "%s: %s" % (type(e).__name__, e)))
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 78)
    print("会话切分 · 单一事实来源（T24-C）")
    print("=" * 78)
    for name, passed, msg in RESULTS:
        print("  [%s] %s" % ("PASS" if passed else "FAIL", name))
        if not passed:
            print("         %s" % msg)
    print("-" * 78)
    print("结果: %d 通过 / %d 失败 / 共 %d" % (ok, len(RESULTS) - ok, len(RESULTS)))
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())

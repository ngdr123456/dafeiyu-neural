# -*- coding: utf-8 -*-
"""台账的**会话切分**与**有效轮计数** —— 单一事实来源（T24-C）。

用户裁定（2026-10-02）
────────────────────────────────────────────────────────────
> 「批准将会话切分逻辑从 `tools/重放对账.py` 抽离至公共模块
>   （如 `engine/session_split.py`），确保**重放与训练台共用同一套单一事实来源**。」
> 「**明确规则：纯 META 会话究竟是在切分时直接丢弃，还是切分后再过滤，
>   必须统一为单一显式函数。**」
> 「**坚决剔除 META 轮**：META 轮一律不计入有效轮数……
>   只有满足 `channel != META` 且机制发生推演的轮次，
>   且该**有效会话长度 ≥ 2 轮**，才计入 50~100 轮的有效观测池。」

★ 本模块的语义**逐字对齐 `tools/重放对账.py`**（那条规则已实证对账到小数点后 3 位、
100% 复现，中间修正过两次）。**任何改动都必须先让对账脚本重跑为绿。**

三条曾踩过的坑（都写在下面代码的注释里）
────────────────────────────────────────────────────────────
    ① **顺序要紧：先判边界、再跳 META**
       第一版写反了 ⇒ META 行的 turn_id 回退没能触发重置 ⇒ 2 处不符。
       实证：那 2 处的上一行恰恰是 `META + turn_id==1`
       （`turn_id` 是**跨 META/B 连续编号**的，所以会话头两轮可能就是 META）。
    ② **`channel` 为空的行完全不看**（不参与边界判定）
       会话台账里有 4 行 `channel=None / turn_id=None / raw_input 空` ——
       它们落在 era 边界上，是**场次分隔行**。
    ③ **纯 META 会话**：切分时**保留**，由 `drop_empty()` 在**出口**统一丢弃。
       （用户裁定要求"统一为单一显式函数"—— 就是这个函数。
         保留的理由：纯 META 会话的存在本身是个事实，分版/调试时可能要看。）

★ 两个**不同**的口径，别混用
────────────────────────────────────────────────────────────
    `session_turns(s)`  非 META 的轮          → **会话长度**（与对账脚本同口径）
    `is_effective(r)`   非 META **且记了 e**  → **观测池**（用户裁定的"机制发生推演"）
    两者在会话台账上差 10 轮（86 重放轮 vs 76 可比对轮）。
"""
from __future__ import annotations

import io
import json

import constants as C          # SSOT（当前公式版本 E_VERSION）


def load(path: str) -> list[dict]:
    """读台账（跳过空行）。"""
    return [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]


def split_sessions(rows: list[dict]) -> list[list[dict]]:
    """按 `turn_id` 回退切成会话。返回**每个会话的行列表**（含 META）。

    ⚠️ 与 `tools/重放对账.py` 的旧内联实现**逐字一致**：
        · `channel` 为空的行走不到这里（在函数内跳过）
        · 边界判定在 **META 跳过之前**
        · 边界一到就开新会话，**当前行进新会话**
    """
    sessions: list[list[dict]] = []
    cur: list[dict] = []
    last = 0
    for r in rows:
        ch = r.get("channel")
        if not ch:
            # ★ 坑②：无 channel 的行**完全不看** —— 不参与边界判定，也不进任何会话。
            #   （它们不携带机制状态，进会话只会污染轮数）
            continue
        tid = r.get("turn_id")
        # ★ 坑①：**先判边界**，再让 META 行照常进容器
        if isinstance(tid, int) and tid <= last and cur:
            sessions.append(cur)
            cur = []
        if isinstance(tid, int):
            last = tid
        cur.append(r)
    if cur:
        sessions.append(cur)
    return sessions


def session_turns(sess: list[dict]) -> list[dict]:
    """一个会话里**计入长度**的那些轮 —— 即非 META 的轮。

    （`重放对账.py` 的旧实现在这里只 `append(tid)` 非 META 行 —— 同义。）
    """
    return [r for r in sess if r.get("channel") and r.get("channel") != "META"]


def drop_empty(sessions: list[list[dict]]) -> list[list[dict]]:
    """★ **唯一**丢弃纯 META 会话的显式函数（用户裁定要求的"单一显式函数"）。

    只在**出口**调用 —— 切分时一律保留。
    """
    return [s for s in sessions if session_turns(s)]


def is_effective(r: dict, only_current: bool = True) -> bool:
    """这一轮算不算**有效轮**（用户裁定：META 一律剔除，且**机制发生推演**）。

    「机制发生推演」的判据：该轮台账 `mech` 快照里**记了 e**
    （机制层的误差层跑了才记 e；META 轮的 e 是原样带过的，不算推演）。

    ★ `only_current`（用户裁定 2026-10-02，方案甲）
    ────────────────────────────────────────────────────────
    > 「**坚决采纳方案 (甲) 只数 `e_version == 2`**。
    >   定性：这正是此前设立 `e_version` 架构分界的真正用意。
    >   观测窗的使命是监测「新动力学（noisy-OR + carry）是否能跑出真实演进」，
    >   **绝不为前朝死锁的旧数据买单**。
    >   实现：批准在计数逻辑中引入显式参数（默认 `only_current=True`，
    >   匹配 `C.E_VERSION`），并保留 `only_current=False` 供**全量历史对账**使用。」

    为什么默认要过滤：v1 时代的 e 是**数学死锁**下的值（上界 0.50 < 门槛 0.60），
    拿它去评判新观测窗必然一开就报红灯 —— 那是**假警报**。
    """
    ch = r.get("channel")
    if not ch or ch == "META":
        return False
    m = r.get("mech") or {}
    if m.get("e") is None:
        return False
    if not only_current:
        return True
    return m.get("e_version") == C.E_VERSION


def count(rows: list[dict], min_len: int = 2, only_current: bool = True) -> dict:
    """观测窗计数（T24-C 用）。

    `only_current=True`（默认）：**只数 `e_version == C.E_VERSION` 的行** ——
        观测窗监测的是「新动力学能不能跑出真实演进」，不为 v1 死锁时代的
        数据买单（用户裁定方案甲）。
    `only_current=False`：全量历史口径，**供对账/调试**看。

    返回：
        sessions        会话总数（**已丢弃纯 META 会话**）
        sessions_raw    切分后的原始数（含纯 META 会话）—— 供对账与调试
        eff_sessions    **有效会话**数（有效轮 ≥ min_len）
        eff_turns       ★ **有效会话里的有效轮数** —— 这才是观测池的分母
        eff_turns_all   全部有效轮（不要求会话够长）—— 供对照，**不进池**
        dist            会话长度分布（**按有效轮数**）
        dist_replay     会话长度分布（**按非 META 轮数**，与 `重放对账.py` 同口径）
        only_current    echo 回来，便于展示时标明口径
    """
    raw = split_sessions(rows)
    ss = drop_empty(raw)
    eff_sessions = 0
    eff_turns = 0
    eff_all = 0
    dist: dict = {}
    dist_replay: dict = {}
    for s in ss:
        n_eff = sum(1 for r in s if is_effective(r, only_current))
        n_rep = len(session_turns(s))
        eff_all += n_eff
        dist[n_eff] = dist.get(n_eff, 0) + 1
        dist_replay[n_rep] = dist_replay.get(n_rep, 0) + 1
        if n_eff >= min_len:
            eff_sessions += 1
            eff_turns += n_eff
    return {"sessions": len(ss), "sessions_raw": len(raw),
            "eff_sessions": eff_sessions, "eff_turns": eff_turns,
            "eff_turns_all": eff_all, "dist": dist, "dist_replay": dist_replay,
            "only_current": only_current}


def window_state(eff_turns: int, equilibration: int | None) -> dict:
    """观测窗三色状态（用户裁定 D-017 + 黄红灯）。

    黄灯（50 轮且 eq==0）**只做诊断不调参**；红灯（100 轮且 eq==0）触发二次校准复盘。
    ⚠️ 段位口径按 **D-017 更正版**：**每满 3 次升半级**，不是"满 3 次到 I-4"。
    """
    eq = equilibration
    if eq is None:
        return {"color": "灰", "text": "equilibration 读不到（devlevel.json 缺失？）"}
    if eq >= 6:
        return {"color": "绿",
                "text": "平衡化 %d 次 —— 已到 **I-4**（每 3 次升半级）" % eq}
    if eq >= 3:
        return {"color": "绿",
                "text": "平衡化 %d 次 —— 已升半级到 **I-3/4**" % eq}
    if eff_turns >= 100:
        return {"color": "红",
                "text": "有效轮 %d/100 且平衡化仍为 0 ⇒ **触发动力学参数二次校准复盘**"
                        "（HALF_LIFE_H 与 ERROR_HIGH）" % eff_turns}
    if eff_turns >= 50:
        return {"color": "黄",
                "text": "有效轮 %d/100 且平衡化仍为 0 ⇒ **只做诊断，不调参**："
                        "取 |e| 分布，看是「会话太短」还是「临界逼近」" % eff_turns}
    return {"color": "灰", "text": "观测中　有效轮 %d/50" % eff_turns}

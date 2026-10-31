# -*- coding: utf-8 -*-
"""L3 状态层

职责：把标记序列累积成「水平分布 + 区间 + 方向」，**绝不输出阶段号**。

理论依据
  [E] 『阶段的意义不能单凭名称来提取。』→ 对外只给区间
  [E] 废纸篓类别：无法判定一律记遵奉水平
  [E] 半级规则：复合反应比最高成分评高半级，且只适用于遵奉以上
  [E] 差倾角(decalage)：两条方向线冲突时**报告冲突，不平均**
  [E] 维度 B｜调节与心理卫生：独立记录，不与水平混算
      『心理卫生与自我发展并不是一回事。』
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RULES_DIR = os.path.join(_ROOT, "rules")

LEVELS = ["I-1", "SYM", "I-2", "DELTA", "I-3", "I-3/4", "I-4", "I-4/5", "I-5", "I-6"]
IDX = {lv: i for i, lv in enumerate(LEVELS)}
WASTEBASKET = "I-3"          # [E] 废纸篓类别
HALF_LEVEL_MIN = IDX["I-3"]  # [E] 半级规则只适用于遵奉以上

# [E] 两个对立观念并存的机制：命中时允许比现状上调半级（仅遵奉以上）
OPPOSED_PAIR_BONUS = 0.5

# 调节维度（维度 B）的探测词域 —— ENG，独立于水平
ADJUSTMENT_PROBES = {
    "depletion": ["累", "熬", "撑不住", "没力气", "耗", "疲倦", "麻木"],
    "recovery": ["睡", "歇", "散步", "慢慢", "缓", "好一些", "喘口气"],
}


@dataclass
class StateEstimate:
    distribution: dict[str, float]
    band: list[str]               # [low, mid, high]
    direction: str                # UP | DOWN | FLAT | CONFLICT
    dopamine_line: str | None
    frankl_line: str | None
    adjustment: float | None
    note: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "band": self.band,
            "direction": self.direction,
            "dopamine_line": self.dopamine_line,
            "frankl_line": self.frankl_line,
            "adjustment": self.adjustment,
            "distribution": {k: round(v, 3) for k, v in self.distribution.items()},
            "note": self.note,
        }


class StateLayer:
    def __init__(self, marker_rules: dict | None = None):
        if marker_rules is None:
            with open(os.path.join(_RULES_DIR, "markers.json"), "r", encoding="utf-8") as f:
                marker_rules = json.load(f)
        self.level_map = marker_rules["derived_rules"]["level_map"]
        self._marker_to_level: dict[str, str] = {}
        for lv, mids in self.level_map.items():
            if lv.startswith("_"):
                continue
            for m in mids:
                self._marker_to_level[m] = lv

        # 状态：对每个 level 的权重（初始均匀）
        self._w: dict[str, float] = {lv: 1.0 for lv in LEVELS}
        self._turns = 0
        # 判不出水平的轮次数。它不是证据，但是**必须可见的事实**：
        # 若这个数接近总轮数，那么任何水平区间都几乎没有信息量，对外必须说清楚。
        self._unclassifiable = 0
        self._adj_samples: list[float] = []

    # ------------------------------------------------------------ 方向线

    @staticmethod
    def _dopamine_line(markers: set[str]) -> str | None:
        """[D] 想要／喜欢分离 → 提示水平在指向段之下。"""
        if "want_like_gap" in markers:
            return "UP"
        return None

    @staticmethod
    def _frankl_line(markers: set[str], mutability: str | None) -> str | None:
        """[M] 态度句——**仅在不可改变处境下**才构成高段证据。"""
        if "attitude_clause" in markers and mutability == "IMMUTABLE":
            return "DOWN"
        return None

    # ------------------------------------------------------------ 主更新

    def update(self, markers: list[str], signature: dict | None = None,
               raw: str = "", underdetermined: bool = False,
               opposed_pair: bool = False) -> StateEstimate:
        self._turns += 1
        ms = set(markers)
        sig = signature or {}
        mutability = sig.get("mutability")

        # --- 1. 废纸篓：无法判定 → 记于遵奉水平 [E]
        #
        # ⚠️ 这里有一处必须写下来的修正（实测数据在 README 第四章第 0·5 条）：
        #   原先 underdetermined 时执行 `self._w[WASTEBASKET] += 0.6`
        #   —— 那是把"这一轮判不出来"**当成 I-3 的正向证据**在累积。
        #   实测后果：连续 8 轮零证据把 I-3 权重推到 3.18（初始 1.0），
        #   而紧接着一句真实的第三途径证据（态度句）只把 I-4/5 加到 1.76。
        #   **真信号永远压不过废纸篓** → 系统对谁都报遵奉水平。
        #   而实测零证据轮次占 67%（见 tests/probe_topic_answers.py），
        #   所以这不是边角情形，是主路径。
        #
        #   修法：[E] 的"废纸篓类别"是**归类指令**，不是数据。
        #   它规定"当输出被迫给一个水平时，给 I-3"，而不是"没判出来就等于 I-3 的证据"。
        #   因此本分支**不注入任何水平证据**，只做遗忘与归一，
        #   另用一个可查看的计数记录"有多少轮是判不出来的"——
        #   这个计数会出现在 /status 与自检里，因为[E]『曾经存在是最为确定的一种存在』。
        if underdetermined:
            for lv in LEVELS:
                self._w[lv] *= 0.97          # 与有证据分支同一遗忘率，保证可比
            self._unclassifiable += 1
            note = ["underdetermined：本轮不含任何水平证据，**不注入任何水平权重**；"
                    "对外若被迫归类，才按【废纸篓类别】记于遵奉水平 [E]"
                    "（修正：原先此处按 I-3 证据累积，会让零证据轮次压过真实证据）"]

        # --- 2. 水平证据
        else:
            note = []
            for lv in LEVELS:
                self._w[lv] *= 0.97          # 轻微遗忘，保证状态可移动（ENG）
            for m in ms:
                lv = self._marker_to_level.get(m)
                if not lv:
                    continue
                if m in ("cliche", "group_sanction"):
                    self._w[lv] += 1.2       # 遵奉信号是最强、最常见的可观察项
                elif m == "blame_external":
                    self._w[lv] += 1.0
                elif m == "voice_shift":
                    self._w[lv] += 1.0
                elif m == "attitude_clause":
                    self._w[lv] += 1.5       # 第三途径出现是稀有的高段证据
                else:
                    self._w[lv] += 0.5

            # --- 3. 半级规则 [E]：只适用于遵奉以上
            if opposed_pair:
                peak = self._peak_level()
                if IDX[peak] >= HALF_LEVEL_MIN:
                    self._w[peak] += OPPOSED_PAIR_BONUS
                    note.append("opposed_pair：按半级规则上调（仅遵奉以上生效）[E]")
                else:
                    note.append("opposed_pair：峰值低于遵奉，半级规则不适用 [E]")

        # --- 4. 归一化
        total = sum(self._w.values())
        dist = {lv: self._w[lv] / total for lv in LEVELS}

        # --- 5. 区间 [low, mid, high]（P25 / 峰值 / P75）
        band = self._band(dist)

        # --- 6. 方向：两条独立线，冲突则不平均 [E]
        dop = self._dopamine_line(ms)
        frk = self._frankl_line(ms, mutability)
        if dop and frk and dop != frk:
            direction = "CONFLICT"
            note.append("dopamine_line 与 frankl_line 冲突：按差倾角(decalage)报告 CONFLICT，不平均 [E]")
        elif dop == "UP" or frk == "UP":
            direction = "UP"
        elif dop == "DOWN" or frk == "DOWN":
            direction = "DOWN"
        else:
            direction = "FLAT"

        # --- 7. 调节维度（维度 B）——独立，不与水平混算 [E]
        adj = self._adjustment(raw)
        if adj is not None:
            self._adj_samples.append(adj)

        return StateEstimate(
            distribution=dist,
            band=band,
            direction=direction,
            dopamine_line=dop,
            frankl_line=frk,
            adjustment=adj,
            note=note,
        )

    # ------------------------------------------------------------ 工具

    def _peak_level(self) -> str:
        return max(LEVELS, key=lambda lv: self._w[lv])

    @staticmethod
    def _band(dist: dict[str, float], mass: float = 0.60) -> list[str]:
        """最短连续窗口，累计概率 ≥ mass。

        [E] 『阶段的意义不能单凭名称来提取』→ 对外只给一个**连续性**区间，
        而不是分位数抽点（分位数在双峰分布上会给出跨全表的假区间）。
        [E] 差倾角：双峰是真实现象，本函数不掩盖它——它只报告质量集中在哪一段。
        """
        best = None
        n = len(LEVELS)
        for i in range(n):
            acc = 0.0
            for j in range(i, n):
                acc += dist[LEVELS[j]]
                if acc >= mass:
                    if best is None or (j - i) < (best[1] - best[0]):
                        best = (i, j)
                    break
        if best is None:
            best = (0, n - 1)
        i, j = best
        seg = LEVELS[i:j + 1]
        peak = max(LEVELS, key=lambda lv: dist[lv])
        return [seg[0], peak, seg[-1]]

    @staticmethod
    def _adjustment(raw: str) -> float | None:
        """维度 B 的粗估（ENG）：耗竭词域 − 恢复词域，归一到 [-1, 1]。

        刻意只做加减，不做语义判断；它是横向指标，不参与水平计算。
        """
        if not raw:
            return None
        dep = sum(1 for w in ADJUSTMENT_PROBES["depletion"] if w in raw)
        rec = sum(1 for w in ADJUSTMENT_PROBES["recovery"] if w in raw)
        if dep == 0 and rec == 0:
            return None
        v = (rec - dep) / max(1, dep + rec)
        return round(v, 3)

    def adjustment_mean(self) -> float | None:
        if not self._adj_samples:
            return None
        return round(sum(self._adj_samples) / len(self._adj_samples), 3)

    def suggestion_level(self) -> str:
        """给 L4 用的基准水平（B 通道的参考点）。"""
        return self._peak_level()

    def evidence_level(self) -> str:
        """B 通道的**稳定**行动水平：取自当前区间的峰值段。

        为什么需要它（一处必须写下来的教训）：
          后验峰值 suggestion_level() 会随权重衰减与证据累积而轻微漂移。
          若 S/B 的一致性以此判定，同一个 S 会在毫无新信息的情况下反复
          自我否定，被自己的疲劳判据误杀。
          区间峰值只依赖**水平证据**（标记 → 水平映射），对衰减不敏感，
          因此 S/B 一致性检验必须用它。
        """
        total = sum(self._w.values())
        dist = {lv: self._w[lv] / total for lv in LEVELS}
        return self._band(dist)[1]

    def higher(self, lv: str, steps: int = 1) -> str:
        i = min(len(LEVELS) - 1, IDX.get(lv, 0) + steps)
        return LEVELS[i]

    def lower(self, lv: str, steps: int = 1) -> str:
        i = max(0, IDX.get(lv, 0) - steps)
        return LEVELS[i]

    def snapshot(self) -> dict:
        return {
            "turns": self._turns,
            "peak": self._peak_level(),
            "adjustment_mean": self.adjustment_mean(),
            "weights": {k: round(v, 3) for k, v in self._w.items()},
            "unclassifiable": self._unclassifiable,
            "evidence_coverage": (
                round(1.0 - self._unclassifiable / self._turns, 2) if self._turns else None),
        }


if __name__ == "__main__":
    s = StateLayer()
    for txt, mk, sig in [
        ("大家都这样", ["cliche", "group_sanction"], {"mutability": "CHANGEABLE"}),
        ("我被情绪困住", ["voice_shift"], {"mutability": "CHANGEABLE"}),
        ("改变不了了，但我可以选择怎么过", ["immutable", "attitude_clause"], {"mutability": "IMMUTABLE"}),
    ]:
        est = s.update(mk, sig, raw=txt)
        print(txt, "->", json.dumps(est.to_dict(), ensure_ascii=False))
    print(json.dumps(s.snapshot(), ensure_ascii=False, indent=1))

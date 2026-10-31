# -*- coding: utf-8 -*-
"""L4 档位引擎：S / B / 门控 / 疲劳 / 试探性并行

理论依据
  [E] 洛华德：『遵守大小便规则不再被体验为一种意向或要求，而成了一种习惯。
      当一种意向成为现实时，超我的诸成分就同化为自我的诸成分。』→ 这就是 S
  [E] 大多数人『稳定在远远低于……的某个阶段上。这一事实意味着平衡使他们稳定在那个阶段上。』→ 这就是档位
  [E] 『一个在遵奉量表上得分较低的人可能是前遵奉者或后遵奉者。』→ 这就是门控存在的理由
  [D] 预期连续落空时多巴胺放电率由 20–30 次/秒降至 0 → 疲劳判据测的是预测命中率，不是省下的算力

诚实声明（写进代码，不写进注释就会被忘掉）
  · 跳档 ≠ 上升。档位间由外部噪声驱动的链是遍历的，长期分布平稳。
  · 方向只能由外部提供；系统不负责让人发展，只负责不浪费发生在人身上的意外。
"""
from __future__ import annotations

import itertools
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any

_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RULES_DIR = os.path.join(_ROOT, "rules")


# ------------------------------------------------------------------ 配置

@dataclass
class GearConfig:
    epsilon: float = 0.34          # 疲劳阈值（ENG，初值待调）
    k_recent: int = 5              # 窗口一致率的窗口长度（ENG）
    age_rate: float = 0.05         # 每轮年龄因子增量（ENG）
    parallel_rounds: int = 2       # 试探性并行的轮数（ENG）
    evidence_threshold: int = 3    # 固化阈值 A（ENG）
    fallback_rounds: int = 3       # 连续无进展轮数 → 降到 L-1（ENG）
    weight_decay: float = 0.02     # 每轮衰减（ENG）


# ------------------------------------------------------------------ 数据结构

@dataclass
class SRecord:
    sid: str
    key: str
    action_level: str
    born_at_turn: int
    evidence_count: int = 1
    hits: int = 0
    last_hit_turn: int | None = None
    verify_failures: int = 0
    age_factor: float = 0.0
    weight: float = 1.0
    status: str = "active"
    consistency: list[bool] = field(default_factory=list)
    channel_rules: list[str] = field(default_factory=lambda: ["S:habit"])

    @property
    def recent_consistency(self) -> float:
        if not self.consistency:
            return 1.0
        return sum(1 for x in self.consistency if x) / len(self.consistency)

    @property
    def fatigue(self) -> float:
        """F(S) = (1 - 最近一致率) × (1 + 年龄因子)"""
        return (1.0 - self.recent_consistency) * (1.0 + self.age_factor)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["recent_consistency"] = round(self.recent_consistency, 3)
        d["fatigue"] = round(self.fatigue, 3)
        return d


@dataclass
class Gear:
    gear_id: str
    level: str
    active_S: list[str] = field(default_factory=list)
    entered_at_turn: int = 0
    dwell_turns: int = 0
    exits: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Decision:
    turn_id: int
    topic_id: str | None
    signature_key: str | None
    channel: str                   # S | B | S+B(试探)
    level: str                     # 本次回应的基准水平
    gear: Gear
    s_used: str | None
    fatigue: float | None
    nudge: str | None              # None | "UP" | "DOWN"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["gear"] = self.gear.to_dict()
        return d


# ------------------------------------------------------------------ 引擎

class GearEngine:
    def __init__(self, state_layer, config: GearConfig | None = None, rules_dir: str | None = None):
        self.state = state_layer
        self.cfg = config or GearConfig()
        self._counter = itertools.count(1)
        self._S: dict[str, SRecord] = {}
        self._by_key: dict[str, str] = {}          # key -> sid
        self._pending: dict[str, int] = {}         # key -> 已见次数（尚未固化）
        self._gear = Gear(gear_id="G0", level=state_layer.suggestion_level(), entered_at_turn=0)
        self._gear_seq = itertools.count(1)
        self._no_progress = 0
        self._last_peak: str | None = None
        self._seen_markers: set[str] = set()
        # 试探性并行：sid -> 剩余轮数
        self._trial: dict[str, int] = {}

        rules_dir = rules_dir or _RULES_DIR
        with open(os.path.join(rules_dir, "markers.json"), "r", encoding="utf-8") as f:
            self._marker_rules = json.load(f)

    # -------------------------------------------------------- 门控（O(1)）

    @staticmethod
    def signature_family(key: str) -> str:
        """同族判定 = 四字段逐个相等。不做模糊匹配。"""
        return key  # 键本身就是族标识；比较即相等判断

    def _find_S(self, key: str) -> SRecord | None:
        sid = self._by_key.get(key)
        if not sid:
            return None
        rec = self._S[sid]
        if rec.status != "active":
            return None
        if rec.fatigue > self.cfg.epsilon:
            rec.status = "decayed"          # 挂起（不删除）
            return None
        return rec

    # -------------------------------------------------------- 固化

    def _maybe_bootstrap(self, key: str, level: str, turn_id: int) -> SRecord | None:
        n = self._pending.get(key, 0) + 1
        self._pending[key] = n
        if n < self.cfg.evidence_threshold:
            return None
        sid = "S%d" % next(self._counter)
        rec = SRecord(sid=sid, key=key, action_level=level,
                      born_at_turn=turn_id, evidence_count=n)
        self._S[sid] = rec
        self._by_key[key] = sid
        return rec

    # -------------------------------------------------------- 主决策

    def decide(self, turn_id: int, topic_id: str | None, signature_key: str,
               markers: list[str], peak_level: str, underdetermined: bool = False) -> Decision:
        notes: list[str] = []
        ms = set(markers)
        sig_key = signature_key or (topic_id or "NA")

        # ---------- 1. 无进展计数（用于 fallback，不用于加难）
        progressed = (peak_level != self._last_peak) or bool(ms - self._seen_markers)
        if progressed:
            self._no_progress = 0
        else:
            self._no_progress += 1
        self._last_peak = peak_level
        self._seen_markers |= ms

        # ---------- 2. 档位推进（离散跳转，不保证上升）
        if peak_level != self._gear.level:
            self._gear.exits += 1
            self._gear = Gear(
                gear_id="G%d" % next(self._gear_seq),
                level=peak_level,
                entered_at_turn=turn_id,
            )
            notes.append("档位切换 → %s（跳档不等于上升）" % peak_level)
        self._gear.dwell_turns += 1

        # ---------- 3. 找 S
        rec = self._find_S(sig_key)
        b_level = peak_level
        b_reason = "B:full-path"

        if rec is not None:
            rec.hits += 1
            rec.last_hit_turn = turn_id
            rec.age_factor += self.cfg.age_rate
            rec.weight = max(0.0, rec.weight - self.cfg.weight_decay)
            s_level = rec.action_level

            # ---------- 4. 试探性并行：B 低权重跑 parallel_rounds 轮
            consistent = (s_level == b_level)
            rec.consistency.append(consistent)
            if len(rec.consistency) > self.cfg.k_recent:
                rec.consistency = rec.consistency[-self.cfg.k_recent:]

            if consistent:
                rec.weight += 0.15
                self._trial.pop(rec.sid, None)
                return Decision(turn_id, topic_id, sig_key, "S", s_level,
                                self._gear, rec.sid, round(rec.fatigue, 3), None,
                                notes + ["S/B 一致 → S 生效，权重上升"])
            else:
                # 不一致：退回 S 并降权；连续不一致由疲劳值累积触发切换
                rec.verify_failures += 1
                rec.weight = max(0.0, rec.weight - 0.25)
                self._trial[rec.sid] = self.cfg.parallel_rounds
                return Decision(turn_id, topic_id, sig_key, "S+B(试探)", b_level,
                                self._gear, rec.sid, round(rec.fatigue, 3), "UP",
                                notes + ["S/B 不一致 → 以 B 为准，S 降权；F(S)=%.3f/ε=%.2f"
                                         % (rec.fatigue, self.cfg.epsilon)])

        # ---------- 5. 无 S：走 B，并尝试固化
        #
        # ⚠️ 固化门槛必须要求**本轮真的有证据**（实测数据见 README 第四章第 0·6 条）。
        #   原先不看证据：同一句话（如"今天天气还行"）重复 A=3 次就生成 S1，
        #   而那句话命中 0 个标记 —— 等于把"没有观察"固化成了一条"行为习惯"。
        #   实测后果：连续 8 轮无标记输入后，系统声称获得了 S1，并进入 S 通道。
        #   依据 [E]：S 对应『遵守大小便规则不再被体验为一种意向或要求，而成了一种习惯』——
        #   习惯是**观察到的行为**，不是观察的缺席。
        if underdetermined or not ms:
            notes.append("本轮无水平证据 → **不计入固化阈值 A**（固化需要观察到行为，"
                         "而非观察的缺席）")
            rec2 = None
        else:
            rec2 = self._maybe_bootstrap(sig_key, b_level, turn_id)
        if rec2 is not None:
            notes.append("越过固化阈值 A=%d → 生成 %s（[E] 意向成为习惯）"
                         % (self.cfg.evidence_threshold, rec2.sid))
            self._gear.active_S.append(rec2.sid)

        # ---------- 6. fallback：连续无进展 → 降到 L-1（而非加大难度）
        nudge = None
        if self._no_progress >= self.cfg.fallback_rounds:
            self._no_progress = 0
            nudge = "DOWN"
            notes.append("连续 %d 轮无进展 → 降到 L-1（[E] 匹配律：对低水平者加大难度效果相反）"
                         % self.cfg.fallback_rounds)

        if underdetermined:
            notes.append("underdetermined → 遵奉水平兜底 [E]，本通道仅供记录")

        return Decision(turn_id, topic_id, sig_key, "B", b_level,
                        self._gear, None, None, nudge, notes)

    # -------------------------------------------------------- 自检与快照

    def snapshot(self) -> dict:
        return {
            "gear": self._gear.to_dict(),
            "S_count": len(self._S),
            "S_active": sum(1 for r in self._S.values() if r.status == "active"),
            "S_decayed": sum(1 for r in self._S.values() if r.status == "decayed"),
            "no_progress_streak": self._no_progress,
            "S": [r.to_dict() for r in self._S.values()],
            "pending": dict(self._pending),
            "honest_note": [
                "跳档 ≠ 上升：档位链遍历，长期分布平稳",
                "方向只能由外部提供",
                "L6 只记录访问频率与停留时长，放弃进步曲线叙事",
            ],
        }


if __name__ == "__main__":
    from state import StateLayer
    st = StateLayer()
    ge = GearEngine(st)
    print(json.dumps(ge.snapshot(), ensure_ascii=False, indent=1)[:600])

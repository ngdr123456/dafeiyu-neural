"""第一期旁路模块的工程师通道类型（字段对齐 PHASE1_BRIEF.md）。

原则：
- 这些 dataclass 只是「仲裁 → 开口」链条的台下信号载体，不是性格、不是分数。
- DriveSignal.direction 允许为 None——动力留空本身就是一个信号，不是缺省。
- ThoughtBrief.dominant 只有 drive|meaning|org 三种，冲突时写明主导。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional

Direction = Optional[Literal["pursue", "guard", "hold"]]
Salience = Literal["low", "mid", "high"]
Posture = Literal["yieldable", "non_negotiable", "needs_clarify"]
Grain = Literal["simple", "rule", "differentiated"]
Dominant = Literal["drive", "meaning", "org"]


@dataclass
class DriveSignal:
    """动力层最小信号：direction 可留空；why 允许好奇类理由；禁止装饰分数。"""

    direction: Direction = None
    salience: Salience = "low"
    why: str = ""


@dataclass
class StanceSignal:
    """立场最小信号：默认能回话；non_negotiable 只在不能装的时候出现。"""

    posture: Posture = "yieldable"
    stake: str = ""
    why: str = ""


@dataclass
class OrgConstraint:
    """组织约束：只约束表达粒度（grain），不永久否决动力。"""

    grain: Grain = "simple"
    can_name: List[str] = field(default_factory=list)
    cannot_fake: List[str] = field(default_factory=list)
    why: str = ""


@dataclass
class ThinContext:
    """薄情境：同场（同一 session）可积累；显式 new session 才清空。

    不做每句改性格，也不顶置长期性格记忆——只放本轮要用的东西。
    """

    session_ok: bool = True
    open_questions: List[str] = field(default_factory=list)
    last_commitments: List[str] = field(default_factory=list)
    facts_this_session: List[str] = field(default_factory=list)
    # 结构化：同场好奇挂起仍 pending（pipeline 写；drive 主路径读；勿靠「待接的话头：」前缀）
    curiosity_hang_pending: bool = False


@dataclass
class ThoughtBrief:
    """一条时间步的完整思想简报：仲裁的输出、开口的唯一依据。"""

    dominant: Dominant
    drive: Optional[DriveSignal] = None
    stance: StanceSignal = field(default_factory=StanceSignal)
    org: OrgConstraint = field(default_factory=OrgConstraint)
    context: ThinContext = field(default_factory=ThinContext)
    say_intent: str = ""
    must_not_pretend: List[str] = field(default_factory=list)
    # 本轮实际命中的 cannot_fake 条目（常驻底线之外额外踩到的；
    # 开口层按它略分 org 口径，不做禁词）
    org_conflicts: List[str] = field(default_factory=list)
    # 结构化：本轮因悬问说过话，开口后应 resolve（勿靠 say_intent 中文子串）
    openq_resolve: bool = False
    # 结构化：本轮好奇挂起 → pipeline 写「待接的话头」（勿再扫 CURIOSITY_MARKS）
    openq_curiosity_hang: bool = False
    # 结构化：本轮用户明示放下／真开新话头 → 开口后 clear 悬问（pipeline 勿再扫放下词表）
    openq_clear: bool = False
    # 结构化：本轮用户催可核对约定（articulate 拒空壳／stub 模板读此标记）
    press_commit: bool = False
    # 结构化：用户示意约定已兑现 → 开口后 resolve
    commit_resolve: bool = False
    # 结构化：本轮守着 pending 承诺，台上开口可交付主题则 resolve
    commit_deliverable: bool = False
    # 用户话已点到 pending 主题（可检验「接着交付」意图，非仅守诺）
    commit_deliver_intent: bool = False
    # 有 pending 时本轮 drive 明确收束／好奇：say_intent 双写动力+薄守诺（勿靠中文子串门控）
    commit_hold_with_drive: bool = False

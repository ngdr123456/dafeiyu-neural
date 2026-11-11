"""旁路模块的工程师通道类型（字段对齐 PHASE1_BRIEF.md）。

原则：
- 这些 dataclass 只是「仲裁 → 开口」链条的台下信号载体，不是性格、不是分数。
- DriveSignal.direction 允许为 None——动力留空本身就是一个信号，不是缺省。
- ThoughtBrief.dominant 只有 drive|meaning|org 三种，冲突时写明主导。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Literal, Optional

if TYPE_CHECKING:
    from .input_contract import InputSignal

Direction = Optional[Literal["pursue", "guard", "hold"]]
Salience = Literal["low", "mid", "high"]
Posture = Literal["yieldable", "non_negotiable", "needs_clarify"]
Grain = Literal["simple", "rule", "differentiated"]
Dominant = Literal["drive", "meaning", "org"]


class DriveReason:
    """动力判定的结构化理由（V2.1）：层间读 reason，why 只留给记录／调试。"""

    BYPASS = "bypass"                          # 工程师旁路
    SESSION_NOT_OK = "session_not_ok"          # 新场未接上
    INPUT_PAUSE = "input_pause"                # 输入信号｜暂停｜
    INPUT_STOP = "input_stop"                  # 输入信号｜终止｜
    INPUT_ANSWERED = "input_answered"          # 输入理解｜答复悬问｜
    INPUT_ASK = "input_ask"                    # 输入信号｜问句｜…缺口在外
    INPUT_REQUEST = "input_request"            # 输入信号｜请求｜…缺口在外
    INPUT_TASK = "input_task"                  # 输入信号｜请求｜…接住具体任务
    IDENTITY_ASK_CLUE = "identity_ask_clue"    # 身份询问｜已有对方线索
    IDENTITY_ASK_NO_CLUE = "identity_ask_no_clue"
    IDENTITY_ANSWER = "identity_answer"        # 身份回应｜
    COMMITMENT_GUARD = "commitment_guard"      # 同场有没兑现的话…（已有要护）
    WANT_SEEN_WAITING = "want_seen_waiting"    # 想被看见｜
    WANT_SEEN_SATISFIED = "want_seen_satisfied"  # 被看见了｜
    OPENQ_SATISFIED = "openq_satisfied"        # 悬问被接住|喜欢/满足…不必再追
    BODY_IMAGINE = "body_imagine"              # 身体想象｜
    OPEN_QUESTION_PICKUP = "open_question_pickup"  # 同场还有悬而未决的问题（…）
    GREET = "greet"                            # 招呼类开场
    SATISFIED = "satisfied"                    # 喜欢/满足侧已接住，不必再追
    OPEN_TOPIC = "open_topic"                  # 缺口在外、想要打开这一话头（…）
    CURIOSITY = "curiosity"                    # 好奇
    DISAPPOINT = "disappoint"                  # 重复空追（guard）
    EMPTY_STAGE = "empty_stage"                # 重复空追（hold）
    TOPIC_CONTINUE = "topic_continue"          # 顺着本场已打开的想要继续（…）
    PRIOR_HER_QUESTION = "prior_her_question"  # 上场她问出去的一句…
    SESSION_CALLBACK = "session_callback"      # 回指同场／本场已有痕迹接
    PRIOR_PRESS = "prior_press"                # 上场承诺｜用户催兑现
    PRIOR_CALLBACK = "prior_callback"          # 回指上一场
    PRIOR_COMMIT_HOLD = "prior_commit_hold"    # 上场还有未兑现的话
    REJECT_HOLD = "reject_hold"                # 开口拒收回流｜同场多次
    FILLER_NONE = "filler_none"                # 这一句没有推力
    STATEMENT_NONE = "statement_none"          # 陈述类的话，没有明显推力方向

    STOP = frozenset({INPUT_PAUSE, INPUT_STOP})
    REQUEST = frozenset({INPUT_REQUEST, INPUT_TASK})
    SATISFIED_SIDE = frozenset({SATISFIED, OPENQ_SATISFIED})
    EMPTY_CHASE = frozenset({DISAPPOINT, EMPTY_STAGE})
    OPEN_GAP = frozenset({OPEN_TOPIC, INPUT_ASK, INPUT_REQUEST})


@dataclass(frozen=True)
class InjectedCues:
    """本轮注入线索（V2.1）：上游/测试显式给 pipeline.turn 的结构化覆盖，一个对象传入。

    语义逐字沿用旧 structured_* kwarg：
    - 标 ``bool | None`` 的是三态：None=走词表/固定线索兜底；True/False=显式覆盖（False 可否决误命中）。
    - 标 ``bool`` 的是两态（旧签名即如此）：True=显式置；False=无结构，走词表兜底
      （marks_fallback=not bool(cue)）。不是否决——为保持行为不变，未升级为三态。
    """

    commit_deny: bool = False
    drive_greet: bool = False
    drive_hold: bool = False
    openq_answered: bool | None = None
    want_seen: bool | None = None
    want_seen_answered: bool | None = None
    want_seen_hang: bool | None = None
    drive_curiosity: bool = False
    drive_open_topic: bool = False
    drive_disappoint: bool = False
    drive_empty_stage: bool = False
    drive_topic_continue: bool = False
    drive_callback: bool = False
    drive_identity_ask: bool = False
    stance_attitude: bool | None = None
    body_imagine: bool | None = None
    stance_necessary_pain: bool | None = None
    stance_self_torture: bool | None = None


@dataclass
class DriveSignal:
    """动力层最小信号：direction 可留空；why 允许好奇类理由；禁止装饰分数。

    V2.1：reason（DriveReason）、topic（判定所指对象）、holds_commitment（判停／答复时同场承诺仍在）
    是层间协议；why 只留给记录／调试，下游不得做子串判断或切片。
    """

    direction: Direction = None
    salience: Salience = "low"
    why: str = ""
    reason: str = ""
    topic: str = ""
    holds_commitment: bool = False
    prior_her_question: bool = False
    prior_her_question_text: str = ""
    judgment_effective: tuple[SessionJudgment, ...] = ()
    action_feedback_effective: tuple[ActionFeedback, ...] = ()


@dataclass
class StanceSignal:
    """立场最小信号：默认能回话；non_negotiable 只在不能装的时候出现。"""

    posture: Posture = "yieldable"
    stake: str = ""
    why: str = ""
    # 结构化：本轮守同场承诺（stance_org 写；arbitrate／articulate／commit_extract 读；
    # 勿以用户可见 stake 中文串作唯一闸。stake 仍可写成 STAKE_HOLD_SAME_FIELD 作字段取值）
    hold_same_field: bool = False
    reasserts_kept: bool = False
    # 本轮实际守住的那一笔同场承诺原文；空表示没有可信且唯一的同场目标，
    # 消费侧不得猜成其他笔。
    held_commitment: str = ""


@dataclass
class OrgConstraint:
    """组织约束：只约束表达粒度（grain），不永久否决动力。"""

    grain: Grain = "simple"
    can_name: List[str] = field(default_factory=list)
    cannot_fake: List[str] = field(default_factory=list)
    why: str = ""
    # 组织层识别的不能假装命中项；旧构造为空时仲裁才兼容兜底。
    conflicts: List[str] = field(default_factory=list)


@dataclass
class HerUtterance:
    text: str
    drive_direction: str
    stance_posture: str
    org_grain: str
    source: str
    complete: bool = False  # Missing in old ledgers: completeness is unknown.


@dataclass(frozen=True)
class RecallEvidence:
    text: str
    session: str
    ended_at: str
    complete: bool
    # multiple 时携带问句列表；unique/no_match 保持空元组。
    questions: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecallResult:
    status: Literal["not_requested", "unique", "no_match", "multiple", "unavailable"]
    evidence: Optional[RecallEvidence] = None


@dataclass(frozen=True)
class SessionAction:
    text: str
    goal: str


@dataclass(frozen=True)
class ActionFeedback:
    action: str
    action_order: int
    evidence: str
    span: str
    scope: str
    effect: str
    relation: str
    previous: str = ""
    source: str = "user_report"
    interpreter: str = ""


@dataclass(frozen=True)
class SessionJudgment:
    evidence: str
    span: str
    holder: str
    subject: str
    content: str
    relation: str = "initial"
    previous: str = ""


@dataclass
class StanceTrace:
    """一条真守住过的取舍点（结构化标识；同场／跨场只用于连续性，不是语义匹配）。"""

    kind: Literal["kept"]
    point: str
    why: str = ""


@dataclass
class CommitmentCandidate:
    text: str
    target: str
    frame: Literal["prior_press", "same_session_press"]
    source: str = ""


@dataclass
class PriorSessionTrace:
    """上一场薄痕迹（跨场读入；非长期人格／非意识海）。

    由 memory 持久层在新场开局灌入 ThinContext.prior_session；
    回指／drive 线索只读结构字段，不拼进 say_intent。
    """

    facts: List[str] = field(default_factory=list)
    commitments_pending: List[str] = field(default_factory=list)
    commitments_resolved: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    ended_at: str = ""
    stance_traces: List[StanceTrace] = field(default_factory=list)
    her_questions: List[str] = field(default_factory=list)

    commitment_candidates: List[CommitmentCandidate] = field(default_factory=list)
    record_metadata: dict | None = None

    def has_trace(self) -> bool:
        return bool(
            self.facts
            or self.commitments_pending
            or self.commitments_resolved
            or self.open_questions
            or self.her_questions
            or self.stance_traces
            or self.commitment_candidates
        )


@dataclass
class ThinContext:
    """薄情境：同场（同一 session）可积累；显式 new session 才清空。

    不做每句改性格，也不顶置长期性格记忆——只放本轮要用的东西。
    prior_session 为跨场读入的上一场薄痕迹（结构字段，可空）。
    """

    session_ok: bool = True
    open_questions: List[str] = field(default_factory=list)
    her_questions: List[str] = field(default_factory=list)
    last_commitments: List[str] = field(default_factory=list)
    commitment_candidates: List[CommitmentCandidate] = field(default_factory=list)
    facts_this_session: List[str] = field(default_factory=list)
    # 本场首次「换话题」切点：facts_this_session 下标；切点前=改向前段；None=尚未改向
    topic_redirect_at: Optional[int] = None
    session_judgments: List[SessionJudgment] = field(default_factory=list)
    session_actions: List[SessionAction] = field(default_factory=list)
    session_actions_overflow: bool = False
    action_feedback: List[ActionFeedback] = field(default_factory=list)
    stance_traces: List[StanceTrace] = field(default_factory=list)
    # 本场每个结构化点被守住的实际次数；只在本场累计，不落盘。
    stance_kept_counts: Dict[str, int] = field(default_factory=dict)
    drive_identity_ask_pending: bool = False
    identity_ask_awaiting_answer: bool = False
    drive_identity_answer_pending: bool = False
    identity_answer_text: str = ""
    # 本轮不可改变处境的态度线索，不跨轮保留。
    stance_attitude_pending: bool = False
    body_imagine_pending: bool = False
    stance_necessary_pain_pending: bool = False
    stance_self_torture_pending: bool = False
    # 结构化：同场好奇挂起仍 pending（pipeline 写；drive 主路径读；勿靠「待接的话头：」前缀）
    curiosity_hang_pending: bool = False
    want_seen_pending: bool = False
    drive_want_seen_satisfied_pending: bool = False
    drive_want_seen_waiting: bool = False
    # 结构化：本轮用户改口／否认同场承诺（pipeline／上游写；drive S2 主路径读；勿主靠 _denies_commitment 词表）
    commitment_deny_pending: bool = False
    # 结构化：本轮招呼 hold（pipeline／上游写；drive 非 S3 主路径读；勿主靠 GREETINGS 词表）
    drive_greet_pending: bool = False
    # 结构化：本轮满足／收束 hold（pipeline／上游写；drive 非 S3 主路径读；勿主靠 SATISFIED_MARKS）
    drive_hold_pending: bool = False
    drive_openq_satisfied_pending: bool = False
    # 结构化：本轮好奇 pursue（pipeline／上游写；drive 非 S3 主路径读；勿主靠 CURIOSITY_MARKS）
    drive_curiosity_pending: bool = False
    # 结构化：本轮打开话题 pursue（pipeline／上游写；drive 非 S3 主路径读；勿主靠 OPEN_TOPIC_PREFIXES）
    drive_open_topic_pending: bool = False
    # 结构化：本轮失望／空追 guard（pipeline／上游写；drive 非 S3 主路径读；勿主靠 DISAPPOINT_MARKS）
    drive_disappoint_pending: bool = False
    # 结构化：本轮空追钝化 hold（pipeline／上游写；drive 非 S3 主路径读；勿主靠 _EMPTY_STAGE_MARKS）
    drive_empty_stage_pending: bool = False
    # 结构化：本轮话题延续 pursue（pipeline／上游写；drive 非 S3 主路径读；勿主靠话题词扫 facts）
    drive_topic_continue_pending: bool = False
    # 结构化：本轮回指 pursue（pipeline／上游写；drive／stub 主路径读；勿主靠 BACKREF_MARKS／why 文案）
    drive_callback_pending: bool = False
    # 跨场：上一场薄痕迹（memory 新场开局灌入；回指／亲历来源读结构，不拼 say_intent）
    prior_session: Optional[PriorSessionTrace] = None
    # 结构化：上场未兑现承诺作 drive 线索（不强制开口提；§6 仍只看同场 last_commitments）
    drive_prior_commit_pending: bool = False
    drive_prior_her_question_pending: bool = False
    drive_prior_her_question_used: bool = False
    # 结构化：本轮跨场回指 pursue（有 prior_session 结构时写入；勿主靠「上次」词表放行）
    drive_prior_callback_pending: bool = False
    # 结构化：本轮用户催兑现上场未了承诺（有 prior.commitments_pending；§6 仍只看同场）
    drive_prior_press_pending: bool = False
    # 工程师通道：强制动力中性 hold（pipeline／env／kwarg；非出生默认；默认 False）
    drive_bypass: bool = False
    # 工程师通道：开口拒收回流（同场累加；不拼 say_intent；不落盘跨场）
    # articulate_reject_count：同场 LLM／hook 被 validate／_accept_draft 拒，或空／抛错落入 stub 的次数
    articulate_reject_count: int = 0
    # last_reject_reasons：短标签／枚举码（非原文灾难句）；容量截断
    last_reject_reasons: List[str] = field(default_factory=list)
    # 选定策略：本轮曾拒但最终已出话（含 stub 兜底）→ True；不清算 articulate_reject_count
    # （跨轮累加供 soft hold）；new_session／/new 清。另一选项「接受后清 count」未采用。
    articulate_reject_recovered: bool = False


@dataclass
class SourcedInput:
    text: str
    source: str = "user"
    provenance: str = "birth/pipeline.py:turn"


@dataclass
class ThoughtBrief:
    """一条时间步的完整思想简报：仲裁的输出、开口的唯一依据。"""

    dominant: Dominant
    drive: Optional[DriveSignal] = None
    stance: StanceSignal = field(default_factory=StanceSignal)
    org: OrgConstraint = field(default_factory=OrgConstraint)
    context: ThinContext = field(default_factory=ThinContext)
    say_intent: str = ""
    # V2.1：say_intent 中「」引语的结构字段（arbitrate／回忆旁路写；开口层读，不再切 say_intent）
    say_quote: str = ""
    must_not_pretend: List[str] = field(default_factory=list)
    # 本轮实际命中的 cannot_fake 条目（常驻底线之外额外踩到的；
    # 开口层按它略分 org 口径，不做禁词）
    org_conflicts: List[str] = field(default_factory=list)
    # 结构化：本轮因悬问说过话，开口后应 resolve（勿靠 say_intent 中文子串）
    openq_resolve: bool = False
    # 结构化：本轮好奇挂起 → pipeline 置 curiosity_hang_pending＋挂 openq（勿强制「待接的话头：」前缀；勿再扫 CURIOSITY_MARKS）
    openq_curiosity_hang: bool = False
    # 结构化：本轮用户明示放下／真开新话头 → 开口后 clear 悬问（pipeline 勿再扫放下词表）
    openq_clear: bool = False
    # 结构化：本轮用户催可核对约定（articulate 拒空壳／stub 模板读此标记）
    press_commit: bool = False
    # 催债动作的目标（可回落最老）；销账只读下方独立的认账身份。
    pressed_commitment: str = ""
    # 结构化：用户示意约定已兑现 → 开口后 resolve
    commit_resolve: bool = False
    # 结构化：本轮用户改口／否认同场承诺（arbitrate 写；pipeline／commit_extract 读；勿主靠 COMMIT_DENY_MARKS）
    commit_deny: bool = False
    # 结构化：本轮 Brief 侧守同场（arbitrate 与 commit_deny 同支置位；articulate 主路径读此／commit_deny／stance.hold_same_field，勿靠 stake 中文串）
    hold_same_field: bool = False
    # 结构化：本轮守着 pending 承诺，台上开口可交付主题则 resolve
    commit_deliverable: bool = False
    # 用户话已点到 pending 主题（可检验「接着交付」意图，非仅守诺）
    commit_deliver_intent: bool = False
    # 承诺与动力并存时双写（含 differentiated）；勿靠中文子串门控。
    commit_hold_with_drive: bool = False
    # 认账身份独立于主导分支与催债动作；空＝未唯一识别（单笔可回落）。
    recognized_prior_commitment: str = ""
    recognized_same_commitment: str = ""

    understanding: Optional["InputSignal"] = None
    user_input: Optional[SourcedInput] = None
    openq_resolve_target: str = ""
    prior_openq_resolve_target: str = ""
    # 仲裁取舍与来源，只供工程师通道。
    dominant_why: str = ""
    # 本轮要回应的实际内容短摘；空表示无实质内容。
    focus: str = ""
    # 本轮理解／本轮原话／同场悬问／同场承诺／上场承诺／同场事实／无实质内容。
    focus_source: str = ""
    recall_evidence: Optional[RecallEvidence] = None
    recall_requested: bool = False
    recall_status: Literal["not_requested", "unique", "no_match", "multiple", "unavailable"] = "not_requested"

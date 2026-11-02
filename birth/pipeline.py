"""出生旁路主管线：turn() 串起 感知 → 动力 → 立场/组织 → 仲裁 → 开口 → 回流。

- 旧 engine/ 旧管线不改动、不 import；
- 同场状态放在模块级 ThinContextStore，只有 turn(..., new_session=True) 清空；
- 开口后事实/悬起/薄承诺回流 ThinContext（extract_commitment 宁缺毋滥）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .arbitrate import arbitrate
from .articulate import articulate, last_articulate_source
from .commit_extract import (
    extract_commitment,
    should_resolve_commitment,
    should_set_commitment_deny_pending,
    structured_deny_from_stance,
)
from .openq_extract import (
    extract_open_question,
    should_clear_open_questions,
    should_resolve_open_question,
)
from .context import ThinContextStore
from .drive import (
    infer_drive,
    should_set_drive_curiosity_pending,
    should_set_drive_disappoint_pending,
    should_set_drive_empty_stage_pending,
    should_set_drive_greet_pending,
    should_set_drive_hold_pending,
    should_set_drive_open_topic_pending,
    should_set_drive_topic_continue_pending,
)
from .stance_org import default_org, default_stance
from .types import ThoughtBrief

_STORE: ThinContextStore = ThinContextStore()


def active_store() -> ThinContextStore:
    """当前同场的存储（测试也用它检查回流）。"""
    return _STORE


@dataclass
class TurnResult:
    utterance: str
    brief: ThoughtBrief
    articulate_source: str = "stub"  # deepseek|opencode|hook|stub|stub_fallback|reject_self_id


def _clip(text: str, limit: int = 40) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + "…"


def turn(
    user_text: str,
    *,
    new_session: bool = False,
    debug: bool = False,
    stub: bool | None = None,
    structured_commit_deny: bool = False,
    structured_drive_greet: bool = False,
    structured_drive_hold: bool = False,
    structured_drive_curiosity: bool = False,
    structured_drive_open_topic: bool = False,
    structured_drive_disappoint: bool = False,
    structured_drive_empty_stage: bool = False,
    structured_drive_topic_continue: bool = False,
) -> TurnResult:
    """跑完一轮完整闭环。new_session=True 显式开新场（唯一清空入口）。

    debug 只是让工程师通道外显得更方便（CLI 用它打印 Brief）；管线行为不受影响。
    stub=True 强制模板开口；None 跟随 articulate 全局/环境（默认可走 LLM）。
    structured_commit_deny: 上游结构化 deny Brief-family 标记（如 ThoughtBrief.commit_deny）；
    为 True 时优先使用结构化信号。live 本轮无 kwarg 时，写入前先跑 early stance，
    从其守诺结构（与 Brief.commit_deny 同条件）前移置 flag；COMMIT_DENY_MARKS
    仅真无结构时兜底——兼容旧路径但不扩词表，不改台上话术；勿误伤
    PRESS_COMMIT／交付／放下。
    structured_drive_greet／structured_drive_hold: 上游结构化招呼／收束 hold cue；
    有结构时 drive 非 S3 主路径读 ThinContext flag，不扫 GREETINGS／SATISFIED_MARKS；
    真无结构时词表兜底（不扩词表）。
    structured_drive_curiosity／structured_drive_open_topic: 上游结构化好奇／打开话题
    pursue cue；有结构时读 ThinContext flag，不扫 CURIOSITY_MARKS／OPEN_TOPIC_PREFIXES；
    真无结构时词表兜底（不扩词表）。
    structured_drive_disappoint／structured_drive_empty_stage／structured_drive_topic_continue:
    上游结构化失望 guard／空台 hold／话题延续 pursue cue；有结构时读 ThinContext flag，
    不扫 DISAPPOINT_MARKS／_EMPTY_STAGE_MARKS／话题词；真无结构时兜底（不扩词表）。
    """
    if new_session:
        _STORE.new_session()

    # 改口否定写入（前移结构化检测；有结构时本轮不必再扫 COMMIT_DENY_MARKS）：
    # 1) 上游 kwarg／同族结构化；2) early stance 守诺结构（与 arbitrate 置
    #    Brief.commit_deny 同条件）同轮回灌；3) 仅真无结构时词表兜底。
    has_pending = bool(_STORE.pending_commitments())
    _STORE.set_commitment_deny_pending(False)
    if should_set_commitment_deny_pending(
        commit_deny=structured_commit_deny,
        user_text=user_text,
        has_pending=has_pending,
        marks_fallback=False,
    ):
        _STORE.set_commitment_deny_pending(True)

    context = _STORE.snapshot()
    # 前移：先跑 stance，从守诺结构得到本轮结构化 deny（不经写入侧词表）
    early_stance = default_stance(user_text, context)
    if (
        not _STORE.context.commitment_deny_pending
        and structured_deny_from_stance(
            early_stance, has_commitments=bool(context.last_commitments)
        )
    ):
        # 同轮结构化：early 守诺 → commit_deny=True，写入不扫词表
        if should_set_commitment_deny_pending(
            commit_deny=True,
            user_text=user_text,
            has_pending=has_pending,
            marks_fallback=False,
        ):
            _STORE.set_commitment_deny_pending(True)
            context = _STORE.snapshot()
    elif not _STORE.context.commitment_deny_pending:
        # 真无结构：COMMIT_DENY_MARKS 词表兜底（见 should_set_commitment_deny_pending）
        if should_set_commitment_deny_pending(
            commit_deny=False,
            user_text=user_text,
            has_pending=has_pending,
            marks_fallback=True,
        ):
            _STORE.set_commitment_deny_pending(True)
            context = _STORE.snapshot()

    # 非 S3：招呼／收束／打开话题／好奇／失望／空台／话题延续 写入
    # （有结构 cue 不扫词表；真无结构时各 MARKS／facts 兜底）
    _STORE.set_drive_greet_pending(False)
    _STORE.set_drive_hold_pending(False)
    _STORE.set_drive_open_topic_pending(False)
    _STORE.set_drive_curiosity_pending(False)
    _STORE.set_drive_disappoint_pending(False)
    _STORE.set_drive_empty_stage_pending(False)
    _STORE.set_drive_topic_continue_pending(False)
    if should_set_drive_greet_pending(
        greet_cue=structured_drive_greet,
        user_text=user_text,
        marks_fallback=not bool(structured_drive_greet),
    ):
        _STORE.set_drive_greet_pending(True)
    if should_set_drive_hold_pending(
        hold_cue=structured_drive_hold,
        user_text=user_text,
        marks_fallback=not bool(structured_drive_hold),
    ):
        _STORE.set_drive_hold_pending(True)
    if should_set_drive_open_topic_pending(
        open_topic_cue=structured_drive_open_topic,
        user_text=user_text,
        marks_fallback=not bool(structured_drive_open_topic),
    ):
        _STORE.set_drive_open_topic_pending(True)
    if should_set_drive_curiosity_pending(
        curiosity_cue=structured_drive_curiosity,
        user_text=user_text,
        marks_fallback=not bool(structured_drive_curiosity),
    ):
        _STORE.set_drive_curiosity_pending(True)
    # empty_stage／topic_continue 兜底需同场 facts；先用当前 snapshot 作 context
    ctx_for_drive_write = _STORE.snapshot()
    if should_set_drive_disappoint_pending(
        disappoint_cue=structured_drive_disappoint,
        user_text=user_text,
        marks_fallback=not bool(structured_drive_disappoint),
    ):
        _STORE.set_drive_disappoint_pending(True)
    if should_set_drive_empty_stage_pending(
        empty_stage_cue=structured_drive_empty_stage,
        user_text=user_text,
        context=ctx_for_drive_write,
        marks_fallback=not bool(structured_drive_empty_stage),
    ):
        _STORE.set_drive_empty_stage_pending(True)
    if should_set_drive_topic_continue_pending(
        topic_continue_cue=structured_drive_topic_continue,
        user_text=user_text,
        context=ctx_for_drive_write,
        marks_fallback=not bool(structured_drive_topic_continue),
    ):
        _STORE.set_drive_topic_continue_pending(True)
    context = _STORE.snapshot()

    drive = infer_drive(user_text, context)
    # 旗标可能刚被 early 守诺结构置位：重算 stance，使主路径读 flag（结构路径）
    stance = default_stance(user_text, context)
    org = default_org(context, drive=drive, stance=stance, user_text=user_text)
    brief = arbitrate(drive=drive, stance=stance, org=org, context=context,
                      user_text=user_text)

    utterance = articulate(brief, stub=stub)

    # 悬问收放（可检验；对齐承诺宁缺——拿不准不清）：
    # - resolve：读 Brief.openq_resolve（禁止 say_intent 中文子串）；
    # - clear：读 Brief.openq_clear（arbitrate 已判放下／换题）；pipeline 不再扫放下词表。
    if should_resolve_open_question(
        brief=brief, user_text=user_text, has_open=bool(context.open_questions)
    ):
        _STORE.resolve_open_question()
    elif should_clear_open_questions(
        brief=brief, has_open=bool(context.open_questions)
    ):
        _STORE.clear_open_questions()

    # 承诺兑现／放下（对齐悬问 resolve；宁缺毋滥，拿不准不清）
    pending0 = context.last_commitments[0] if context.last_commitments else None
    if should_resolve_commitment(
        brief=brief, utterance=utterance, pending_first=pending0
    ):
        _STORE.resolve_commitment()

    # 开口后回流薄情境：本轮用户的话头 + 台上这句都 clip 进同场事实；
    # 动力层好奇追问入库；台上薄提取承诺/悬问（宁缺毋滥）
    _STORE.append_fact(f"用户说：{_clip(user_text)}")
    _STORE.append_fact(f"台上说：{_clip(utterance)}")
    commitment = extract_commitment(utterance)
    if commitment:
        _STORE.append_commitment(commitment)
    # 好奇挂起：读 Brief.openq_curiosity_hang（禁止 pipeline 再扫 CURIOSITY_MARKS）
    if getattr(brief, "openq_curiosity_hang", False):
        # 新好奇挂起替换旧悬问（可检验的「新话头」，避免只进不出堆黏）
        if _STORE.pending_questions():
            _STORE.clear_open_questions()
        # 结构化标记：drive 主路径读该布尔；「待接的话头：」前缀仅作文案载体＋兜底
        _STORE.set_curiosity_hang_pending(True)
        _STORE.append_open_question(f"待接的话头：{_clip(user_text)}")
    else:
        open_q = extract_open_question(utterance)
        if open_q:
            _STORE.append_open_question(open_q)

    # 改口否定／非 S3 drive flags 只服务本轮 drive：回合末清，不漏到下一轮
    _STORE.set_commitment_deny_pending(False)
    _STORE.set_drive_greet_pending(False)
    _STORE.set_drive_hold_pending(False)
    _STORE.set_drive_open_topic_pending(False)
    _STORE.set_drive_curiosity_pending(False)
    _STORE.set_drive_disappoint_pending(False)
    _STORE.set_drive_empty_stage_pending(False)
    _STORE.set_drive_topic_continue_pending(False)

    return TurnResult(
        utterance=utterance,
        brief=brief,
        articulate_source=last_articulate_source(),
    )

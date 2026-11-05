"""出生旁路主管线：turn() 串起 感知 → 动力 → 立场/组织 → 仲裁 → 开口 → 回流。

- 旧 engine/ 旧管线不改动、不 import；
- 同场状态放在模块级 ThinContextStore，只有 turn(..., new_session=True) 清空；
- 开口后事实/悬起/薄承诺回流 ThinContext（extract_commitment 宁缺毋滥）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .arbitrate import arbitrate
from .articulate import articulate, last_articulate_source, take_reject_feedback
from .commit_extract import (
    extract_commitment,
    should_resolve_commitment,
    utterance_covers_pending_commitment,
    should_set_commitment_deny_pending,
    structured_deny_from_stance,
)
from .openq_extract import (
    answered_open_question,
    extract_open_question,
    should_clear_open_questions,
    should_resolve_open_question,
)
from .context import ThinContextStore
from .drive import (
    infer_drive,
    should_set_drive_callback_pending,
    is_identity_ask,
    is_neutral_filler,
    identity_self_introduction,
    should_set_drive_curiosity_pending,
    should_set_drive_disappoint_pending,
    should_set_drive_empty_stage_pending,
    should_set_drive_greet_pending,
    should_set_drive_hold_pending,
    should_set_drive_open_topic_pending,
    should_set_drive_prior_callback_pending,
    should_set_drive_prior_press_pending,
    should_set_drive_topic_continue_pending,
)
from .memory import active_memory, memory_enabled
from .stance_org import (ATTITUDE_MARKS, commitment_point, conflict_point,
                         default_org, default_stance)
from .types import ThoughtBrief

_STORE: ThinContextStore = ThinContextStore()


def active_store() -> ThinContextStore:
    """当前同场的存储（测试也用它检查回流）。"""
    return _STORE


def _persist_and_reset_session() -> None:
    """场结束：可选落盘 → 清场 → 读入上一场为 prior_session 结构。"""
    mem = active_memory() if memory_enabled() else None
    if mem is not None and _STORE.has_session_content():
        trace = _STORE.export_session_trace()
        mem.append_session(**trace)
    _STORE.new_session()
    if mem is not None:
        prior = mem.latest_prior()
        if prior is not None and prior.has_trace():
            _STORE.set_prior_session(prior)
            if prior.commitments_pending:
                _STORE.set_drive_prior_commit_pending(True)


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
    structured_openq_answered: bool | None = None,
    structured_want_seen: bool | None = None,
    structured_want_seen_answered: bool | None = None,
    structured_want_seen_hang: bool | None = None,
    structured_drive_curiosity: bool = False,
    structured_drive_open_topic: bool = False,
    structured_drive_disappoint: bool = False,
    structured_drive_empty_stage: bool = False,
    structured_drive_topic_continue: bool = False,
    structured_drive_callback: bool = False,
    structured_drive_identity_ask: bool = False,
    structured_stance_attitude: bool | None = None,
    structured_body_imagine: bool | None = None,
    structured_stance_necessary_pain: bool | None = None,
    structured_stance_self_torture: bool | None = None,
    drive_bypass: bool = False,
) -> TurnResult:
    """跑完一轮完整闭环。new_session=True 显式开新场（唯一清空入口）。

    structured_want_seen=True 表示对方已接住，False 表示仍未接住；None 才用极薄口语兜底。
    structured_want_seen_answered 如有值则覆盖上述判断；structured_want_seen_hang=True
    标记本轮开口在等对方的看法，False 禁止开口指纹兜底。
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
    structured_drive_callback: 上游结构化回指 pursue cue；有结构时读 ThinContext.drive_callback_pending，
    不扫 BACKREF_MARKS；真无结构时 is_session_backref 兜底（不扩词表）。有承诺时写入侧不置（§6）。
    drive_bypass: 工程师通道——强制动力层中性 hold（亦可 BIRTH_DRIVE_BYPASS／NEUTRAL 环境变量
    或 ThinContext.drive_bypass）；默认 False，出生路径零行为变化；非听感验收。
    """
    if new_session:
        # 跨场：先把本场薄痕迹落盘（若开启），再清场，再灌入上一场痕迹
        _persist_and_reset_session()

    # None 才使用固定线索；显式 False 可由上游否决误命中。
    _STORE.context.stance_attitude_pending = (
        structured_stance_attitude if structured_stance_attitude is not None
        else any(mark in (user_text or "") for mark in ATTITUDE_MARKS)
    )
    _STORE.context.body_imagine_pending = (
        structured_body_imagine if structured_body_imagine is not None
        else "想象一下亲眼看看" in (user_text or "")
    )
    _STORE.context.stance_necessary_pain_pending = (
        structured_stance_necessary_pain if structured_stance_necessary_pain is not None
        else any(mark in (user_text or "") for mark in ("只能面对", "躲不掉", "必须承受"))
    )
    _STORE.context.stance_self_torture_pending = (
        structured_stance_self_torture if structured_stance_self_torture is not None
        else any(mark in (user_text or "") for mark in ("我就是要难受", "偏要跟自己过不去", "不痛苦就没意义"))
    )

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

    # 非 S3：招呼／收束／打开话题／好奇／失望／空台／话题延续／回指 写入
    # （有结构 cue 不扫词表；真无结构时各 MARKS／facts 兜底）
    _STORE.set_drive_greet_pending(False)
    answer = identity_self_introduction(user_text) if _STORE.context.identity_ask_awaiting_answer else ""
    _STORE.context.identity_answer_text = answer
    _STORE.context.drive_identity_answer_pending = bool(answer)
    _STORE.set_drive_identity_ask_pending(structured_drive_identity_ask or is_identity_ask(user_text))
    _STORE.set_drive_hold_pending(False)
    _STORE.context.drive_openq_satisfied_pending = False
    _STORE.context.drive_want_seen_satisfied_pending = False
    seen_signal = (structured_want_seen_answered if structured_want_seen_answered is not None
                   else structured_want_seen)
    text = (user_text or "").strip()
    if seen_signal is None:
        # A deliberately narrow response shape, not generic topic overlap.
        seen_signal = (len(text) >= 4 and not is_neutral_filler(text)
                       and not any(q in text for q in ("?", "？"))
                       and ("我听到你" in text or "我理解你" in text))
    if _STORE.context.want_seen_pending and seen_signal:
        _STORE.set_want_seen_pending(False)
        _STORE.context.drive_want_seen_satisfied_pending = True
    _STORE.context.drive_want_seen_waiting = bool(
        _STORE.context.want_seen_pending and
        (seen_signal is False and (structured_want_seen is not None or structured_want_seen_answered is not None)
         or is_neutral_filler(user_text))
    )
    pending_openq = _STORE.snapshot()
    has_hang = bool(pending_openq.curiosity_hang_pending or pending_openq.open_questions)
    answered = has_hang and (
        structured_openq_answered if structured_openq_answered is not None
        else answered_open_question(user_text, pending_openq.open_questions)
    )
    if answered:
        if pending_openq.open_questions:
            _STORE.resolve_open_question()
        else:
            _STORE.set_curiosity_hang_pending(False)
        _STORE.context.drive_openq_satisfied_pending = True
    _STORE.set_drive_open_topic_pending(False)
    _STORE.set_drive_curiosity_pending(False)
    _STORE.set_drive_disappoint_pending(False)
    _STORE.set_drive_empty_stage_pending(False)
    _STORE.set_drive_topic_continue_pending(False)
    _STORE.set_drive_callback_pending(False)
    _STORE.set_drive_prior_callback_pending(False)
    _STORE.set_drive_prior_press_pending(False)
    # prior_commit 线索：有 prior_session 未兑现则整场可作线索（每轮重申，不靠回合末残留）
    _STORE.set_drive_prior_commit_pending(False)
    prior = _STORE.context.prior_session
    _STORE.set_drive_prior_her_question_pending(False)
    if prior is not None and prior.her_questions:
        _STORE.set_drive_prior_her_question_pending(True)
    if prior is not None and prior.commitments_pending:
        _STORE.set_drive_prior_commit_pending(True)
    _STORE.set_drive_bypass(False)
    if drive_bypass:
        _STORE.set_drive_bypass(True)
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
    # DRIVE_V1 §6：同场承诺在场时，写入侧不置 S8–S11 flag，避免压过 guard
    # （drive 内亦有 §6 先于 S8–S11；此处双保险，使 turn 路径与直调 infer_drive 对齐）。
    _commitments_block_s8_s10 = bool(ctx_for_drive_write.last_commitments)
    if not _commitments_block_s8_s10 and should_set_drive_disappoint_pending(
        disappoint_cue=structured_drive_disappoint,
        user_text=user_text,
        marks_fallback=not bool(structured_drive_disappoint),
    ):
        _STORE.set_drive_disappoint_pending(True)
    if not _commitments_block_s8_s10 and should_set_drive_empty_stage_pending(
        empty_stage_cue=structured_drive_empty_stage,
        user_text=user_text,
        context=ctx_for_drive_write,
        marks_fallback=not bool(structured_drive_empty_stage),
    ):
        _STORE.set_drive_empty_stage_pending(True)
    if not _commitments_block_s8_s10 and should_set_drive_topic_continue_pending(
        topic_continue_cue=structured_drive_topic_continue,
        user_text=user_text,
        context=ctx_for_drive_write,
        marks_fallback=not bool(structured_drive_topic_continue),
    ):
        _STORE.set_drive_topic_continue_pending(True)
    if not _commitments_block_s8_s10 and should_set_drive_callback_pending(
        callback_cue=structured_drive_callback,
        user_text=user_text,
        context=ctx_for_drive_write,
        marks_fallback=not bool(structured_drive_callback),
    ):
        _STORE.set_drive_callback_pending(True)
    # 跨场回指：须有 prior_session 结构；同场承诺在场时不置（对齐 §6）
    if not _commitments_block_s8_s10 and should_set_drive_prior_callback_pending(
        user_text=user_text,
        context=ctx_for_drive_write,
        marks_fallback=True,
    ):
        _STORE.set_drive_prior_callback_pending(True)
    # 上场承诺被催：须有 prior.commitments_pending；同场承诺在场时不置（对齐 §6；
    # 不把 prior pending 并进 last_commitments）
    _STORE.set_drive_prior_press_pending(False)
    if not _commitments_block_s8_s10 and should_set_drive_prior_press_pending(
        user_text=user_text,
        context=ctx_for_drive_write,
        marks_fallback=True,
    ):
        _STORE.set_drive_prior_press_pending(True)
    context = _STORE.snapshot()

    drive = infer_drive(user_text, context, drive_bypass=drive_bypass or None)
    # 旗标可能刚被 early 守诺结构置位：重算 stance，使主路径读 flag（结构路径）
    stance = default_stance(user_text, context)
    org = default_org(context, drive=drive, stance=stance, user_text=user_text)
    brief = arbitrate(drive=drive, stance=stance, org=org, context=context,
                      user_text=user_text)
    if brief.drive is not None and bool(getattr(brief.drive, "prior_her_question", False)):
        _STORE.set_drive_prior_her_question_used()

    utterance = articulate(brief, stub=stub)

    stance_now = brief.stance
    if stance_now.posture == "non_negotiable":
        kept_point = ""
        if brief.org_conflicts:
            kept_point = conflict_point(brief.org_conflicts[0])
        elif brief.hold_same_field and context.last_commitments:
            kept_point = commitment_point(context.last_commitments[0])
        if kept_point:
            _STORE.append_stance_trace("kept", kept_point, stance_now.why)
            _STORE.record_stance_kept(kept_point)

    # Only a concrete opening asking for the other's side creates a wait.
    opening_hang = structured_want_seen_hang
    if opening_hang is None:
        opening_hang = any(mark in (brief.say_intent + utterance)
                           for mark in ("想听听你的看法", "想听听你怎么看"))
    if opening_hang and not context.drive_want_seen_satisfied_pending:
        _STORE.set_want_seen_pending(True)

    # 开口拒收回流薄体验（工程师通道）：短标签进 ThinContext；不拼 say_intent；不落盘。
    # 策略：同场累加 articulate_reject_count；本轮曾拒但已出话 → recovered=True（不清 count）。
    reject_tags = take_reject_feedback()
    if reject_tags:
        _STORE.record_articulate_rejects(reject_tags)
    _STORE.mark_articulate_uttered(rejected_this_turn=bool(reject_tags))

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

    # 上场未兑现被催后，开口覆盖该 pending → prior 侧 resolved（不并进 last_commitments）
    prior_now = context.prior_session
    if (
        prior_now is not None
        and prior_now.commitments_pending
        and bool(getattr(context, "drive_prior_press_pending", False))
    ):
        prior_p0 = prior_now.commitments_pending[0]
        if utterance_covers_pending_commitment(utterance, prior_p0):
            _STORE.resolve_prior_commitment(match=prior_p0)

    if structured_openq_answered is True:
        live_prior = _STORE.context.prior_session
        if live_prior is not None and live_prior.her_questions:
            _STORE.remove_prior_her_question(live_prior.her_questions[0])

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
        # 结构化标记：drive／stub 主路径读该布尔。默认只置 flag＋挂 clip 文案，
        # 不强制写「待接的话头：」前缀（drive/stub 已读 flag）。前缀仅无 flag 时的
        # 人类可读／旧快照兜底（drive_cues_from_context），本路径不写。
        _STORE.set_curiosity_hang_pending(True)
        _STORE.append_open_question(_clip(user_text))
    elif (not (opening_hang and not context.drive_want_seen_satisfied_pending)
          and "想被看见｜" not in (drive.why or "")
          and not (context.open_questions and is_neutral_filler(user_text))):
        open_q = extract_open_question(utterance)
        if open_q:
            _STORE.append_her_question(open_q)

    # 改口否定／非 S3 drive flags 只服务本轮 drive：回合末清，不漏到下一轮
    _STORE.set_commitment_deny_pending(False)
    _STORE.set_drive_greet_pending(False)
    _STORE.context.stance_attitude_pending = False
    _STORE.context.body_imagine_pending = False
    _STORE.context.stance_necessary_pain_pending = False
    _STORE.context.stance_self_torture_pending = False
    _STORE.context.identity_ask_awaiting_answer = _STORE.context.drive_identity_ask_pending
    _STORE.set_drive_identity_ask_pending(False)
    _STORE.context.drive_identity_answer_pending = False
    _STORE.context.identity_answer_text = ""
    _STORE.set_drive_hold_pending(False)
    _STORE.context.drive_openq_satisfied_pending = False
    _STORE.context.drive_want_seen_satisfied_pending = False
    _STORE.context.drive_want_seen_waiting = False
    _STORE.set_drive_open_topic_pending(False)
    _STORE.set_drive_curiosity_pending(False)
    _STORE.set_drive_disappoint_pending(False)
    _STORE.set_drive_empty_stage_pending(False)
    _STORE.set_drive_topic_continue_pending(False)
    _STORE.set_drive_callback_pending(False)
    _STORE.set_drive_prior_callback_pending(False)
    _STORE.set_drive_prior_press_pending(False)
    # drive_prior_commit_pending 下一轮开头按 prior_session 重申，此处清以免脏读
    _STORE.set_drive_prior_commit_pending(False)
    _STORE.set_drive_prior_her_question_pending(False)
    _STORE.set_drive_bypass(False)

    return TurnResult(
        utterance=utterance,
        brief=brief,
        articulate_source=last_articulate_source(),
    )

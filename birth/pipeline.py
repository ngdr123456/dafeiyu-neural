"""出生旁路主管线：turn() 串起 感知 → 动力 → 立场/组织 → 仲裁 → 开口 → 回流。

- 旧 engine/ 旧管线不改动、不 import；
- 同场状态放在模块级 ThinContextStore，只有 turn(..., new_session=True) 清空；
- 开口后事实/悬起/薄承诺回流 ThinContext（extract_commitment 宁缺毋滥）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import os

from .arbitrate import arbitrate
from .articulate import articulate, last_articulate_source, take_reject_feedback
from .commit_extract import (
    extract_commitment,
    pressed_frame,
    should_resolve_commitment,
    user_marks_commitment_done,
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
from .input_contract import InputSignal, credible_open_question_answer
from .input_sense import sense_input
from .stance_org import (ATTITUDE_MARKS, commitment_point, conflict_point,
                         default_org, default_stance)
from .types import CommitmentCandidate, HerUtterance, ThoughtBrief

_STORE: ThinContextStore = ThinContextStore()


def active_store() -> ThinContextStore:
    """当前同场的存储（测试也用它检查回流）。"""
    return _STORE


def end_session() -> bool:
    """记忆开启且本场有内容时落盘；不清场，容量异常原样交给调用方。"""
    mem = active_memory() if memory_enabled() else None
    if mem is None or not _STORE.has_session_content():
        return False
    mem.append_session(**_STORE.export_session_trace())
    return True


def _persist_and_reset_session() -> None:
    """场结束：可选落盘 → 清场 → 读入上一场为 prior_session 结构。"""
    mem = active_memory() if memory_enabled() else None
    end_session()
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
    input_signal: InputSignal | None = None


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
    input_signal: InputSignal | None = None,
    sense: bool | None = None,
    output: Callable[[TurnResult], None] | None = None,
) -> TurnResult:
    """跑完一轮完整闭环。new_session=True 显式开新场（唯一清空入口）。

    output：同步输出确认回调；必须在完整输出成功（含缓冲 flush）后才正常返回，
    中断／失败须抛异常。回调期间不得重入 turn、清场或修改 result／store。
    正常返回后才记录台词及其承诺、悬问、守诺和已出话体验；异常不回流这些副作用。
    非 CLI 调用不传 output 时，沿用旧接口：调用 turn 即隐式确认消费返回台词，立即回流；
    需要实际交付确认的调用方必须传 output，不能先 turn 再自行打印。
    用户输入及其已触发的状态更新不依赖输出确认，不回滚。
    structured_want_seen=True 表示对方已接住，False 表示仍未接住；None 才用极薄口语兜底。
    structured_want_seen_answered 如有值则覆盖上述判断；structured_want_seen_hang=True
    标记本轮开口在等对方的看法，False 禁止开口指纹兜底。
    debug 只是让工程师通道外显得更方便（CLI 用它打印 Brief）；管线行为不受影响。
    stub=True 强制模板开口；None 跟随 articulate 全局/环境（默认可走 LLM）。
    sense=None 读取 BIRTH_INPUT_SENSE（默认关闭）；显式信号优先，绕过动力时不感知。
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
    if sense is None:
        sense = os.environ.get("BIRTH_INPUT_SENSE", "").strip().lower() in {"1", "true", "yes", "on"}
    if input_signal is None and sense and not drive_bypass:
        input_signal = sense_input(user_text, context=context)
    # 前移：先跑 stance，从守诺结构得到本轮结构化 deny（不经写入侧词表）
    early_stance = default_stance(user_text, context, understanding=input_signal)
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
    if answered and not credible_open_question_answer(input_signal):
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

    drive = infer_drive(user_text, context, drive_bypass=drive_bypass or None, input_signal=input_signal,
                        understanding=input_signal)
    # 旗标可能刚被 early 守诺结构置位：重算 stance，使主路径读 flag（结构路径）
    stance = default_stance(user_text, context, understanding=input_signal)
    org = default_org(context, drive=drive, stance=stance, user_text=user_text,
                      understanding=input_signal)
    brief = arbitrate(drive=drive, stance=stance, org=org, context=context,
                      user_text=user_text, understanding=input_signal)
    from .self_recall import recall, recall_request
    brief.recall_requested = recall_request(input_signal, user_text)
    brief.recall_evidence = recall(input_signal, user_text, _STORE, active_memory() if memory_enabled() else None)
    utterance = articulate(brief, stub=stub)
    result = TurnResult(
        utterance=utterance,
        brief=brief,
        articulate_source=last_articulate_source(),
        input_signal=input_signal,
    )
    # 拒收确实发生过；先取走反馈，避免输出失败后串到下一轮。
    reject_tags = take_reject_feedback()
    if reject_tags:
        _STORE.record_articulate_rejects(reject_tags)
    topic = input_signal.topic if input_signal is not None else ""
    def record_meta(origin, truncated=False):
        result = {"origin": origin, "subject": topic[:80], "truncated": truncated}
        if len(topic) > 80:
            result["subject_truncated"] = True
        if topic and input_signal is not None and input_signal.degraded:
            result["subject_degraded"] = True
        return result
    _STORE.append_fact(f"用户说：{_clip(user_text)}", metadata=record_meta("user_statement", len(user_text.strip()) > 40))
    if output is not None:
        output(result)

    # 以下均依赖这句话已交付；输出异常时 end_session 只能保存此前经历。
    if brief.drive is not None and bool(getattr(brief.drive, "prior_her_question", False)):
        _STORE.set_drive_prior_her_question_used()

    stance_now = brief.stance
    if stance_now.posture == "non_negotiable":
        kept_point = ""
        if brief.org_conflicts:
            kept_point = conflict_point(brief.org_conflicts[0])
        elif brief.hold_same_field and context.last_commitments:
            target = getattr(brief.stance, "held_commitment", "") or ""
            if (not target and len(context.last_commitments) == 1
                    and not (input_signal and input_signal.quoted_or_negated)):
                target = context.last_commitments[0]  # 唯一一笔，兼容旧构造
            if target and target in context.last_commitments:
                kept_point = commitment_point(target)
        if kept_point:
            _STORE.append_stance_trace("kept", kept_point, stance_now.why, metadata=record_meta("system_observation", kept_point.endswith("…")))
            _STORE.record_stance_kept(kept_point)

    # Only a concrete opening asking for the other's side creates a wait.
    opening_hang = structured_want_seen_hang
    if opening_hang is None:
        opening_hang = any(mark in (brief.say_intent + utterance)
                           for mark in ("想听听你的看法", "想听听你怎么看"))
    if opening_hang and not context.drive_want_seen_satisfied_pending:
        _STORE.set_want_seen_pending(True)

    # 拒收标签已在输出前记录；确认已出话后才标记 recovered（不清 count）。
    _STORE.mark_articulate_uttered(rejected_this_turn=bool(reject_tags))

    # 悬问收放（可检验；对齐承诺宁缺——拿不准不清）：
    # - resolve：读 Brief.openq_resolve（禁止 say_intent 中文子串）；
    # - clear：读 Brief.openq_clear（arbitrate 已判放下／换题）；pipeline 不再扫放下词表。
    if brief.openq_resolve_target:
        _STORE.resolve_open_question(match=brief.openq_resolve_target)
    elif brief.prior_openq_resolve_target:
        _STORE.remove_prior_her_question(brief.prior_openq_resolve_target)
    elif should_resolve_open_question(
        brief=brief, user_text=user_text, has_open=bool(context.open_questions)
    ):
        _STORE.resolve_open_question()
    elif should_clear_open_questions(
        brief=brief, has_open=bool(context.open_questions)
    ):
        _STORE.clear_open_questions()

    # 承诺兑现／放下（对齐悬问 resolve；宁缺毋滥，拿不准不清）
    commitment = extract_commitment(utterance)
    frame = pressed_frame(brief)
    press_candidate = bool(commitment and frame)
    resolved_targets = set()
    pending_all = set(context.last_commitments)
    if context.prior_session:
        pending_all.update(context.prior_session.commitments_pending)
    pending0 = brief.recognized_same_commitment or (
        context.last_commitments[0] if len(pending_all) == 1 and context.last_commitments else None
    )
    if should_resolve_commitment(
        brief=brief, utterance=utterance, pending_first=pending0,
        commitment_candidate=press_candidate,
    ):
        done = _STORE.resolve_commitment(match=pending0)
        if done:
            resolved_targets.add(done)

    # 用户明确示意已兑现，按独立认账身份销 prior；无需催债分支胜出。
    prior_now = context.prior_session
    if (
        prior_now is not None
        and prior_now.commitments_pending
    ):
        # 无唯一身份时只允许单笔回落，多笔不猜。
        prior_p0 = brief.recognized_prior_commitment or (
            prior_now.commitments_pending[0] if len(pending_all) == 1 else None
        )
        if prior_p0 and user_marks_commitment_done(user_text):
            done = _STORE.resolve_prior_commitment(match=prior_p0)
            if done:
                resolved_targets.add(done)

    if (structured_openq_answered is True and not answered
            and not credible_open_question_answer(input_signal)):
        live_prior = _STORE.context.prior_session
        if live_prior is not None and live_prior.her_questions:
            _STORE.remove_prior_her_question(live_prior.her_questions[0])

    # 用户话头已记录；确认输出后再将台上这句 clip 进同场事实；
    # 动力层好奇追问入库；台上薄提取承诺/悬问（宁缺毋滥）
    _STORE.append_fact(f"台上说：{_clip(utterance)}", metadata=record_meta("her_utterance", len(utterance.strip()) > 40))
    if utterance.strip():
        _STORE.append_her_utterance(HerUtterance(
            text=utterance,
            drive_direction=(brief.drive.direction or "") if brief.drive else "",
            stance_posture=brief.stance.posture or "",
            org_grain=brief.org.grain or "",
            source=result.articulate_source,
            complete=True,
        ))
    if commitment:
        if frame is None:
            _STORE.append_commitment(commitment, metadata=record_meta("her_utterance", commitment != utterance.strip()))
        elif frame[1] not in resolved_targets:
            _STORE.append_commitment_candidate(CommitmentCandidate(
                text=commitment, target=frame[1], frame=frame[0], source=last_articulate_source()
            ), metadata=record_meta("her_utterance", commitment != utterance.strip()))
    # 好奇挂起：读 Brief.openq_curiosity_hang（禁止 pipeline 再扫 CURIOSITY_MARKS）
    if getattr(brief, "openq_curiosity_hang", False):
        # 新好奇挂起替换旧悬问（可检验的「新话头」，避免只进不出堆黏）
        if _STORE.pending_questions():
            _STORE.clear_open_questions()
        # 结构化标记：drive／stub 主路径读该布尔。默认只置 flag＋挂 clip 文案，
        # 不强制写「待接的话头：」前缀（drive/stub 已读 flag）。前缀仅无 flag 时的
        # 人类可读／旧快照兜底（drive_cues_from_context），本路径不写。
        _STORE.set_curiosity_hang_pending(True)
        _STORE.append_open_question(_clip(user_text), metadata=record_meta("user_statement", len(user_text.strip()) > 40))
    elif (not (opening_hang and not context.drive_want_seen_satisfied_pending)
          and "想被看见｜" not in (drive.why or "")
          and not (context.open_questions and is_neutral_filler(user_text))):
        open_q = extract_open_question(utterance)
        if open_q:
            _STORE.append_her_question(open_q, metadata=record_meta("her_utterance", open_q != utterance.strip()))

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

    return result

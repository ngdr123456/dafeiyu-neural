"""ThinContext 存储：同场积累；显式 new_session 才清空；开口后回流入口。

设计要点（对齐 PHASE1_BRIEF.md 第 2 条）：
- 不做每句改性格，也不顶置长期性格记忆；只存本轮/同场要用的东西。
- 唯一的清空入口是 :meth:`ThinContextStore.new_session`，其余只积累；
  例外：悬问 resolve_open_question／clear_open_questions；承诺
  resolve_commitment／clear_commitments（兑现或明确放下时，只动承诺列表）。
- 回流入口：append_fact / append_commitment；append_open_question 供动力层挂悬而未决。
- 开口拒收：record_articulate_rejects／mark_articulate_uttered（同场结构字段；不落盘 JSON）。
"""

from __future__ import annotations

from .types import PriorSessionTrace, ThinContext


class ThinContextStore:
    """持有当前同场的 ThinContext，并提供回流写入方法。"""

    def __init__(self, context: ThinContext | None = None) -> None:
        self._context = context if context is not None else ThinContext()
        # 本场已兑现承诺（resolve 弹出时累积；供跨场落盘；new_session 清）
        self._resolved_commitments: list[str] = []

    @property
    def context(self) -> ThinContext:
        """内部可写上下文（仅 pipeline 与 store 自身使用）。"""
        return self._context

    def snapshot(self) -> ThinContext:
        """给仲裁/Brief 用的副本，避免台下引用被外部改穿存储。"""
        ctx = self._context
        prior = None
        if ctx.prior_session is not None:
            ps = ctx.prior_session
            prior = PriorSessionTrace(
                facts=list(ps.facts),
                commitments_pending=list(ps.commitments_pending),
                commitments_resolved=list(ps.commitments_resolved),
                open_questions=list(ps.open_questions),
                ended_at=ps.ended_at,
            )
        return ThinContext(
            session_ok=ctx.session_ok,
            open_questions=list(ctx.open_questions),
            last_commitments=list(ctx.last_commitments),
            facts_this_session=list(ctx.facts_this_session),
            drive_identity_ask_pending=ctx.drive_identity_ask_pending,
            identity_ask_awaiting_answer=ctx.identity_ask_awaiting_answer,
            drive_identity_answer_pending=ctx.drive_identity_answer_pending,
            identity_answer_text=ctx.identity_answer_text,
            curiosity_hang_pending=ctx.curiosity_hang_pending,
            commitment_deny_pending=ctx.commitment_deny_pending,
            drive_greet_pending=ctx.drive_greet_pending,
            drive_hold_pending=ctx.drive_hold_pending,
            drive_curiosity_pending=ctx.drive_curiosity_pending,
            drive_open_topic_pending=ctx.drive_open_topic_pending,
            drive_disappoint_pending=ctx.drive_disappoint_pending,
            drive_empty_stage_pending=ctx.drive_empty_stage_pending,
            drive_topic_continue_pending=ctx.drive_topic_continue_pending,
            drive_callback_pending=ctx.drive_callback_pending,
            prior_session=prior,
            drive_prior_commit_pending=ctx.drive_prior_commit_pending,
            drive_prior_callback_pending=ctx.drive_prior_callback_pending,
            drive_prior_press_pending=ctx.drive_prior_press_pending,
            drive_bypass=ctx.drive_bypass,
            articulate_reject_count=ctx.articulate_reject_count,
            last_reject_reasons=list(ctx.last_reject_reasons),
            articulate_reject_recovered=ctx.articulate_reject_recovered,
        )

    def new_session(self) -> None:
        """唯一的清空入口：只有显式 new_session 才会清掉同场积累（含好奇挂起 flag）。

        跨场 prior_session 由 pipeline 在清场后按需灌入；此处先置空。
        开口拒收痕迹（articulate_reject_count／last_reject_reasons／recovered）一并清，
        不持久化到跨场 JSON。
        """
        self._context = ThinContext()
        self._resolved_commitments = []

    # -- 积累（只加不减，精确重复去重避免自我灌水） ----------------------

    @staticmethod
    def _append_unique(items: list[str], text: str) -> None:
        text = text.strip()
        if text and text not in items:
            items.append(text)

    def append_fact(self, fact: str) -> None:
        """开口后事实回流：本轮发生了什么，下一轮可用。"""
        self._append_unique(self._context.facts_this_session, fact)

    def set_drive_identity_ask_pending(self, pending: bool) -> None:
        self._context.drive_identity_ask_pending = pending

    def append_commitment(self, commitment: str) -> None:
        """开口后承诺回流：说出去的话要守。"""
        self._append_unique(self._context.last_commitments, commitment)

    def append_open_question(self, question: str) -> None:
        """动力层留下的悬而未决，供后续轮次捡起。"""
        self._append_unique(self._context.open_questions, question)

    def set_curiosity_hang_pending(self, pending: bool) -> None:
        """pipeline 显式标记好奇挂起（读 Brief.openq_curiosity_hang）。

        只在挂起时置 True；resolve/clear/new_session 均清回 False，
        drive 主路径读该布尔，勿再靠「待接的话头：」前缀文本。
        """
        self._context.curiosity_hang_pending = pending

    def set_commitment_deny_pending(self, pending: bool) -> None:
        """pipeline 显式标记本轮用户改口／否认同场承诺（读 Brief／写入侧线索）。

        drive 主路径读该布尔（S2 承诺在场＋改口 → guard）；词表仅在无 flag 时兜底。
        resolve_commitment／clear_commitments／new_session 均清回 False；
        pipeline 也在每回合末清，防漏到下一轮。
        """
        self._context.commitment_deny_pending = pending

    def set_drive_greet_pending(self, pending: bool) -> None:
        """pipeline 显式标记本轮招呼 hold（上游结构化／写入侧）。

        drive 非 S3 主路径读该布尔；GREETINGS 仅无 flag 时兜底。
        new_session／回合末清 False，防漏到下一轮。
        """
        self._context.drive_greet_pending = pending

    def set_drive_hold_pending(self, pending: bool) -> None:
        """pipeline 显式标记本轮满足／收束 hold（上游结构化／写入侧）。

        drive 非 S3 主路径读该布尔；SATISFIED_MARKS 仅无 flag 时兜底。
        new_session／回合末清 False，防漏到下一轮。
        """
        self._context.drive_hold_pending = pending

    def set_drive_curiosity_pending(self, pending: bool) -> None:
        """pipeline 显式标记本轮好奇 pursue（上游结构化／写入侧）。

        drive 非 S3 主路径读该布尔；CURIOSITY_MARKS 仅无 flag 时兜底。
        new_session／回合末清 False，防漏到下一轮。
        """
        self._context.drive_curiosity_pending = pending

    def set_drive_open_topic_pending(self, pending: bool) -> None:
        """pipeline 显式标记本轮打开话题 pursue（上游结构化／写入侧）。

        drive 非 S3 主路径读该布尔；OPEN_TOPIC_PREFIXES 仅无 flag 时兜底。
        new_session／回合末清 False，防漏到下一轮。
        """
        self._context.drive_open_topic_pending = pending

    def set_drive_disappoint_pending(self, pending: bool) -> None:
        """pipeline 显式标记本轮失望／空追 guard（上游结构化／写入侧）。

        drive 非 S3 主路径读该布尔；DISAPPOINT_MARKS 仅无 flag 时兜底。
        new_session／回合末清 False，防漏到下一轮。
        """
        self._context.drive_disappoint_pending = pending

    def set_drive_empty_stage_pending(self, pending: bool) -> None:
        """pipeline 显式标记本轮空追钝化 hold（上游结构化／写入侧）。

        drive 非 S3 主路径读该布尔；_EMPTY_STAGE_MARKS／近两轮空台接话判定仅无 flag 时兜底。
        new_session／回合末清 False，防漏到下一轮。
        """
        self._context.drive_empty_stage_pending = pending

    def set_drive_topic_continue_pending(self, pending: bool) -> None:
        """pipeline 显式标记本轮话题延续 pursue（上游结构化／写入侧）。

        drive 非 S3 主路径读该布尔；话题词扫 facts 仅无 flag 时兜底。
        new_session／回合末清 False，防漏到下一轮。
        """
        self._context.drive_topic_continue_pending = pending

    def set_drive_callback_pending(self, pending: bool) -> None:
        """pipeline 显式标记本轮回指 pursue（上游结构化／写入侧）。

        drive／stub 主路径读该布尔；is_session_backref／BACKREF_MARKS 仅无 flag 时兜底。
        new_session／回合末清 False，防漏到下一轮。
        有 last_commitments 时写入侧不置（对齐 §6，勿压过 guard）。
        """
        self._context.drive_callback_pending = pending

    def set_drive_bypass(self, pending: bool) -> None:
        """工程师通道：强制动力层中性 hold（非出生默认）。

        drive 主路径读该布尔／env／kwarg；默认 False；回合末清，防漏到下一轮。
        """
        self._context.drive_bypass = pending

    def resolve_open_question(self) -> str | None:
        """接完第一条悬问：弹出并返回它；没有悬问时返回 None。

        用在「本轮因悬问说过话」之后——捡一次就该接完，不留着长期占领主导。
        好奇挂起 flag 一并清 False（宁缺毋滥：resolve 即视为挂起已接）。
        """
        if self._context.open_questions:
            self._context.curiosity_hang_pending = False
            return self._context.open_questions.pop(0)
        return None

    def clear_open_questions(self) -> None:
        """放下同场所有悬问（用户换题、开了新话头时用）；好奇挂起 flag 一并清。"""
        self._context.open_questions.clear()
        self._context.curiosity_hang_pending = False

    def resolve_commitment(self) -> str | None:
        """兑现／接完第一条承诺：弹出并返回它；没有则 None。

        对齐 resolve_open_question；态度上可守的对象，接完可放下。
        改口否定 flag 一并清 False（承诺已了，改口线索无对象）。
        弹出的条目记入本场已兑现列表，供跨场落盘。
        """
        if self._context.last_commitments:
            self._context.commitment_deny_pending = False
            done = self._context.last_commitments.pop(0)
            self._append_unique(self._resolved_commitments, done)
            return done
        return None

    def clear_commitments(self) -> None:
        """放下同场所有承诺（仅明确整场放下时用；宁缺毋滥）；改口否定 flag 一并清。"""
        self._context.last_commitments.clear()
        self._context.commitment_deny_pending = False


    def set_drive_prior_commit_pending(self, pending: bool) -> None:
        """pipeline：上场未兑现承诺作 drive 线索（不强制开口；§6 仍看同场）。"""
        self._context.drive_prior_commit_pending = pending

    def set_drive_prior_callback_pending(self, pending: bool) -> None:
        """pipeline：本轮跨场回指 pursue（须有 prior_session 结构；有同场承诺时不置）。"""
        self._context.drive_prior_callback_pending = pending

    def set_drive_prior_press_pending(self, pending: bool) -> None:
        """pipeline：本轮催兑现上场未了承诺（须有 prior.commitments_pending；有同场承诺时不置）。"""
        self._context.drive_prior_press_pending = pending

    def resolve_prior_commitment(self, match: str | None = None) -> str | None:
        """兑现上场 pending：从 prior_session.commitments_pending 弹出并记入 resolved。

        不并进同场 last_commitments（§6 仍只看同场）。match 若给则按主题覆盖挑一条，
        否则弹第一条。无 prior／无 pending → None。
        """
        prior = self._context.prior_session
        if prior is None or not prior.commitments_pending:
            return None
        done = None
        if match is None:
            done = prior.commitments_pending.pop(0)
        else:
            from .commit_extract import utterance_covers_pending_commitment
            for i, p in enumerate(list(prior.commitments_pending)):
                if p == match or utterance_covers_pending_commitment(match, p):
                    done = prior.commitments_pending.pop(i)
                    break
            if done is None:
                return None
        self._append_unique(prior.commitments_resolved, done)
        return done

    def set_prior_session(self, prior: PriorSessionTrace | None) -> None:
        """新场开局灌入上一场薄痕迹；None 表示无痕迹。"""
        if prior is None:
            self._context.prior_session = None
            return
        self._context.prior_session = PriorSessionTrace(
            facts=list(prior.facts),
            commitments_pending=list(prior.commitments_pending),
            commitments_resolved=list(prior.commitments_resolved),
            open_questions=list(prior.open_questions),
            ended_at=prior.ended_at,
        )

    def has_session_content(self) -> bool:
        """本场是否有可落盘的薄痕迹（空场不写）。"""
        ctx = self._context
        return bool(
            ctx.facts_this_session
            or ctx.last_commitments
            or self._resolved_commitments
            or ctx.open_questions
        )

    def export_session_trace(self) -> dict:
        """导出本场薄痕迹字典（供 BirthMemoryStore.append_session）。

        不含 articulate_reject_*／last_reject_reasons（拒收不跨场持久化）。
        """
        ctx = self._context
        return {
            "facts": list(ctx.facts_this_session),
            "commitments_pending": list(ctx.last_commitments),
            "commitments_resolved": list(self._resolved_commitments),
            "open_questions": list(ctx.open_questions),
        }


    # -- 开口拒收回流（工程师通道；同场；不落盘） ----------------------

    _REJECT_REASON_CAP = 8

    def record_articulate_rejects(self, tags: list[str]) -> None:
        """LLM／hook 草稿被拒：累加 count，写入短标签（不存原文灾难句）。"""
        cleaned: list[str] = []
        for t in tags:
            s = (t or "").strip()
            if s and s not in cleaned:
                cleaned.append(s)
        if not cleaned:
            return
        self._context.articulate_reject_count += len(cleaned)
        merged = list(self._context.last_reject_reasons)
        for s in cleaned:
            if s not in merged:
                merged.append(s)
        # 只留最近 N 条
        if len(merged) > self._REJECT_REASON_CAP:
            merged = merged[-self._REJECT_REASON_CAP :]
        self._context.last_reject_reasons = merged
        # 拒收发生后本轮尚未最终上台
        self._context.articulate_reject_recovered = False

    def mark_articulate_uttered(self, *, rejected_this_turn: bool) -> None:
        """本轮最终接受（含 stub 兜底上台）。

        策略选定：不清算 articulate_reject_count（跨轮累加）；
        若本轮曾拒 → articulate_reject_recovered=True（「本轮曾拒但已出话」）。
        """
        if rejected_this_turn:
            self._context.articulate_reject_recovered = True
        # 无拒收的干净接受：不改 count；recovered 保持原状（或显式 False 亦可）
        # 选定：干净接受将 recovered 置 False，避免「上轮 recovered」脏读误导。
        else:
            self._context.articulate_reject_recovered = False

    def resolved_commitments(self) -> list[str]:
        return list(self._resolved_commitments)

    # -- 只读视图 ----------------------------------------------

    def pending_commitments(self) -> list[str]:
        return list(self._context.last_commitments)

    def pending_questions(self) -> list[str]:
        return list(self._context.open_questions)

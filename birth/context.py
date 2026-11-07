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

from dataclasses import asdict, replace
from copy import deepcopy

from .memory import DEFAULT_MAX_UTTERANCES, _clip_list
from .types import CommitmentCandidate, HerUtterance, PriorSessionTrace, StanceTrace, ThinContext


class ThinContextStore:
    """持有当前同场的 ThinContext，并提供回流写入方法。"""

    def __init__(self, context: ThinContext | None = None) -> None:
        self._context = context if context is not None else ThinContext()
        # 本场已兑现承诺（resolve 弹出时累积；供跨场落盘；new_session 清）
        self._resolved_commitments: list[str] = []
        self._her_utterances: list[HerUtterance] = []
        self.prior_her_question_text = ""
        self._record_metadata = {name: {} for name in ("facts", "stance_traces", "open_questions", "her_questions", "last_commitments", "resolved_commitments", "commitment_candidates")}

    @staticmethod
    def _copy_prior_metadata(metadata):
        if metadata is None:
            return None
        copied = {}
        for name, entries in metadata.items():
            if name in ("commitment_candidates", "stance_traces"):
                copied[name] = deepcopy(entries)
            else:
                copied[name] = dict(entries)
        return copied

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
                commitment_candidates=[replace(c) for c in ps.commitment_candidates],
                facts=list(ps.facts),
                commitments_pending=list(ps.commitments_pending),
                commitments_resolved=list(ps.commitments_resolved),
                open_questions=list(ps.open_questions),
                her_questions=list(ps.her_questions),
                ended_at=ps.ended_at,
                stance_traces=[StanceTrace(t.kind, t.point, t.why) for t in ps.stance_traces],
                record_metadata=self._copy_prior_metadata(ps.record_metadata),
            )
        return ThinContext(
            session_ok=ctx.session_ok,
            open_questions=list(ctx.open_questions),
            her_questions=list(ctx.her_questions),
            last_commitments=list(ctx.last_commitments),
            commitment_candidates=[replace(c) for c in ctx.commitment_candidates],
            facts_this_session=list(ctx.facts_this_session),
            stance_traces=[StanceTrace(t.kind, t.point, t.why) for t in ctx.stance_traces],
            stance_kept_counts=dict(ctx.stance_kept_counts),
            drive_identity_ask_pending=ctx.drive_identity_ask_pending,
            identity_ask_awaiting_answer=ctx.identity_ask_awaiting_answer,
            drive_identity_answer_pending=ctx.drive_identity_answer_pending,
            identity_answer_text=ctx.identity_answer_text,
            stance_attitude_pending=ctx.stance_attitude_pending,
            body_imagine_pending=ctx.body_imagine_pending,
            stance_necessary_pain_pending=ctx.stance_necessary_pain_pending,
            stance_self_torture_pending=ctx.stance_self_torture_pending,
            curiosity_hang_pending=ctx.curiosity_hang_pending,
            want_seen_pending=ctx.want_seen_pending,
            drive_want_seen_satisfied_pending=ctx.drive_want_seen_satisfied_pending,
            drive_want_seen_waiting=ctx.drive_want_seen_waiting,
            commitment_deny_pending=ctx.commitment_deny_pending,
            drive_greet_pending=ctx.drive_greet_pending,
            drive_hold_pending=ctx.drive_hold_pending,
            drive_openq_satisfied_pending=ctx.drive_openq_satisfied_pending,
            drive_curiosity_pending=ctx.drive_curiosity_pending,
            drive_open_topic_pending=ctx.drive_open_topic_pending,
            drive_disappoint_pending=ctx.drive_disappoint_pending,
            drive_empty_stage_pending=ctx.drive_empty_stage_pending,
            drive_topic_continue_pending=ctx.drive_topic_continue_pending,
            drive_callback_pending=ctx.drive_callback_pending,
            prior_session=prior,
            drive_prior_commit_pending=ctx.drive_prior_commit_pending,
            drive_prior_her_question_pending=ctx.drive_prior_her_question_pending,
            drive_prior_her_question_used=ctx.drive_prior_her_question_used,
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
        self._her_utterances = []
        self.prior_her_question_text = ""
        self._record_metadata = {name: {} for name in self._record_metadata}

    def append_her_utterance(self, entry: HerUtterance) -> None:
        self._her_utterances = _clip_list(
            [*self._her_utterances, replace(entry)], DEFAULT_MAX_UTTERANCES
        )

    # -- 积累（只加不减，精确重复去重避免自我灌水） ----------------------

    @staticmethod
    def _append_unique(items: list[str], text: str) -> None:
        text = text.strip()
        if text and text not in items:
            items.append(text)

    def _record_origin(self, field, key, existed, metadata, *, conservative_truncation=True):
        entries = self._record_metadata[field]
        if not existed:
            entries[key] = dict(metadata) if metadata is not None else None
        elif (key not in entries or entries[key] != metadata
              or (conservative_truncation and metadata is not None and (metadata.get("truncated") or metadata.get("subject_truncated")))):
            entries[key] = None

    def append_fact(self, fact: str, *, metadata=None) -> None:
        """开口后事实回流：本轮发生了什么，下一轮可用。"""
        key = fact.strip()
        if key:
            self._record_origin("facts", key, key in self._context.facts_this_session, metadata)
        self._append_unique(self._context.facts_this_session, fact)

    def append_stance_trace(self, kind: str, point: str, why: str = "", *, metadata=None) -> None:
        point = point.strip()
        if not point:
            return
        key = (kind, point)
        existed = any(t.kind == kind and t.point == point for t in self._context.stance_traces)
        self._record_origin("stance_traces", key, existed, metadata)
        if existed:
            if any(t.kind == kind and t.point == point and t.why != (why or "").strip()
                   for t in self._context.stance_traces):
                self._record_metadata["stance_traces"][key] = None
            return
        self._context.stance_traces.append(StanceTrace(kind=kind, point=point, why=(why or "").strip()))
        del self._context.stance_traces[:-20]
        live = {(t.kind, t.point) for t in self._context.stance_traces}
        self._record_metadata["stance_traces"] = {k: v for k, v in self._record_metadata["stance_traces"].items() if k in live}

    def record_stance_kept(self, point: str) -> None:
        if point:
            counts = self._context.stance_kept_counts
            counts[point] = counts.get(point, 0) + 1

    def set_drive_identity_ask_pending(self, pending: bool) -> None:
        self._context.drive_identity_ask_pending = pending

    def append_commitment(self, commitment: str, *, metadata=None) -> None:
        """开口后承诺回流：说出去的话要守。"""
        key = commitment.strip()
        if key:
            self._record_origin("last_commitments", key, key in self._context.last_commitments, metadata, conservative_truncation=False)
        self._append_unique(self._context.last_commitments, commitment)

    def append_commitment_candidate(self, candidate: CommitmentCandidate, *, metadata=None) -> None:
        candidates = self._context.commitment_candidates
        key = (candidate.target, candidate.text)
        self._record_origin("commitment_candidates", key, any((c.target, c.text) == key for c in candidates), metadata, conservative_truncation=False)
        if candidate not in candidates:
            candidates.append(replace(candidate))
            del candidates[:-20]
        live = {(c.target, c.text) for c in candidates}
        self._record_metadata["commitment_candidates"] = {k: v for k, v in self._record_metadata["commitment_candidates"].items() if k in live}

    def commitment_candidates(self) -> list[CommitmentCandidate]:
        return [replace(c) for c in self._context.commitment_candidates]

    def _remove_candidates(self, targets: set[str]) -> None:
        ctx = self._context
        ctx.commitment_candidates = [c for c in ctx.commitment_candidates if c.target not in targets]
        self._record_metadata["commitment_candidates"] = {k: v for k, v in self._record_metadata["commitment_candidates"].items() if k[0] not in targets}
        if ctx.prior_session:
            ctx.prior_session.commitment_candidates = [
                c for c in ctx.prior_session.commitment_candidates if c.target not in targets
            ]
            if ctx.prior_session.record_metadata is not None:
                entries = ctx.prior_session.record_metadata.get("commitment_candidates", {})
                ctx.prior_session.record_metadata["commitment_candidates"] = {k: v for k, v in entries.items() if k not in targets}

    def append_open_question(self, question: str, *, metadata=None) -> None:
        """动力层留下的悬而未决，供后续轮次捡起。"""
        key = question.strip()
        if key:
            self._record_origin("open_questions", key, key in self._context.open_questions, metadata)
        self._append_unique(self._context.open_questions, question)

    def append_her_question(self, q: str, *, metadata=None) -> None:
        key = q.strip()
        if key:
            self._record_origin("open_questions", key, key in self._context.open_questions, metadata)
            self._record_origin("her_questions", key, key in self._context.her_questions, metadata)
        self._append_unique(self._context.open_questions, q)
        self._append_unique(self._context.her_questions, q)

    def set_want_seen_pending(self, pending: bool) -> None:
        """Set or clear the separate cross-turn relational wait."""
        self._context.want_seen_pending = pending

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

    def resolve_open_question(self, match: str | None = None) -> str | None:
        """接完悬问：match=None 弹第一条；指定目标只精确弹该条，未命中返回 None。

        用在「本轮因悬问说过话」之后——捡一次就该接完，不留着长期占领主导。
        好奇挂起 flag 一并清 False（宁缺毋滥：resolve 即视为挂起已接）。
        """
        if match is not None and match not in self._context.open_questions:
            return None
        if self._context.open_questions:
            self._context.curiosity_hang_pending = False
            index = self._context.open_questions.index(match) if match is not None else 0
            result = self._context.open_questions.pop(index)
            self._record_metadata["open_questions"].pop(result, None)
            self._record_metadata["her_questions"].pop(result, None)
            self._context.her_questions = [q for q in self._context.her_questions if q in self._context.open_questions]
            return result
        self._context.her_questions = [q for q in self._context.her_questions if q in self._context.open_questions]
        return None

    def clear_open_questions(self) -> None:
        """放下同场所有悬问（用户换题、开了新话头时用）；好奇挂起 flag 一并清。"""
        self._context.open_questions.clear()
        self._record_metadata["open_questions"].clear()
        self._record_metadata["her_questions"].clear()
        self._context.her_questions = [q for q in self._context.her_questions if q in self._context.open_questions]
        self._context.curiosity_hang_pending = False

    def resolve_commitment(self, match: str | None = None) -> str | None:
        """兑现／接完指定承诺：精确匹配；旧调用不传 match 时仍取第一条。

        对齐 resolve_open_question；态度上可守的对象，接完可放下。
        改口否定 flag 一并清 False（承诺已了，改口线索无对象）。
        弹出的条目记入本场已兑现列表，供跨场落盘。
        """
        if self._context.last_commitments:
            if match is not None and match not in self._context.last_commitments:
                return None
            self._context.commitment_deny_pending = False
            index = self._context.last_commitments.index(match) if match is not None else 0
            done = self._context.last_commitments.pop(index)
            metadata = self._record_metadata["last_commitments"].pop(done, None)
            self._record_origin("resolved_commitments", done, done in self._resolved_commitments, metadata, conservative_truncation=False)
            self._remove_candidates({done})
            self._append_unique(self._resolved_commitments, done)
            return done
        return None

    def clear_commitments(self) -> None:
        """放下同场所有承诺（仅明确整场放下时用；宁缺毋滥）；改口否定 flag 一并清。"""
        self._remove_candidates(set(self._context.last_commitments))
        self._context.last_commitments.clear()
        self._record_metadata["last_commitments"].clear()
        # 候选元数据只随被删的候选走（_remove_candidates 已处理）；指向上场未兑现承诺的
        # 候选仍在本场，元数据必须留住，不能整片清空。
        self._context.commitment_deny_pending = False


    def set_drive_prior_commit_pending(self, pending: bool) -> None:
        """pipeline：上场未兑现承诺作 drive 线索（不强制开口；§6 仍看同场）。"""
        self._context.drive_prior_commit_pending = pending

    def set_drive_prior_her_question_pending(self, pending: bool) -> None:
        self._context.drive_prior_her_question_pending = pending

    def set_drive_prior_her_question_used(self) -> None:
        self._context.drive_prior_her_question_used = True

    def remove_prior_her_question(self, q: str) -> bool:
        prior = self._context.prior_session
        if prior is None or q not in prior.her_questions:
            return False
        prior.her_questions.remove(q)
        if self.prior_her_question_text == q:
            self.prior_her_question_text = ""
        return True

    def set_drive_prior_callback_pending(self, pending: bool) -> None:
        """pipeline：本轮跨场回指 pursue（须有 prior_session 结构；有同场承诺时不置）。"""
        self._context.drive_prior_callback_pending = pending

    def set_drive_prior_press_pending(self, pending: bool) -> None:
        """pipeline：本轮催兑现上场未了承诺（须有 prior.commitments_pending；有同场承诺时不置）。"""
        self._context.drive_prior_press_pending = pending

    def resolve_prior_commitment(self, match: str | None = None) -> str | None:
        """兑现上场 pending：从 prior_session.commitments_pending 弹出并记入 resolved。

        不并进同场 last_commitments（§6 仍只看同场）。match 若给则先全表找精确相等，
        找不到再按主题覆盖挑一条；否则弹第一条。无 prior／无 pending → None。
        """
        prior = self._context.prior_session
        if prior is None or not prior.commitments_pending:
            return None
        done = None
        if match is None:
            done = prior.commitments_pending.pop(0)
        else:
            from .commit_extract import utterance_covers_pending_commitment

            # 先全表找精确相等：两笔互相包含时，不能让主题覆盖先命中前一笔。
            exact_index = next(
                (i for i, p in enumerate(prior.commitments_pending) if p == match),
                None,
            )
            if exact_index is not None:
                done = prior.commitments_pending.pop(exact_index)
            else:
                # 没有精确相等，再按主题覆盖挑；保持原有回退。
                for i, p in enumerate(list(prior.commitments_pending)):
                    if utterance_covers_pending_commitment(match, p):
                        done = prior.commitments_pending.pop(i)
                        break
                if done is None:
                    return None
        self._remove_candidates({done})
        if prior.record_metadata is not None:
            pending_meta = prior.record_metadata.setdefault("commitments_pending", {})
            resolved_meta = prior.record_metadata.setdefault("commitments_resolved", {})
            metadata = pending_meta.pop(done, None)
            if done not in prior.commitments_resolved:
                if metadata is not None:
                    resolved_meta[done] = metadata
                else:
                    resolved_meta.pop(done, None)
            elif resolved_meta.get(done) != metadata:
                resolved_meta.pop(done, None)
        self._append_unique(prior.commitments_resolved, done)
        return done

    def set_prior_session(self, prior: PriorSessionTrace | None) -> None:
        """新场开局灌入上一场薄痕迹；None 表示无痕迹。"""
        self.prior_her_question_text = ""
        if prior is None:
            self._context.prior_session = None
            return
        self._context.prior_session = PriorSessionTrace(
            commitment_candidates=[replace(c) for c in prior.commitment_candidates],
            facts=list(prior.facts),
            commitments_pending=list(prior.commitments_pending),
            commitments_resolved=list(prior.commitments_resolved),
            open_questions=list(prior.open_questions),
            her_questions=list(prior.her_questions),
            ended_at=prior.ended_at,
            stance_traces=[StanceTrace(t.kind, t.point, t.why) for t in prior.stance_traces],
            record_metadata=self._copy_prior_metadata(prior.record_metadata),
        )

    def has_session_content(self) -> bool:
        """本场是否有可落盘的薄痕迹（空场不写）。"""
        ctx = self._context
        return bool(
            ctx.facts_this_session
            or ctx.last_commitments
            or ctx.commitment_candidates
            or self._resolved_commitments
            or ctx.open_questions
            or ctx.stance_traces
            or self._her_utterances
        )

    def export_session_trace(self) -> dict:
        """导出本场薄痕迹字典（供 BirthMemoryStore.append_session）。

        不含 articulate_reject_*／last_reject_reasons（拒收不跨场持久化）。
        """
        ctx = self._context
        # 继承来的悬问只续一场，用过没用过都放掉；本场新问句不在 prior_live 里，照常导出。
        prior_live = set(ctx.prior_session.her_questions) if ctx.prior_session else set()
        prior_commits = list(ctx.prior_session.commitments_pending) if ctx.prior_session else []
        combined = []
        for c in prior_commits + list(ctx.last_commitments):
            if c not in combined:
                combined.append(c)
        candidates = []
        resolved = list(dict.fromkeys(
            (ctx.prior_session.commitments_resolved if ctx.prior_session else [])
            + self._resolved_commitments
        ))
        prior_candidates = ctx.prior_session.commitment_candidates if ctx.prior_session else []
        for candidate in prior_candidates + ctx.commitment_candidates:
            if candidate.target in combined and candidate not in candidates:
                candidates.append(replace(candidate))
        prior_metadata = (ctx.prior_session.record_metadata or {}) if ctx.prior_session else {}

        def merged_metadata(name, local_name, prior_items, local_items, key=lambda item: item, nested=False):
            prior_keys = {key(item) for item in prior_items}
            local_keys = {key(item) for item in local_items}
            prior_entries = prior_metadata.get(name, {})
            local_entries = self._record_metadata[local_name]

            def prior_lookup(item):
                if nested:
                    outer, inner = key(item)
                    return (prior_entries.get(outer) or {}).get(inner)
                return prior_entries.get(key(item))

            def get(item):
                k = key(item)
                old, new = prior_lookup(item), local_entries.get(k)
                if k in prior_keys and k in local_keys:
                    return old if old == new else None
                return old if k in prior_keys else new
            return get

        pending_meta = merged_metadata("commitments_pending", "last_commitments", prior_commits, ctx.last_commitments)
        resolved_meta = merged_metadata("commitments_resolved", "resolved_commitments", ctx.prior_session.commitments_resolved if ctx.prior_session else [], self._resolved_commitments)
        candidate_meta = merged_metadata("commitment_candidates", "commitment_candidates", prior_candidates, ctx.commitment_candidates, lambda c: (c.target, c.text), nested=True)
        return {
            "commitment_candidates": candidates,
            "facts": list(ctx.facts_this_session),
            "commitments_pending": combined,
            "commitments_resolved": resolved,
            "open_questions": list(ctx.open_questions),
            "her_questions": [
                q for q in ctx.her_questions
                if q in ctx.open_questions and q not in prior_live
            ],
            "stance_traces": list(ctx.stance_traces),
            "her_utterances": [asdict(entry) for entry in self._her_utterances],
            "record_metadata": {
                "facts": [self._record_metadata["facts"].get(x) for x in ctx.facts_this_session],
                "open_questions": [self._record_metadata["open_questions"].get(x) for x in ctx.open_questions],
                "her_questions": [self._record_metadata["her_questions"].get(q) for q in ctx.her_questions if q in ctx.open_questions and q not in prior_live],
                "stance_traces": [self._record_metadata["stance_traces"].get((t.kind, t.point)) for t in ctx.stance_traces],
                "commitments_pending": [pending_meta(c) for c in combined],
                "commitments_resolved": [resolved_meta(c) for c in resolved],
                "commitment_candidates": [candidate_meta(c) for c in candidates],
            },
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

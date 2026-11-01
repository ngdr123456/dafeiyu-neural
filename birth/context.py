"""ThinContext 存储：同场积累；显式 new_session 才清空；开口后回流入口。

设计要点（对齐 PHASE1_BRIEF.md 第 2 条）：
- 不做每句改性格，也不顶置长期性格记忆；只存本轮/同场要用的东西。
- 唯一的清空入口是 :meth:`ThinContextStore.new_session`，其余只积累；
  唯一的两个例外是悬问的收放：resolve_open_question（接完一条）与
  clear_open_questions（用户换题时放下），只动 open_questions，不动事实/承诺。
- 回流入口：append_fact / append_commitment；append_open_question 供动力层挂悬而未决。
"""

from __future__ import annotations

from .types import ThinContext


class ThinContextStore:
    """持有当前同场的 ThinContext，并提供回流写入方法。"""

    def __init__(self, context: ThinContext | None = None) -> None:
        self._context = context if context is not None else ThinContext()

    @property
    def context(self) -> ThinContext:
        """内部可写上下文（仅 pipeline 与 store 自身使用）。"""
        return self._context

    def snapshot(self) -> ThinContext:
        """给仲裁/Brief 用的副本，避免台下引用被外部改穿存储。"""
        ctx = self._context
        return ThinContext(
            session_ok=ctx.session_ok,
            open_questions=list(ctx.open_questions),
            last_commitments=list(ctx.last_commitments),
            facts_this_session=list(ctx.facts_this_session),
        )

    def new_session(self) -> None:
        """唯一的清空入口：只有显式 new_session 才会清掉同场积累。"""
        self._context = ThinContext()

    # -- 积累（只加不减，精确重复去重避免自我灌水） ----------------------

    @staticmethod
    def _append_unique(items: list[str], text: str) -> None:
        text = text.strip()
        if text and text not in items:
            items.append(text)

    def append_fact(self, fact: str) -> None:
        """开口后事实回流：本轮发生了什么，下一轮可用。"""
        self._append_unique(self._context.facts_this_session, fact)

    def append_commitment(self, commitment: str) -> None:
        """开口后承诺回流：说出去的话要守。"""
        self._append_unique(self._context.last_commitments, commitment)

    def append_open_question(self, question: str) -> None:
        """动力层留下的悬而未决，供后续轮次捡起。"""
        self._append_unique(self._context.open_questions, question)

    def resolve_open_question(self) -> str | None:
        """接完第一条悬问：弹出并返回它；没有悬问时返回 None。

        用在「本轮因悬问说过话」之后——捡一次就该接完，不留着长期占领主导。
        """
        if self._context.open_questions:
            return self._context.open_questions.pop(0)
        return None

    def clear_open_questions(self) -> None:
        """放下同场所有悬问（用户换题、开了新话头时用）。"""
        self._context.open_questions.clear()

    # -- 只读视图 ----------------------------------------------

    def pending_commitments(self) -> list[str]:
        return list(self._context.last_commitments)

    def pending_questions(self) -> list[str]:
        return list(self._context.open_questions)

"""出生旁路主管线：turn() 串起 感知 → 动力 → 立场/组织 → 仲裁 → 开口 → 回流。

- 旧 engine/ 旧管线不改动、不 import；
- 同场状态放在模块级 ThinContextStore，只有 turn(..., new_session=True) 清空；
- 开口后事实/悬起/薄承诺回流 ThinContext（extract_commitment 宁缺毋滥）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .arbitrate import arbitrate
from .articulate import articulate, last_articulate_source
from .commit_extract import extract_commitment, should_resolve_commitment
from .openq_extract import (
    extract_open_question,
    should_clear_open_questions,
    should_resolve_open_question,
)
from .context import ThinContextStore
from .drive import infer_drive
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
) -> TurnResult:
    """跑完一轮完整闭环。new_session=True 显式开新场（唯一清空入口）。

    debug 只是让工程师通道外显得更方便（CLI 用它打印 Brief）；管线行为不受影响。
    stub=True 强制模板开口；None 跟随 articulate 全局/环境（默认可走 LLM）。
    """
    if new_session:
        _STORE.new_session()

    context = _STORE.snapshot()

    drive = infer_drive(user_text, context)
    stance = default_stance(user_text, context)
    org = default_org(context, drive=drive, stance=stance, user_text=user_text)
    brief = arbitrate(drive=drive, stance=stance, org=org, context=context,
                      user_text=user_text)

    utterance = articulate(brief, stub=stub)

    # 悬问收放（可检验；对齐承诺宁缺——拿不准不清）：
    # - resolve：读 Brief.openq_resolve（禁止 say_intent 中文子串）；
    # - clear：真开新话头／用户明示放下；闲聊／改口否定／身份问勿误清。
    if should_resolve_open_question(
        brief=brief, user_text=user_text, has_open=bool(context.open_questions)
    ):
        _STORE.resolve_open_question()
    elif should_clear_open_questions(
        user_text=user_text, has_open=bool(context.open_questions)
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
        _STORE.append_open_question(f"待接的话头：{_clip(user_text)}")
    else:
        open_q = extract_open_question(utterance)
        if open_q:
            _STORE.append_open_question(open_q)

    return TurnResult(
        utterance=utterance,
        brief=brief,
        articulate_source=last_articulate_source(),
    )

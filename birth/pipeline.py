"""出生旁路主管线：turn() 串起 感知 → 动力 → 立场/组织 → 仲裁 → 开口 → 回流。

- 旧 engine/ 旧管线不改动、不 import；
- 同场状态放在模块级 ThinContextStore，只有 turn(..., new_session=True) 清空；
- 开口后事实/悬起/薄承诺回流 ThinContext（extract_commitment 宁缺毋滥）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .arbitrate import arbitrate
from .articulate import articulate, last_articulate_source
from .commit_extract import extract_commitment
from .context import ThinContextStore
from .drive import CURIOSITY_MARKS, infer_drive, is_neutral_filler
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

    # 悬问的收放（先于新回流写入，用的是本轮开始时的快照）：
    # - 本轮因悬问说过话（filler 且确有悬问 → meaning 短暂捡一次）→ 接完第一条；
    # - 本轮是新实质内容（非 filler）→ 旧悬问放下，眼前的话头优先；
    # - 非 filler 且本轮正好把悬问捡起来了（drive pursue 顺着悬问）→ 同样放下。
    spoke_for_open_question = (
        brief.dominant == "meaning"
        and not context.last_commitments
        and bool(context.open_questions)
    )
    if spoke_for_open_question:
        _STORE.resolve_open_question()
    elif not is_neutral_filler(user_text) and context.open_questions:
        _STORE.clear_open_questions()

    # 开口后回流薄情境：本轮用户的话头 + 台上这句都 clip 进同场事实；
    # 动力层的好奇追问入库；台上若像答应/约定则薄提取承诺（宁缺毋滥）
    _STORE.append_fact(f"用户说：{_clip(user_text)}")
    _STORE.append_fact(f"台上说：{_clip(utterance)}")
    commitment = extract_commitment(utterance)
    if commitment:
        _STORE.append_commitment(commitment)
    if (drive.direction == "pursue"
            and any(mark in user_text for mark in CURIOSITY_MARKS)):
        _STORE.append_open_question(f"待接的话头：{_clip(user_text)}")

    return TurnResult(
        utterance=utterance,
        brief=brief,
        articulate_source=last_articulate_source(),
    )

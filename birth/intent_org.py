"""意图层：判断「顺着答就会踩 must_not_pretend」——不是扩词表命中。

规格债：禁止再往 EXPERIENCE/SELF_CODE_*_MARKS 堆条目。
这里用封闭的意图范畴（向「你」索要亲历事实 / 把说话人钉成程序基底），
只写冲突交给仲裁；不挡话、不作禁词闸。
"""

from __future__ import annotations

import re

from .input_contract import InputSignal

def demands_lived_biography(text: str, understanding: InputSignal | None = None) -> bool:
    """Consume credible, scoped understanding; unknown input is not a conflict."""
    return bool(understanding is not None and not understanding.degraded
                and understanding.confidence == "high"
                and understanding.experience_intent == "impersonation"
                and understanding.experience_scope.strip()
                and len(understanding.experience_scope) <= 600
                and understanding.experience_scope in (text or ""))


# 名词后接「员/猿/高手/大神/水平」是在说人（程序员、代码高手），不是基底身份。
_SUBSTRATE_NOUN = r"(?:代码|程序|模型|AI|ai|人工智能|机器人)(?!员|猿|高手|大神|水平)"
_COPULA = r"(?:是不是|算不算|不是|就是|只是|算是|是)"
_QUANT = r"(?:一?[段个堆串套台款种]|个)?"
# 问身份的形状：你（＋≤4 字副词，如「其实/本质上/到底」）＋系词＋（量词）＋基底名词；
# 或无「你」时「底层/本质（上）＋系词＋（量词）＋基底名词」。
_SUBSTRATE_IDENTITY = re.compile(
    r"你[^，。？！?!,、\s]{0,4}?" + _COPULA + _QUANT + _SUBSTRATE_NOUN
    + r"|(?:底层|本质)上?" + _COPULA + _QUANT + _SUBSTRATE_NOUN)


def demands_substrate_identity(text: str) -> bool:
    """意图：把说话人钉成代码/程序/模型等基底身份。

    V2.1 3a：只认「问身份」的形状（你＋是/不是/算不算…＋代码类名词），
    不再按「你」与「代码/程序/模型/AI」共现判——「你帮我看下这段代码」不触发。
    感知目前没有身份提问字段（InputSignal 无此项），故只按形状。"""
    t = (text or "").strip()
    return bool(_SUBSTRATE_IDENTITY.search(t))


def intent_org_conflicts(user_text: str, *, understanding: InputSignal | None = None) -> list[str]:
    """返回本轮意图踩到的 must_not_pretend 条目（可空）。"""
    conflicts: list[str] = []
    if demands_lived_biography(user_text, understanding):
        conflicts.append("无来源装经历")
    if demands_substrate_identity(user_text):
        conflicts.append("自述是代码")
    return conflicts

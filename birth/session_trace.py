"""同场痕迹：回指检测与薄事实摘要（体验通道，非长期性格库）。"""

from __future__ import annotations

from typing import List

from .types import ThinContext

# 回指线索：识别「在指同场刚说过的」，不是禁词表
BACKREF_MARKS = (
    "刚才",
    "上面",
    "还记得",
    "那个",
    "之前说",
    "前面那个",
    "刚说",
    "刚才说",
    "上一句",
    "上头",
)


def is_session_backref(user_text: str, context: ThinContext) -> bool:
    """用户话像在回指，且本场已有痕迹。"""
    text = (user_text or "").strip()
    if not text or not context.facts_this_session:
        return False
    return any(mark in text for mark in BACKREF_MARKS)


def recent_facts(context: ThinContext, n: int = 3) -> List[str]:
    facts = list(context.facts_this_session or [])
    if n <= 0:
        return []
    return facts[-n:]


def topic_hint_from_facts(facts: List[str]) -> str:
    """从「用户说：…」里抠可点到的话题词；优先开话题句，跳过回指／催答应。"""
    open_prefixes = (
        "我想聊",
        "我想说说",
        "我想说",
        "咱们聊",
        "我们聊",
        "聊聊",
        "说下",
        "说一下",
        "谈谈",
    )
    skip_if = BACKREF_MARKS + (
        "你答应",
        "答应一下",
        "答应我",
        "说好了吗",
        "你记一下",
        "你好",
        "够了",
        "先这样",
    )

    def _body(fact: str) -> str:
        body = fact[len("用户说："):].rstrip("…").strip()
        for prefix in open_prefixes:
            if body.startswith(prefix):
                return body[len(prefix):].strip(" 。，,！？!?")
        return body.strip(" 。，,！？!?")

    # 1) 优先：明确打开话题的用户句
    for fact in reversed(facts or []):
        if not fact.startswith("用户说："):
            continue
        raw = fact[len("用户说："):].rstrip("…").strip()
        for prefix in open_prefixes:
            if raw.startswith(prefix):
                body = raw[len(prefix):].strip(" 。，,！？!?")
                if body:
                    return body
    # 2) 否则最近一条非回指／非催答应的用户句
    for fact in reversed(facts or []):
        if not fact.startswith("用户说："):
            continue
        body = _body(fact)
        if not body:
            continue
        if any(m in body for m in skip_if):
            continue
        return body
    return ""


# 跨场回指线索：识别「在指上一场」，不是禁词表；放行须另有 prior_session 结构
PRIOR_BACKREF_MARKS = (
    "上次",
    "上一回",
    "上场",
    "之前那次",
    "上一场",
)


def is_prior_session_backref(user_text: str, context: ThinContext) -> bool:
    """用户话像在回指上一场，且 prior_session 结构有痕迹。

    放行／pursue 依据是 prior_session.has_trace()，不是关键词本身。
    无痕迹时返回 False（「上次」不单独构成跨场回指）。
    """
    prior = getattr(context, "prior_session", None)
    if prior is None or not prior.has_trace():
        return False
    text = (user_text or "").strip()
    if not text:
        return False
    return any(mark in text for mark in PRIOR_BACKREF_MARKS)


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
    """从最近「用户说：…」里抠一点可点到的话题词；抠不出就空串。"""
    for fact in reversed(facts or []):
        if not fact.startswith("用户说："):
            continue
        body = fact[len("用户说：") :].rstrip("…").strip()
        for prefix in (
            "我想聊",
            "我想说说",
            "我想说",
            "咱们聊",
            "我们聊",
            "聊聊",
            "说下",
            "说一下",
            "谈谈",
        ):
            if body.startswith(prefix):
                body = body[len(prefix) :].strip()
                break
        body = body.strip(" 。，,！？!?")
        if body:
            return body
    return ""

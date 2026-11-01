"""开口后薄提取承诺：宁缺毋滥；不是禁词表。"""

from __future__ import annotations

import re

# 答应／约定形状（输入侧轻量线索）
_COMMIT_SHAPES = (
    "我晚点",
    "我回头",
    "下次",
    "改天",
    "我答应",
    "说好",
    "咱们说好",
    "先记下",
    "我记下",
    "回头再",
    "晚点再",
    "稍后",
)

# 明确排除：寒暄／收束／身份／纯回指
_EXCLUDE_MARKS = (
    "嗨",
    "我在呢",
    "你好",
    "先这样",
    "够了",
    "不用了",
    "是不是代码",
    "不认死",
    "没有来处",
    "记得，你刚才",
    "嗯，听着",
)


def user_presses_commitment(user_text: str) -> bool:
    """用户侧催答应／约定（轻量线索）；供仲裁写 say_intent，不是禁词。"""
    text = (user_text or "").strip()
    if not text:
        return False
    marks = (
        "你答应",
        "答应一下",
        "答应我",
        "说好了吗",
        "说好啊",
        "咱们说好",
        "你记一下",
        "你记下",
        "约定好",
        "说定了",
    )
    return any(m in text for m in marks)


def extract_commitment(utterance: str) -> str | None:
    """台上开口像「答应／约定下一件可核对的事」→ 短摘；否则 None。"""
    text = (utterance or "").strip()
    if not text or len(text) < 6:
        return None
    if any(mark in text for mark in _EXCLUDE_MARKS):
        # 整句若主要是排除形态且没有强约定，跳过
        if not any(s in text for s in ("我答应", "说好", "先记下", "我记下")):
            if any(mark in text for mark in ("嗨", "我在呢", "够了", "先这样", "不用了", "嗯，听着", "记得，你刚才")):
                return None

    if not any(shape in text for shape in _COMMIT_SHAPES):
        return None

    # 还要有一点「后续可核对」：再…／聊…／跟你…／把…／补…
    if not re.search(r"(再|聊|跟你|把|补|说|谈|讲|回)", text):
        return None

    # 短摘：优先截含约定线索的那一段
    clip = text
    for shape in _COMMIT_SHAPES:
        idx = text.find(shape)
        if idx >= 0:
            clip = text[idx:]
            break
    clip = clip.strip()
    if len(clip) > 40:
        clip = clip[:40] + "…"
    return clip or None

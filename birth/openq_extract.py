"""开口后薄提取悬问：宁缺毋滥；不是禁词表。"""

from __future__ import annotations

import re
import unicodedata


def answered_open_question(user_text: str, questions: list[str]) -> bool:
    """Conservative topic overlap, not a semantic answer classifier."""
    from .drive import is_neutral_filler, _extract_open_topic
    from .stance_org import _denies_commitment

    text = (user_text or "").strip()
    if (is_neutral_filler(text) or _denies_commitment(text) or len(text) < 4
            or _extract_open_topic(text) or user_marks_open_question_putdown(text)):
        return False
    if any(mark in text for mark in ("?", "？")):
        return False
    # Only contiguous CJK pairs or whole Latin words; skip question scaffolding.
    noise = {"为什么", "什么", "怎么", "如何", "你想", "哪头", "是否", "这个", "那个"}
    def tokens(s: str) -> set[str]:
        result = set(re.findall(r"[A-Za-z0-9]{3,}", s.lower()))
        for run in re.findall(r"[\u4e00-\u9fff]+", s):
            result.update(run[i:i+2] for i in range(len(run)-1) if run[i:i+2] not in noise)
        return result
    return bool(questions and tokens(questions[0]) & tokens(text))

# 问对方的轻量形状
_ASK_MARKS = ("吗", "呢", "要不要", "要不要先", "哪头", "哪边", "怎么看", "你想")

# 排除：身份套话、纯寒暄
_EXCLUDE = (
    "是不是代码",
    "是不是程序",
    "我是不是",
    "嗨，我在呢",
    "我在呢",
    "你好呀",
    "在吗",  # 台上不应把寒暄当悬问挂起
)


def extract_open_question(utterance: str) -> str | None:
    """台上开口向对方抛出可接的问句 → 短摘；否则 None。"""
    text = (utterance or "").strip()
    if not text or len(text) < 4:
        return None
    if any(x in text for x in _EXCLUDE):
        return None

    has_qmark = ("？" in text) or ("?" in text)
    has_ask = any(m in text for m in _ASK_MARKS)
    if not (has_qmark or has_ask):
        return None
    # 至少像在问对方：有问号，或「吗/呢/要不要」且不像自言自语短填充
    if not has_qmark and not any(m in text for m in ("吗", "呢", "要不要", "哪头", "你想")):
        return None

    clip = text
    # 优先从问句片段截
    for sep in ("？", "?"):
        if sep in text:
            # 取含问号的最后一小段的前文
            parts = text.replace("?", "？").split("？")
            # 最后非空问句段
            for part in reversed(parts):
                part = part.strip()
                if part:
                    clip = part + "？"
                    break
            break
    clip = clip.strip()
    if has_qmark:
        clip = re.split(r"[。！!\n]", clip)[-1].strip()
    if len(clip) > 40:
        clip = "…" + clip[-40:] if has_qmark else clip[:40] + "…"
    if not any(not c.isspace() and not unicodedata.category(c).startswith("P") for c in clip):
        return None
    return clip or None


# 放下／换题：可检验线索（宁缺毋滥；不是禁词堵嘴）
_PUTDOWN_MARKS = (
    "先放下",
    "先不说这个",
    "换个话题",
    "别提那个了",
    "不问了",
    "这个先搁下",
    "悬着的先放",
    "刚才那个先别问",
)


def user_marks_open_question_putdown(user_text: str) -> bool:
    text = (user_text or "").strip()
    if not text:
        return False
    return any(m in text for m in _PUTDOWN_MARKS)


# 与 ThoughtBrief.openq_resolve 同一语义：arbitrate 写、此处读；改口文案不静默失效
OPENQ_RESOLVE_FLAG = True  # Brief.openq_resolve 的约定真值


def should_resolve_open_question(*, brief, user_text: str, has_open: bool) -> bool:
    """仅当 Brief 结构化标记 openq_resolve（+ meaning）才 resolve。

    禁止只靠中文 say_intent 子串；drive「适时捡起」不会置位该标记。
    """
    if not has_open:
        return False
    if getattr(brief, "dominant", None) != "meaning":
        return False
    return bool(getattr(brief, "openq_resolve", False)) is OPENQ_RESOLVE_FLAG


# 与 ThoughtBrief.openq_clear 同一语义：arbitrate 写、此处读；改口文案不静默失效
OPENQ_CLEAR_FLAG = True  # Brief.openq_clear 的约定真值


def should_clear_open_questions(
    *, brief, has_open: bool, user_text: str = ""
) -> bool:
    """换题 clear 可检验化：仅当 Brief 结构化标记 openq_clear（+ has_open）才 clear。

    与 should_resolve_open_question 同语义：arbitrate 写、此处读；改口文案不静默失效。
    user_text 仅作兼容保留，此处不再扫放下／开题词表。
    """
    if not has_open:
        return False
    return bool(getattr(brief, "openq_clear", False)) is OPENQ_CLEAR_FLAG

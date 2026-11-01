"""开口后薄提取悬问：宁缺毋滥；不是禁词表。"""

from __future__ import annotations

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
    if len(clip) > 40:
        clip = clip[:40] + "…"
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


def should_resolve_open_question(*, brief, user_text: str, has_open: bool) -> bool:
    """仅当本轮确因悬问说过话（filler 短暂 meaning 接完）才 resolve。

    勿把 drive「适时捡起悬着」当成接完——那只是可捡话头，不是 resolve。
    """
    if not has_open:
        return False
    intent = getattr(brief, "say_intent", "") or ""
    # 与 arbitrate：open_questions + filler → meaning 口径逐字对齐
    if "就着眼前这句把同场悬着的那一点接完" in intent:
        return True
    return False


def should_clear_open_questions(*, user_text: str, has_open: bool) -> bool:
    """换题 clear 须可检验：真开新话头或用户明示放下。闲聊／改口／身份勿清。"""
    if not has_open:
        return False
    text = (user_text or "").strip()
    if not text:
        return False
    if user_marks_open_question_putdown(text):
        return True
    # 真开新话头（复用动力层前缀，避免另造词表堵嘴）
    from .drive import _extract_open_topic
    if _extract_open_topic(text):
        return True
    return False

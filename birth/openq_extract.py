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

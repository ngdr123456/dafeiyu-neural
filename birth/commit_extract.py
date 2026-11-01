"""开口后薄提取承诺：宁缺毋滥；不是禁词表。"""

from __future__ import annotations

import re

# 与 ThoughtBrief.press_commit 同一语义：arbitrate 写、articulate 读
PRESS_COMMIT_FLAG = True

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


# 兑现／放下：用户侧轻量线索（宁缺毋滥；不是禁词堵嘴，未命中就不清）
_FULFILL_USER_MARKS = (
    "兑现了",
    "补过了",
    "你补了",
    "已经补了",
    "你说过了",
    "说过了",
    "那件事补完",
    "算你兑现",
    "这句兑现了",
)

# 台上像把 pending 可核对后续接上的轻量形状
_DELIVER_UTTER_MARKS = (
    "接着聊",
    "补上",
    "补一下",
    "说到这",
    "就聊",
    "先把这事说完",
    "把前面那句接上",
)


def user_marks_commitment_done(user_text: str) -> bool:
    """用户明确示意那件约定已补／已兑现。"""
    text = (user_text or "").strip()
    if not text:
        return False
    return any(m in text for m in _FULFILL_USER_MARKS)


def utterance_covers_pending_commitment(utterance: str, commitment: str) -> bool:
    """台上开口是否把 pending 承诺的可核对后续接上（宁缺毋滥）。

    要求：承诺短摘里能抠到一点内容词，且开口含该词 + 接上形状；
    拿不准（抠不出内容）→ False，不清。
    """
    utt = (utterance or "").strip()
    pending = (commitment or "").strip()
    if not utt or not pending or len(pending) < 4:
        return False
    if not any(m in utt for m in _DELIVER_UTTER_MARKS):
        return False
    # 从承诺里去掉约定壳，抠一点内容
    body = pending
    for shape in _COMMIT_SHAPES:
        body = body.replace(shape, " ")
    for noise in ("好，", "。", "，", "、", "…", "跟你", "再"):
        body = body.replace(noise, " ")
    tokens = [w for w in body.split() if len(w) >= 2]
    if not tokens:
        # 无空格中文：取连续 2+ 字片段中最长的非壳残留
        compact = "".join(ch for ch in pending if ch not in "好，。、… ")
        for shape in sorted(_COMMIT_SHAPES, key=len, reverse=True):
            compact = compact.replace(shape, "")
        tokens = [compact[i:i+2] for i in range(0, max(0, len(compact) - 1)) if compact[i:i+2].strip()]
        tokens = [t for t in tokens if t and t not in ("跟你", "再聊", "晚点")]
    # 至少有一个内容词出现在开口里
    for tok in tokens:
        if len(tok) >= 2 and tok in utt:
            return True
    return False


def should_resolve_commitment(
    *,
    user_text: str,
    utterance: str,
    pending_first: str | None,
) -> bool:
    """可检验才 resolve；拿不准返回 False（不清）。不扩成通用嘴闸。"""
    if not pending_first:
        return False
    if user_marks_commitment_done(user_text):
        return True
    if utterance_covers_pending_commitment(utterance, pending_first):
        return True
    return False

"""V2.1 第三步：同一概念只留一份词表定义（输入侧轻量线索，不是禁词闸）。

各模块从这里取，不再各自维护近义副本。取舍理由见
tests/_offline_v21_step3_lexicon_*/report.md（逐词列）。
"""

from __future__ import annotations

import re

# 明确打开话题（前缀；drive._extract_open_topic 允许句首 0–4 字内出现，
# session_trace.topic_hint_from_facts 只认句首）。
# 并集来源：drive.OPEN_TOPIC_PREFIXES ∪ session_trace.open_prefixes；
# 剔除（过宽）：「我想说」（多为表态/反驳，如「我想说你错了」）、「说下」「说一下」（多为请对方说，如「你说一下」）。
OPEN_TOPIC_PREFIXES = (
    "我想聊", "我想说说", "我想说一下", "跟你说件", "跟你说一下", "跟你说个",
    "我们谈谈", "咱们谈谈", "咱们聊", "我们聊", "聊聊", "谈谈",
)

# 收束／满足（喜欢侧已接住，不必再追）。
# 并集来源：drive.SATISFIED_MARKS ∪ session_trace 两处 skip 里的「够了」「先这样」；
# 剔除（过宽）：「挺好的」（评价句，如「这道菜挺好的」，不是收束）。
SATISFIED_MARKS = (
    "够了", "先这样", "不用了", "就这样吧", "先到这", "可以了",
    "行了就这样", "先到这里", "暂时不用", "就先这样",
)

# 放下／换话题（悬问放下与话题改向切点同一概念）。
# 并集来源：openq_extract._PUTDOWN_MARKS ∪ session_trace.TOPIC_REDIRECT_MARKS；无剔除。
TOPIC_DROP_MARKS = (
    "先放下", "先不说这个", "换个话题", "别提那个了", "不问了", "这个先搁下",
    "悬着的先放", "刚才那个先别问",
    "换话题", "先不说", "不说这个了", "聊点别的", "说点别的",
)

# 原 pipeline.turn 内联整句字面（V2.1 3d 迁出；均为短语，非类级感知字段；无新增词）。
BODY_IMAGINE_MARKS = ("想象一下亲眼看看",)
NECESSARY_PAIN_MARKS = ("只能面对", "躲不掉", "必须承受")
SELF_TORTURE_MARKS = ("我就是要难受", "偏要跟自己过不去", "不痛苦就没意义")

# V2.1 3e：近因时间指示词（替代 input_sense 的整句剧本正则；只看词，不看句形）。
RECENCY_DEICTIC_MARKS = ("上次", "先前", "刚才", "previous", "prior", "earlier")
# 显式更早／另一次：不是「最近一次」，不绑最近、不升置信。
EXPLICIT_OLDER_MARKS = ("上上次", "更早", "最早", "第一次", "最开始", "头一次", "另一次", "另外一次",
                        "another", "different", "separate", "first", "earliest", "before that")


def _has_mark(text: str, marks) -> bool:
    for mark in marks:
        if mark.isascii():
            if re.search(r"\b" + re.escape(mark) + r"\b", text):
                return True
        elif mark in text:
            return True
    return False


def has_bare_recency_deictic(text: str) -> bool:
    """原话含光杆近因时间指示词，且没有显式更早／另一次的指称。只看词，不看整句形状。"""
    t = (text or "").strip().lower()
    if not _has_mark(t, RECENCY_DEICTIC_MARKS):
        return False
    return not _has_mark(t, EXPLICIT_OLDER_MARKS)

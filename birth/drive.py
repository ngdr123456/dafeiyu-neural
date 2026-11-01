"""动力层最小实现：user_text + ThinContext -> DriveSignal。

明确不做：
- 装饰分数（重要度/热度打分）并当成性格——这里只有 direction/salience/why 三槽位；
- 禁词表 / regex 堵嘴——下面这些词只是识别「有没有动力」的线索，不是拒绝话路的闸门。

允许留空：direction 可为 None（没有推力也是状态）。why 允许好奇类理由：
好奇本身就是动力的合法来源，不需要别的借口。
"""

from __future__ import annotations

from .context import ThinContextStore  # noqa: F401  (类型提示用)
from .types import DriveSignal, ThinContext

GREETINGS = {
    "你好", "您好", "hello", "hi", "hi!", "hi~", "嗨", "嗨~", "哈喽", "哈罗",
    "早上好", "中午好", "下午好", "晚上好", "晚安", "在吗", "在么", "hello!",
}
NEUTRAL_FILLERS = {"嗯", "嗯嗯", "嗯。", "哦", "哦哦", "喔", "好", "好的", "ok",
                   "okay", "行", "行吧", "好吧", "?", "？？"}

# 好奇类线索：用户在问「为什么/怎么回事」，好奇本身即可驱动
CURIOSITY_MARKS = ("为什么", "怎么会", "怎么回事", "为什么呀", "凭什么", "啥区别",
                   "有何不同", "好奇", "想知道", "说不上来为啥")

STORY_MARKS = ("过去", "从前", "你说过", "你的经历", "你小时候")  # 只有识别记忆依赖时才用


def _is_greeting(text: str) -> bool:
    return text in GREETINGS or (len(text) <= 4 and "你好" in text)


def is_neutral_filler(text: str) -> bool:
    """识别「嗯/好」这类没推力的接话。公开给仲裁/pipeline 用：
    本轮是不是 filler 决定悬问能不能短暂 meaning 捡一次。"""
    return (text or "").strip() in NEUTRAL_FILLERS or len((text or "").strip()) <= 2


def infer_drive(user_text: str, context: ThinContext) -> DriveSignal:
    """单人单轮的最小动力推断。规则可调，但三槽位不增：无装饰分数。"""
    text = (user_text or "").strip()

    if _is_greeting(text):
        return DriveSignal(
            direction="hold",
            salience="low",
            why="招呼类开场，没有要推进的事；稳住场子即可，想聊什么听用户的",
        )

    if is_neutral_filler(text):
        return DriveSignal(
            direction=None,
            salience="low",
            why="这一句没有推力，也不必硬造一个；如实回应即可",
        )

    if any(mark in text for mark in CURIOSITY_MARKS):
        return DriveSignal(
            direction="pursue",
            salience="high",
            why="用户问出了『为什么』类问题，好奇本身就是够格的推力，顺着看清楚",
        )

    if context.last_commitments:
        first = context.last_commitments[0]
        return DriveSignal(
            direction="hold",
            salience="mid",
            why=f"同场有没兑现的话（{first}），这轮不能当没说过",
        )

    if context.open_questions:
        first = context.open_questions[0]
        return DriveSignal(
            direction="pursue",
            salience="mid",
            why=f"同场还有悬而未决的问题（{first}），可以适时捡起来",
        )

    return DriveSignal(
        direction=None,
        salience="low",
        why="陈述类的话，没有明显推力方向；如实接住，不硬造动力",
    )

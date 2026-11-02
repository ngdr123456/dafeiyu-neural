"""动力层：user_text + ThinContext -> DriveSignal（DRIVE_V1）。

对齐《贪婪的多巴胺》：想要 ≠ 喜欢／满足；预期落空会改推力。
槽位只有 direction / salience / why；禁止装饰分数当性格；不上台播报追守停。
线索只在输入侧，不是禁词闸门。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .context import ThinContextStore  # noqa: F401  (类型提示用)
from .session_trace import is_session_backref, topic_hint_from_facts
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

# 满足／收束（喜欢侧已接住，不必再追）
SATISFIED_MARKS = (
    "够了", "先这样", "挺好的", "不用了", "就这样吧", "先到这", "可以了",
    "行了就这样", "先到这里", "暂时不用", "就先这样",
)

# 明确打开话题
OPEN_TOPIC_PREFIXES = (
    "我想聊", "我想说说", "我想说一下", "跟你说件", "跟你说一下", "跟你说个",
    "我们谈谈", "咱们谈谈", "咱们聊", "我们聊", "聊聊", "谈谈",
)

# 空追失望（轻量）
DISAPPOINT_MARKS = (
    "你怎么老这样", "还是没回答", "你又没答", "答非所问", "你有没有在听",
    "怎么老是这样", "还是没说清楚",
)

_EMPTY_STAGE_MARKS = ("嗯，听着", "你想让接几句", "这句我接", "听着呢")


@dataclass
class DriveCues:
    """结构化线索：主路径先读上下文结构，不再先扫输入侧词表。"""

    commitments_present: bool = False
    open_question_pending: bool = False
    # 同场好奇挂起仍 pending：主路径读 ThinContext.curiosity_hang_pending 结构化布尔
    curiosity_hang_pending: bool = False
    session_ok: bool = True


def drive_cues_from_context(context: ThinContext) -> DriveCues:
    """从 ThinContext 抽结构化线索（不扫用户输入侧词表）。

    好奇挂起主路径读 ThinContext.curiosity_hang_pending 布尔。
    兜底范围：仅当结构化 flag 缺省/False 时，才扫 open_questions 是否以
    「待接的话头：」开头（兼容旧快照／未写 flag 的路径）；
    不是禁词闸门，不扩词表，不改台上话术。
    """
    flag = bool(getattr(context, "curiosity_hang_pending", False))
    prefix_fallback = any(
        q.startswith("待接的话头：") for q in (context.open_questions or [])
    )
    return DriveCues(
        commitments_present=bool(context.last_commitments),
        open_question_pending=bool(context.open_questions),
        curiosity_hang_pending=flag or prefix_fallback,
        session_ok=context.session_ok,
    )


def _is_greeting(text: str) -> bool:
    return text in GREETINGS or (len(text) <= 4 and "你好" in text)


def is_neutral_filler(text: str) -> bool:
    """识别「嗯/好」这类没推力的接话。公开给仲裁/pipeline 用：
    本轮是不是 filler 决定悬问能不能短暂 meaning 捡一次。"""
    return (text or "").strip() in NEUTRAL_FILLERS or len((text or "").strip()) <= 2


def _extract_open_topic(text: str) -> str | None:
    """「我想聊X」→ X；抠不出返回 None。"""
    for prefix in OPEN_TOPIC_PREFIXES:
        if text.startswith(prefix):
            topic = text[len(prefix) :].strip().strip(" 。，,！？!?:：")
            return topic or None
        # 允许句中「来聊聊X」
        idx = text.find(prefix)
        if idx >= 0 and idx <= 4:
            topic = text[idx + len(prefix) :].strip().strip(" 。，,！？!?:：")
            return topic or None
    return None


def _is_satisfied(text: str) -> bool:
    return any(mark in text for mark in SATISFIED_MARKS)


def _is_disappointed(text: str) -> bool:
    return any(mark in text for mark in DISAPPOINT_MARKS)


def _empty_chase_signal(text: str, context: ThinContext) -> DriveSignal | None:
    """重复空追钝化（薄）：失望线索，或近两轮台上净是无内容接话。"""
    if _is_disappointed(text):
        return DriveSignal(
            direction="guard",
            salience="mid",
            why="重复空追，想要还在但满足没到；先停硬追、改接住对方的不满",
        )
    facts = list(context.facts_this_session or [])
    stage_lines = [f for f in facts if f.startswith("台上说：")]
    if len(stage_lines) >= 2:
        last_two = stage_lines[-2:]
        if all(any(m in line for m in _EMPTY_STAGE_MARKS) for line in last_two):
            # 用户还在同一话头上追
            topic = topic_hint_from_facts(facts)
            if topic and topic in text:
                return DriveSignal(
                    direction="hold",
                    salience="low",
                    why="重复空追，想要还在但满足没到；先停硬追、改接住",
                )
    return None


def _topic_continuation(text: str, context: ThinContext) -> DriveSignal | None:
    """本场已有话题词，本轮是对该话题的延续（非回指套话）。"""
    topic = topic_hint_from_facts(list(context.facts_this_session or []))
    if not topic or len(topic) < 2:
        return None
    if is_session_backref(text, context):
        return None
    if topic in text:
        return DriveSignal(
            direction="pursue",
            salience="mid",
            why=f"顺着本场已打开的想要继续（{topic}），不装没话头",
        )
    return None


def infer_drive(
    user_text: str,
    context: ThinContext,
    cues: DriveCues | None = None,
) -> DriveSignal:
    """DRIVE_V1 优先级：结构化阶段先行；无结构信号时才走 MARKS 兜底。

    S3 好奇挂起主路径读 ThinContext.curiosity_hang_pending 结构化布尔
    （pipeline 写 store flag）；「待接的话头：」前缀仅兜底兼容旧快照。
    """
    text = (user_text or "").strip()
    if cues is None:
        cues = drive_cues_from_context(context)

    # -- 结构化阶段：先读 cues，不动词表 --------------------------------
    # S1) 新场未接上 → 不推
    if not cues.session_ok:
        return DriveSignal(direction=None, salience="low", why="新场未接上，先不推")

    # S2) 承诺在场 + 本轮改口否定 → guard（复用 stance 线索，懒导入避免环）
    if cues.commitments_present and context.last_commitments:
        from .stance_org import _denies_commitment
        if _denies_commitment(text):
            first = context.last_commitments[0]
            return DriveSignal(
                direction="guard",
                salience="mid",
                why=f"同场有没兑现的话（{first}），已有要护，这轮不能当没说过",
            )

    # S3) 好奇挂起（读 ThinContext flag，「待接的话头：」前缀仅兜底）+ filler → 适时捡起悬问
    if cues.curiosity_hang_pending and context.open_questions:
        if is_neutral_filler(text):
            first = context.open_questions[0]
            return DriveSignal(
                direction="pursue",
                salience="mid",
                why=f"同场还有悬而未决的问题（{first}），可以适时捡起来",
            )

    # 兜底：无结构信号判定时才扫输入侧 MARKS（CURIOSITY/SATISFIED/DISAPPOINT/_EMPTY_STAGE）
    # 1) 招呼
    if _is_greeting(text):
        return DriveSignal(
            direction="hold",
            salience="low",
            why="招呼类开场，没有要推进的事；稳住场子即可，想聊什么听用户的",
        )

    # 2) 满足／收束
    if _is_satisfied(text):
        return DriveSignal(
            direction="hold",
            salience="low",
            why="喜欢/满足侧已接住，不必再追；对方示意够了或先收束",
        )

    # 3) 明确打开话题
    opened = _extract_open_topic(text)
    if opened:
        return DriveSignal(
            direction="pursue",
            salience="mid",
            why=f"缺口在外、想要打开这一话头（{opened}）",
        )

    # 4) 好奇
    if any(mark in text for mark in CURIOSITY_MARKS):
        return DriveSignal(
            direction="pursue",
            salience="high",
            why="用户问出了『为什么』类问题，好奇本身就是够格的推力，顺着看清楚",
        )

    # 5) 回指（与未兑现承诺冲突时：已有要护优先于普通回指追）
    if is_session_backref(text, context):
        if context.last_commitments:
            # 懒导入：stance_org 已依赖 drive.is_neutral_filler，避免环
            from .stance_org import _denies_commitment
            if _denies_commitment(text):
                first = context.last_commitments[0]
                return DriveSignal(
                    direction="guard",
                    salience="mid",
                    why=f"同场有没兑现的话（{first}），已有要护，这轮不能当没说过",
                )
        return DriveSignal(
            direction="pursue",
            salience="mid",
            why="用户在回指同场刚才的话头，动力要用本场已有痕迹接，不装没发生过",
        )

    # 6) 同场承诺：已有要护 → guard（hold 留给满足收束／空追该停）
    if context.last_commitments:
        first = context.last_commitments[0]
        return DriveSignal(
            direction="guard",
            salience="mid",
            why=f"同场有没兑现的话（{first}），已有要护，这轮不能当没说过",
        )

    # 7) 悬问 + filler：可 pursue；纯 filler 留空
    if is_neutral_filler(text):
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
            why="这一句没有推力，也不必硬造一个；如实回应即可",
        )

    # 8) 空追钝化
    dull = _empty_chase_signal(text, context)
    if dull is not None:
        return dull

    # 非 filler 的悬问：仍可作轻量 pursue（不强制）
    if context.open_questions:
        first = context.open_questions[0]
        return DriveSignal(
            direction="pursue",
            salience="mid",
            why=f"同场还有悬而未决的问题（{first}），可以适时捡起来",
        )

    # 9) 话题延续 / 默认陈述
    cont = _topic_continuation(text, context)
    if cont is not None:
        return cont

    return DriveSignal(
        direction=None,
        salience="low",
        why="陈述类的话，没有明显推力方向；如实接住，不硬造动力",
    )

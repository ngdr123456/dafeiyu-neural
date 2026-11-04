"""动力层：user_text + ThinContext -> DriveSignal（DRIVE_V1）。

对齐《贪婪的多巴胺》：想要 ≠ 喜欢／满足；预期落空会改推力。
槽位只有 direction / salience / why；禁止装饰分数当性格；不上台播报追守停。
线索只在输入侧，不是禁词闸门。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .context import ThinContextStore  # noqa: F401  (类型提示用)
from .session_trace import (
    is_prior_session_backref,
    is_session_backref,
    topic_hint_from_facts,
)
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


def is_identity_ask(text: str) -> bool:
    """A deliberately small set of direct questions about the user's identity."""
    text = re.sub(r"\s+", "", text or "")
    return any(shape in text for shape in (
        "知道我是谁", "认识我吗", "认识我么", "记得我是谁",
        "记得我吗", "认得我吗", "知道我叫什么",
    ))


def identity_self_introduction(text: str) -> str:
    """Accept a complete explicit self-introduction from this turn."""
    text = (text or "").strip()
    if any(mark in text for mark in ("?", "？")):
        return ""
    if re.fullmatch(r"(?:我叫|我的名字是|我名叫|我是)[^，。！？；\n]{1,40}[。！]?", text):
        return text.rstrip("。！")
    return ""


def identity_clue(context: ThinContext) -> str:
    """Return a sourced, explicit self-description, never an assistant turn or a question."""
    prior = context.prior_session
    facts = list(context.facts_this_session or []) + list(prior.facts if prior else [])
    for fact in facts:
        fact = fact.strip()
        if fact.startswith("台上说："):
            continue
        if fact.startswith("用户说："):
            fact = fact[len("用户说："):].strip()
        if not fact or any(mark in fact for mark in ("?", "？")):
            continue
        if re.match(r"^(?:我叫|我的名字是|我名叫|我是)[^，。！？；\n]{1,40}[。！]?$", fact):
            return fact.rstrip("。！")
    return ""


@dataclass
class DriveCues:
    """结构化线索：主路径先读上下文结构，不再先扫输入侧词表。"""

    commitments_present: bool = False
    drive_identity_ask_pending: bool = False
    drive_identity_answer_pending: bool = False
    # 改口否定挂起：主路径读 ThinContext.commitment_deny_pending 结构化布尔
    commitment_deny_pending: bool = False
    open_question_pending: bool = False
    # 同场好奇挂起仍 pending：主路径读 ThinContext.curiosity_hang_pending 结构化布尔
    curiosity_hang_pending: bool = False
    # 招呼 hold：主路径读 ThinContext.drive_greet_pending；GREETINGS 仅无结构时兜底
    drive_greet_pending: bool = False
    # 满足／收束 hold：主路径读 ThinContext.drive_hold_pending；SATISFIED_MARKS 仅无结构时兜底
    drive_hold_pending: bool = False
    # 结构化：本轮好奇 pursue（pipeline／上游写；drive 非 S3 主路径读；勿主靠 CURIOSITY_MARKS）
    drive_curiosity_pending: bool = False
    # 结构化：本轮打开话题 pursue（pipeline／上游写；drive 非 S3 主路径读；勿主靠 OPEN_TOPIC_PREFIXES）
    drive_open_topic_pending: bool = False
    # 结构化：本轮失望／空追 guard（pipeline／上游写；drive 非 S3 主路径读；勿主靠 DISAPPOINT_MARKS）
    drive_disappoint_pending: bool = False
    # 结构化：本轮空追钝化 hold（pipeline／上游写；drive 非 S3 主路径读；勿主靠 _EMPTY_STAGE_MARKS）
    drive_empty_stage_pending: bool = False
    # 结构化：本轮话题延续 pursue（pipeline／上游写；drive 非 S3 主路径读；勿主靠话题词扫 facts）
    drive_topic_continue_pending: bool = False
    # 结构化：本轮回指 pursue（pipeline／上游写；drive／stub 主路径读；勿主靠 BACKREF_MARKS／why 文案）
    drive_callback_pending: bool = False
    # 结构化：上场未兑现承诺线索（不强制开口；§6 仍只看同场 last_commitments）
    drive_prior_commit_pending: bool = False
    # 结构化：跨场回指 pursue（须有 prior_session 结构）
    drive_prior_callback_pending: bool = False
    # 结构化：催兑现上场未了承诺 → pursue（须有 prior.commitments_pending；后于 §6）
    drive_prior_press_pending: bool = False
    session_ok: bool = True


def drive_cues_from_context(context: ThinContext) -> DriveCues:
    """从 ThinContext 抽结构化线索（不扫用户输入侧词表）。

    改口否定（S2）主路径读 ThinContext.commitment_deny_pending 布尔；
    好奇挂起主路径读 ThinContext.curiosity_hang_pending 布尔；
    招呼／收束 hold（非 S3）主路径读 drive_greet_pending／drive_hold_pending。
    结构化：好奇 pursue / 打开话题 pursue / 失望 guard / 空台 hold / 话题延续 pursue / 回指 pursue 主路径读 flag；
    兜底范围见各段注释：仅当结构化 flag 缺省/False 时才扫输入侧线索
    （兼容旧快照／未写 flag 的路径）；不是禁词闸门，不扩词表，不改台上话术。
    """
    flag = bool(getattr(context, "curiosity_hang_pending", False))
    prefix_fallback = any(
        q.startswith("待接的话头：") for q in (context.open_questions or [])
    )
    return DriveCues(
        commitments_present=bool(context.last_commitments),
        drive_identity_ask_pending=bool(getattr(context, "drive_identity_ask_pending", False)),
        drive_identity_answer_pending=bool(getattr(context, "drive_identity_answer_pending", False)),
        commitment_deny_pending=bool(
            getattr(context, "commitment_deny_pending", False)
        ),
        open_question_pending=bool(context.open_questions),
        curiosity_hang_pending=flag or prefix_fallback,
        drive_greet_pending=bool(getattr(context, "drive_greet_pending", False)),
        drive_hold_pending=bool(getattr(context, "drive_hold_pending", False)),
        drive_curiosity_pending=bool(
            getattr(context, "drive_curiosity_pending", False)
        ),
        drive_open_topic_pending=bool(
            getattr(context, "drive_open_topic_pending", False)
        ),
        drive_disappoint_pending=bool(
            getattr(context, "drive_disappoint_pending", False)
        ),
        drive_empty_stage_pending=bool(
            getattr(context, "drive_empty_stage_pending", False)
        ),
        drive_topic_continue_pending=bool(
            getattr(context, "drive_topic_continue_pending", False)
        ),
        drive_callback_pending=bool(
            getattr(context, "drive_callback_pending", False)
        ),
        drive_prior_commit_pending=bool(
            getattr(context, "drive_prior_commit_pending", False)
        ),
        drive_prior_callback_pending=bool(
            getattr(context, "drive_prior_callback_pending", False)
        ),
        drive_prior_press_pending=bool(
            getattr(context, "drive_prior_press_pending", False)
        ),
        session_ok=context.session_ok,
    )


def should_set_drive_greet_pending(
    *,
    greet_cue: bool = False,
    user_text: str = "",
    marks_fallback: bool = True,
) -> bool:
    """主路径读上游结构化 greet_cue；仅无结构且允许兜底时才扫 GREETINGS。

    兜底范围：greet_cue 缺省/False 且 marks_fallback 时，才用既有 _is_greeting
    （兼容未写 flag 的直调／旧路径）。不是禁词闸门，不扩词表，不改台上话术。
    """
    if bool(greet_cue):
        return True
    if not marks_fallback:
        return False
    return _is_greeting((user_text or "").strip())


def should_set_drive_hold_pending(
    *,
    hold_cue: bool = False,
    user_text: str = "",
    marks_fallback: bool = True,
) -> bool:
    """主路径读上游结构化 hold_cue；仅无结构且允许兜底时才扫 SATISFIED_MARKS。

    兜底范围：hold_cue 缺省/False 且 marks_fallback 时，才用既有 _is_satisfied
    （兼容未写 flag 的直调／旧路径）。不是禁词闸门，不扩词表，不改台上话术。
    """
    if bool(hold_cue):
        return True
    if not marks_fallback:
        return False
    return _is_satisfied((user_text or "").strip())


def should_set_drive_curiosity_pending(
    *,
    curiosity_cue: bool = False,
    user_text: str = "",
    marks_fallback: bool = True,
) -> bool:
    """主路径读上游结构化 curiosity_cue；仅无结构且允许兜底时才扫 CURIOSITY_MARKS。

    兜底范围：curiosity_cue 缺省/False 且 marks_fallback 时，才用既有 CURIOSITY_MARKS
    （兼容未写 flag 的直调／旧路径）。不是禁词闸门，不扩词表，不改台上话术。
    与 curiosity_hang_pending（S3 同场挂起）不同：本 flag 仅本轮好奇 pursue。
    """
    if bool(curiosity_cue):
        return True
    if not marks_fallback:
        return False
    text = (user_text or "").strip()
    return any(mark in text for mark in CURIOSITY_MARKS)


def should_set_drive_open_topic_pending(
    *,
    open_topic_cue: bool = False,
    user_text: str = "",
    marks_fallback: bool = True,
) -> bool:
    """主路径读上游结构化 open_topic_cue；仅无结构且允许兜底时才扫 OPEN_TOPIC_PREFIXES。

    兜底范围：open_topic_cue 缺省/False 且 marks_fallback 时，才用既有 _extract_open_topic
    （兼容未写 flag 的直调／旧路径）。不是禁词闸门，不扩词表，不改台上话术。
    """
    if bool(open_topic_cue):
        return True
    if not marks_fallback:
        return False
    return _extract_open_topic((user_text or "").strip()) is not None


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




def should_set_drive_disappoint_pending(
    *,
    disappoint_cue: bool = False,
    user_text: str = "",
    marks_fallback: bool = True,
) -> bool:
    """主路径读上游结构化 disappoint_cue；仅无结构且允许兜底时才扫 DISAPPOINT_MARKS。

    兜底范围：disappoint_cue 缺省/False 且 marks_fallback 时，才用既有 _is_disappointed
    （兼容未写 flag 的直调／旧路径）。不是禁词闸门，不扩词表，不改台上话术。
    """
    if bool(disappoint_cue):
        return True
    if not marks_fallback:
        return False
    return _is_disappointed((user_text or "").strip())


def should_set_drive_empty_stage_pending(
    *,
    empty_stage_cue: bool = False,
    user_text: str = "",
    context: ThinContext | None = None,
    marks_fallback: bool = True,
) -> bool:
    """主路径读上游结构化 empty_stage_cue；仅无结构且允许兜底时才走既有空台接话判定。

    兜底范围：empty_stage_cue 缺省/False 且 marks_fallback 时，才用既有
    「近两轮台上净是无内容接话 + 话题仍在」那一支（direction=hold），不含 DISAPPOINT。
    不是禁词闸门，不扩词表，不改台上话术。
    """
    if bool(empty_stage_cue):
        return True
    if not marks_fallback:
        return False
    if context is None:
        return False
    text = (user_text or "").strip()
    facts = list(context.facts_this_session or [])
    stage_lines = [f for f in facts if f.startswith("台上说：")]
    if len(stage_lines) >= 2:
        last_two = stage_lines[-2:]
        if all(any(m in line for m in _EMPTY_STAGE_MARKS) for line in last_two):
            topic = topic_hint_from_facts(facts)
            if topic and topic in text:
                return True
    return False


def should_set_drive_topic_continue_pending(
    *,
    topic_continue_cue: bool = False,
    user_text: str = "",
    context: ThinContext | None = None,
    marks_fallback: bool = True,
) -> bool:
    """主路径读上游结构化 topic_continue_cue；仅无结构且允许兜底时才走既有 _topic_continuation。

    兜底范围：topic_continue_cue 缺省/False 且 marks_fallback 时，才用既有
    _topic_continuation 是否非 None（兼容未写 flag 的直调／旧路径）。
    不是禁词闸门，不扩词表，不改台上话术。
    """
    if bool(topic_continue_cue):
        return True
    if not marks_fallback:
        return False
    if context is None:
        return False
    return _topic_continuation((user_text or "").strip(), context) is not None


def should_set_drive_callback_pending(
    *,
    callback_cue: bool = False,
    user_text: str = "",
    context: ThinContext | None = None,
    marks_fallback: bool = True,
) -> bool:
    """主路径读上游结构化 callback_cue；仅无结构且允许兜底时才走既有 is_session_backref。

    兜底范围：callback_cue 缺省/False 且 marks_fallback 时，才用既有
    is_session_backref（BACKREF_MARKS + facts 非空；兼容未写 flag 的直调／旧路径）。
    不是禁词闸门，不扩词表，不改台上话术。
    """
    if bool(callback_cue):
        return True
    if not marks_fallback:
        return False
    if context is None:
        return False
    return is_session_backref((user_text or "").strip(), context)


def should_set_drive_prior_callback_pending(
    *,
    prior_callback_cue: bool = False,
    user_text: str = "",
    context: ThinContext | None = None,
    marks_fallback: bool = True,
) -> bool:
    """主路径读上游结构化 prior_callback_cue；仅无结构且允许兜底时才走 is_prior_session_backref。

    放行／pursue 仍要求 context.prior_session 有痕迹；无痕迹时「上次」不置 flag。
    不是禁词闸门，不扩用户对话禁词表，不改台上话术。
    """
    if bool(prior_callback_cue):
        return True
    if not marks_fallback:
        return False
    if context is None:
        return False
    return is_prior_session_backref((user_text or "").strip(), context)



def should_set_drive_prior_press_pending(
    *,
    prior_press_cue: bool = False,
    user_text: str = "",
    context: ThinContext | None = None,
    marks_fallback: bool = True,
) -> bool:
    """主路径读上游结构化 prior_press_cue；仅无结构且允许兜底时才走 user_presses_prior_pending。

    放行／pursue 仍要求 prior_session.commitments_pending 非空；无 pending 时不置 flag。
    不是禁词闸门，不扩用户对话禁词表，不改台上话术；§6 同场 last_commitments 仍优先。
    """
    if bool(prior_press_cue):
        return True
    if not marks_fallback:
        return False
    if context is None:
        return False
    prior = getattr(context, "prior_session", None)
    if prior is None or not getattr(prior, "commitments_pending", None):
        return False
    from .commit_extract import user_presses_prior_pending
    return user_presses_prior_pending((user_text or "").strip(), prior)


_BYPASS_ENV_TRUTHY = frozenset({"1", "true", "yes", "on"})


def is_drive_bypass_on(
    *,
    explicit: bool | None = None,
    context: ThinContext | None = None,
) -> bool:
    """工程师通道：是否强制动力中性 hold。默认关；非出生默认。

    开启途径（任一即可）：
    - explicit=True（infer_drive／turn 的 drive_bypass kwarg）
    - ThinContext.drive_bypass=True
    - 环境变量 BIRTH_DRIVE_BYPASS 或 BIRTH_DRIVE_NEUTRAL ∈ {1,true,yes,on}
    """
    if explicit is True:
        return True
    if context is not None and bool(getattr(context, "drive_bypass", False)):
        return True
    for key in ("BIRTH_DRIVE_BYPASS", "BIRTH_DRIVE_NEUTRAL"):
        if os.environ.get(key, "").strip().lower() in _BYPASS_ENV_TRUTHY:
            return True
    return False


def infer_drive(
    user_text: str,
    context: ThinContext,
    cues: DriveCues | None = None,
    *,
    drive_bypass: bool | None = None,
) -> DriveSignal:
    """DRIVE_V1 优先级：结构化阶段先行；无结构信号时才走 MARKS 兜底。

    工程师旁路（drive_bypass／ThinContext.drive_bypass／BIRTH_DRIVE_BYPASS｜NEUTRAL）：
    开则固定 hold/low、why「工程师旁路」，跳过全部 S*；默认关，零行为变化。

    S2 改口否定主路径读 ThinContext.commitment_deny_pending 结构化布尔
    （pipeline 经 store 在 turn 开头置位）；兜底范围见 S2 注释。
    S3 好奇挂起主路径读 ThinContext.curiosity_hang_pending 结构化布尔
    （pipeline 写 store flag＋挂 openq clip，不强制前缀）；「待接的话头：」前缀仅兜底兼容旧快照。
    S4／S5 招呼／收束 hold 主路径读 drive_greet_pending／drive_hold_pending；
    GREETINGS／SATISFIED_MARKS 仅无结构时兜底（不扩词表）。
    S6／S7 打开话题／好奇 pursue 主路径读 drive_open_topic_pending／drive_curiosity_pending；
    OPEN_TOPIC_PREFIXES／CURIOSITY_MARKS 仅无结构时兜底（不扩词表）。
    §6 同场承诺在场 → guard 须先于 S8／S9／S10（空追／话题延续不得压过已有要护）。
    S8／S9／S10 失望 guard／空台 hold／话题延续 pursue 主路径读
    drive_disappoint_pending／drive_empty_stage_pending／drive_topic_continue_pending；
    DISAPPOINT_MARKS／_EMPTY_STAGE_MARKS／话题词扫 facts 仅无结构时兜底（不扩词表）。
    S11 回指 pursue 主路径读 drive_callback_pending；须后于 §6（有承诺时不得压过 guard）；
    is_session_backref／BACKREF_MARKS 仅无结构时兜底（不扩词表）。
    S12a 上场承诺被催 pursue（drive_prior_press_pending；须后于 §6；不并进 last_commitments）。
    S14 开口拒收回流 soft hold：articulate_reject_count≥2 且 filler、无 commitment_deny、
    无催答应 → hold/low；why「开口拒收回流｜同场多次」；不扩词表、不改台上话术。
    """
    text = (user_text or "").strip()
    if cues is None:
        cues = drive_cues_from_context(context)

    # 工程师旁路：拔掉动力接线，固定中性 hold（管线仍跑；非听感验收）
    if is_drive_bypass_on(explicit=drive_bypass, context=context):
        return DriveSignal(
            direction="hold",
            salience="low",
            why="工程师旁路",
        )

    # -- 结构化阶段：先读 cues，不动词表 --------------------------------
    # S1) 新场未接上 → 不推
    if not cues.session_ok:
        return DriveSignal(direction=None, salience="low", why="新场未接上，先不推")

    # Identity questions do not enter the neutral-filler path. §6 still wins
    # when a same-session commitment is present.
    if cues.drive_identity_ask_pending and not cues.commitments_present:
        if identity_clue(context):
            return DriveSignal(direction="pursue", salience="mid", why="身份询问｜已有对方线索，接着确认")
        return DriveSignal(direction="hold", salience="low", why="身份询问｜没有可识别的对方线索，先听对方介绍")

    if cues.drive_identity_answer_pending:
        if cues.commitments_present:
            return DriveSignal(direction="guard", salience="mid", why="同场有没兑现的话，先守住承诺")
        return DriveSignal(direction="pursue", salience="mid", why="身份回应｜接住对方的自我介绍")

    # S2) 承诺在场 + 本轮改口否定 → guard
    # 主路径：读 cues.commitment_deny_pending（ThinContext 结构化布尔，pipeline／上游置位）。
    # 兜底范围：仅当结构化 flag 缺省/False 时，才扫 _denies_commitment 词表
    # （兼容未写 flag 的直调／旧路径）；不是禁词闸门，不扩词表，不改台上话术。
    if cues.commitments_present and context.last_commitments:
        denied = bool(cues.commitment_deny_pending)
        if not denied:
            from .stance_org import _denies_commitment
            denied = _denies_commitment(text)
        if denied:
            first = context.last_commitments[0]
            return DriveSignal(
                direction="guard",
                salience="mid",
                why=f"同场有没兑现的话（{first}），已有要护，这轮不能当没说过",
            )

    # Relational receipt/wait is separate from topic questions and never beats §6.
    if context.want_seen_pending or context.drive_want_seen_satisfied_pending:
        if cues.commitments_present:
            return DriveSignal(direction="guard", salience="mid", why="同场有没兑现的话，先守住承诺")
        if context.drive_want_seen_satisfied_pending:
            return DriveSignal(direction="hold", salience="low", why="被看见了｜接住这份回应，先停在这里")
        if context.drive_want_seen_waiting or is_neutral_filler(text):
            return DriveSignal(direction="pursue", salience="mid", why="想被看见｜还在等对方回应")

    if context.drive_openq_satisfied_pending:
        if cues.commitments_present:
            return DriveSignal(direction="guard", salience="mid", why="同场有没兑现的话，先守住承诺")
        return DriveSignal(direction="hold", salience="low", why="悬问被接住|喜欢/满足侧到了，不必再追")

    # S3) 好奇挂起（读 ThinContext flag，「待接的话头：」前缀仅兜底）+ filler → 适时捡起悬问
    if cues.curiosity_hang_pending and context.open_questions:
        if is_neutral_filler(text):
            first = context.open_questions[0]
            return DriveSignal(
                direction="pursue",
                salience="mid",
                why=f"同场还有悬而未决的问题（{first}），可以适时捡起来",
            )

    # S4) 结构化招呼 → hold（主路径读 flag；GREETINGS 仅无结构时兜底）
    if cues.drive_greet_pending:
        return DriveSignal(
            direction="hold",
            salience="low",
            why="招呼类开场，没有要推进的事；稳住场子即可，想聊什么听用户的",
        )

    # S5) 结构化满足／收束 → hold（主路径读 flag；SATISFIED_MARKS 仅无结构时兜底）
    if cues.drive_hold_pending:
        return DriveSignal(
            direction="hold",
            salience="low",
            why="喜欢/满足侧已接住，不必再追；对方示意够了或先收束",
        )

    # S6) 结构化打开话题 → pursue mid（主路径读 flag；OPEN_TOPIC_PREFIXES 仅无结构时兜底）
    if cues.drive_open_topic_pending:
        opened = _extract_open_topic(text)  # why 富化，不决定分支
        topic_bit = f"（{opened}）" if opened else ""
        return DriveSignal(
            direction="pursue",
            salience="mid",
            why=f"缺口在外、想要打开这一话头{topic_bit}",
        )

    # S7) 结构化好奇 → pursue high（主路径读 flag；CURIOSITY_MARKS 仅无结构时兜底）
    if cues.drive_curiosity_pending:
        return DriveSignal(
            direction="pursue",
            salience="high",
            why="用户问出了『为什么』类问题，好奇本身就是够格的推力，顺着看清楚",
        )

    # §6) 同场承诺在场 → guard（DRIVE_V1：须先于 §8 空追／§9 话题延续／§11 回指；
    # S8–S11 不得压过已有要护。写入侧亦不应在有 last_commitments 时置空台／话题／回指 flag。）
    if cues.commitments_present and context.last_commitments:
        first = context.last_commitments[0]
        return DriveSignal(
            direction="guard",
            salience="mid",
            why=f"同场有没兑现的话（{first}），已有要护，这轮不能当没说过",
        )

    # S8) 结构化失望／空追 → guard mid（主路径读 flag；DISAPPOINT_MARKS 仅无结构时兜底）
    if cues.drive_disappoint_pending:
        return DriveSignal(
            direction="guard",
            salience="mid",
            why="重复空追，想要还在但满足没到；先停硬追、改接住对方的不满",
        )

    # S9) 结构化空台接话钝化 → hold low（主路径读 flag；_EMPTY_STAGE_MARKS 仅无结构时兜底）
    if cues.drive_empty_stage_pending:
        return DriveSignal(
            direction="hold",
            salience="low",
            why="重复空追，想要还在但满足没到；先停硬追、改接住",
        )

    # S10) 结构化话题延续 → pursue mid（主路径读 flag；话题词扫 facts 仅无结构时兜底）
    if cues.drive_topic_continue_pending:
        topic = topic_hint_from_facts(list(context.facts_this_session or []))
        if topic:
            why = f"顺着本场已打开的想要继续（{topic}），不装没话头"
        else:
            why = "顺着本场已打开的想要继续，不装没话头"
        return DriveSignal(
            direction="pursue",
            salience="mid",
            why=why,
        )

    # S11) 结构化回指 → pursue mid（主路径读 flag；须后于 §6；BACKREF_MARKS 仅无结构时兜底）
    if cues.drive_callback_pending:
        return DriveSignal(
            direction="pursue",
            salience="mid",
            why="用户在回指同场刚才的话头，动力要用本场已有痕迹接，不装没发生过",
        )

    # S12a) 上场未兑现承诺被催 → pursue mid（须有 prior.commitments_pending；须后于 §6；
    # 不把 prior pending 并进 last_commitments；why 指纹标明上场承诺）
    if cues.drive_prior_press_pending:
        prior = getattr(context, "prior_session", None)
        first = ""
        if prior is not None and prior.commitments_pending:
            first = prior.commitments_pending[0]
        why = (
            f"上场承诺｜用户催兑现（{first}）"
            if first
            else "上场承诺｜用户催兑现"
        )
        return DriveSignal(
            direction="pursue",
            salience="mid",
            why=why,
        )

    # S12) 跨场回指 → pursue mid（须有 prior_session 结构；须后于 §6；不强制开口提上场承诺）
    if cues.drive_prior_callback_pending:
        return DriveSignal(
            direction="pursue",
            salience="mid",
            why="用户在回指上一场的话头，动力要用上场已有痕迹接，不装没发生过",
        )

    # S13) 上场未兑现承诺线索：不强制开口；仅 filler／无内容时留低显著 hold，
    # 不压后续好奇／开话题等兜底（§6 同场承诺仍优先；drive_bypass 已在入口短路）
    if cues.drive_prior_commit_pending and is_neutral_filler(text):
        return DriveSignal(
            direction="hold",
            salience="low",
            why="上场还有未兑现的话，可作线索，不强制这轮开口提",
        )

    # S14) 开口拒收回流 soft hold（可选读）：同场 reject_count≥2 且无改口否定、
    # 无催答应 → filler 时 hold/low；why 用结构指纹，不逼台上自述「我被闸了」。
    # §6／drive_bypass 已在前；不压后续好奇／开话题 MARKS 兜底。
    reject_n = int(getattr(context, "articulate_reject_count", 0) or 0)
    if (
        reject_n >= 2
        and is_neutral_filler(text)
        and not bool(getattr(context, "commitment_deny_pending", False))
    ):
        from .commit_extract import user_presses_commitment
        if not user_presses_commitment(text):
            return DriveSignal(
                direction="hold",
                salience="low",
                why="开口拒收回流｜同场多次",
            )

    # 兜底：无结构信号判定时才扫输入侧 MARKS（GREETINGS/SATISFIED/CURIOSITY/DISAPPOINT/_EMPTY_STAGE）
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

    # 5) 回指兜底（无 drive_callback_pending 时）：与未兑现承诺冲突时已有要护优先于普通回指追
    if is_session_backref(text, context):
        if context.last_commitments:
            # 主路径读 ThinContext.commitment_deny_pending；仅无 flag 时才扫
            # _denies_commitment 词表兜底（懒导入：stance_org 已依赖 drive.is_neutral_filler，避免环）
            denied = bool(cues.commitment_deny_pending)
            if not denied:
                from .stance_org import _denies_commitment
                denied = _denies_commitment(text)
            if denied:
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

    # 5a) 上场承诺被催兜底（无 drive_prior_press_pending 时）
    from .commit_extract import user_presses_prior_pending
    prior = getattr(context, "prior_session", None)
    if prior is not None and prior.commitments_pending and user_presses_prior_pending(text, prior):
        first = prior.commitments_pending[0]
        return DriveSignal(
            direction="pursue",
            salience="mid",
            why=f"上场承诺｜用户催兑现（{first}）",
        )

    # 5b) 跨场回指兜底（无 drive_prior_callback_pending 时）
    if is_prior_session_backref(text, context):
        return DriveSignal(
            direction="pursue",
            salience="mid",
            why="用户在回指上一场的话头，动力要用上场已有痕迹接，不装没发生过",
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

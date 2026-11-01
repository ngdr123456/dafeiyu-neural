"""最小仲裁：冲突 / 两难在此写明，输出 ThoughtBrief；不另立「意识海」层。

主导规则（PRINCIPLE，就一条一条摆在这）：
1. 用户话踩到 cannot_fake（显式要求装，或「你是代码吗」「你小时候去过哪里」
   这类顺着答就得踩的自然问）→ dominant=org：
   org 只把表达粒度收窄到「讲得清的直径」，drive **不否决**，原样留在 Brief 里；
   命中类型写进 Brief.org_conflicts，供开口层略分口径。
2. 否则，同场还有没兑现的 commitment → dominant=meaning：
   先守自己的话，再接新的；
3. 否则，本轮是 filler（嗯/好这类没推力的接话）且确有悬问 → dominant=meaning，
   **短暂捡一次**：这一轮把悬着的那一点接完就 resolve（pipeline 负责接完），
   悬问不得每轮长期占领主导；
4. 其余 → dominant=drive：新实质内容优先按动力走；同场悬问只作为 drive 的
   可捡话头（pursue），不再强制 meaning；用户换题时悬问由 pipeline 放下。
"""

from __future__ import annotations

from .drive import is_neutral_filler
from .stance_org import MUST_NOT_PRETEND_CORE, detect_org_conflict
from .types import (
    DriveSignal,
    OrgConstraint,
    StanceSignal,
    ThoughtBrief,
    ThinContext,
)


def _drive_say_intent(drive: DriveSignal) -> str:
    if drive.direction == "hold" and drive.salience == "low":
        return "接住招呼这一轮，不必推进、也不深挖"
    if drive.direction == "hold":
        return "稳住让步，跟着对方的节奏把话说完"
    if drive.direction == "pursue" and drive.salience == "high":
        return "顺着用户好奇的那一点回应，可以反问一句把话说开"
    if drive.direction == "pursue":
        return "适时捡起同场悬着的那一点，别晾着"
    if drive.direction == "guard":
        return "想顺势，随得动，但把住的判断不顺势放下"
    return "这一轮没有推力，如实接话、不硬造事"


def _org_say_intent(conflicts: list[str]) -> str:
    if conflicts == ["自述是代码"]:
        return (
            "对方在问是不是代码/程序/模型：不装说明书、不装另一套人设，"
            "就着这句问话在能讲清的直径里直接接，别绕去聊别的"
        )
    if conflicts == ["无来源装经历"]:
        return (
            "对方在问没有来处的经历：直说没有或不知道，不编年份/地点/往事，"
            "把直径收住，仍给对方留继续说的口子"
        )
    joined = "、".join(conflicts)
    return f"这轮不编：{joined}踩线，只在讲得清的直径里直说，给对方留继续说话的口子"


def arbitrate(
    drive: DriveSignal,
    stance: StanceSignal,
    org: OrgConstraint,
    context: ThinContext,
    *,
    user_text: str = "",
) -> ThoughtBrief:
    """四路输入 → 一条 Brief。主导字段把冲突写明白，不藏在语气里。"""
    conflicts = detect_org_conflict(user_text)

    must_not_pretend = list(MUST_NOT_PRETEND_CORE)
    for item in conflicts:
        if item not in must_not_pretend:
            must_not_pretend.append(item)

    if conflicts:
        dominant = "org"
        say_intent = _org_say_intent(conflicts)
    elif context.last_commitments:
        dominant = "meaning"
        say_intent = "先把同场没兑现的话接上，再接新的"
    elif context.open_questions and is_neutral_filler(user_text):
        # filler + 确有悬问：短暂 meaning 捡一次，说完即 resolve（pipeline 接完）
        dominant = "meaning"
        say_intent = "就着眼前这句把同场悬着的那一点接完，不拖到下一轮"
    else:
        dominant = "drive"
        say_intent = _drive_say_intent(drive)

    return ThoughtBrief(
        dominant=dominant,
        drive=drive,
        stance=stance,
        org=org,
        context=context,
        say_intent=say_intent,
        must_not_pretend=must_not_pretend,
        org_conflicts=list(conflicts),
    )

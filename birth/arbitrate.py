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

from .drive import _extract_open_topic, is_neutral_filler
from .commit_extract import (
    _pending_topic_tokens,
    topic_from_pending_commitment,
    user_marks_commitment_done,
    user_presses_commitment,
)
from .openq_extract import user_marks_open_question_putdown
from .session_trace import is_session_backref, recent_facts, topic_hint_from_facts
from .stance_org import MUST_NOT_PRETEND_CORE, detect_org_conflict, stance_holds_same_field
from .types import (
    DriveSignal,
    OrgConstraint,
    StanceSignal,
    ThoughtBrief,
    ThinContext,
)


def _drive_say_intent(drive: DriveSignal) -> str:
    why = drive.why or ""
    if "身体想象｜" in why:
        return "承认想象中想要感受的愿望，不把想象说成亲历"
    if "想被看见｜" in why:
        return "轻轻说还想听听对方怎么看，给对方留余地"
    if "被看见了｜" in why:
        return "接住对方的回应，稳住这一刻"
    if "悬问被接住|" in why:
        return "接住对方给出的回答，稳住这一轮，不再追问同一个悬问"
    # DRIVE_V1：按 why 形状分流（开口人话，不上台播报追守停）
    if "喜欢/满足" in why or "不必再追" in why:
        return "对方示意够了或先收束，稳住、不继续加码追"
    if "重复空追" in why:
        return "这一轮先停硬追，老实接住对方的不满或缺口，不装已经答完"
    if "想要打开" in why or "缺口在外" in why:
        # 把打开的话头短摘带进 say_intent，供 stub/LLM 点到
        topic = ""
        if "（" in why and "）" in why:
            topic = why.split("（", 1)[1].split("）", 1)[0].strip()
        if topic:
            return (
                f"接住对方新打开的话头「{topic}」，可以顺着问一句，不抢着下结论"
            )
        return "接住对方新打开的话头，可以顺着问一句，不抢着下结论"
    if "顺着本场已打开的想要继续" in why:
        return "顺着本场已打开的话头继续接，不装没话头，也不硬造新场"
    if drive.direction == "hold" and drive.salience == "low":
        return "接住招呼这一轮，不必推进、也不深挖"
    if drive.direction == "hold":
        return "稳住让步，跟着对方的节奏把话说完"
    if drive.direction == "pursue" and drive.salience == "high":
        return "顺着用户好奇的那一点回应，可以反问一句把话说开"
    if bool(getattr(drive, "prior_her_question", False)):
        return "上场你问出去的那句还没被接住，可以顺口问回来，别当成对方已经答过"
    if drive.direction == "pursue":
        return "适时捡起同场悬着的那一点，别晾着"
    if drive.direction == "guard":
        if "没兑现" in why or "已有要护" in why:
            return "先守住同场说过的话，把住的判断不顺势放下"
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

    openq_resolve = False
    # 对齐 drive 已判定的好奇 pursue/high；写标记供 pipeline，不在此再扫词表
    openq_curiosity_hang = (
        drive.direction == "pursue"
        and drive.salience == "high"
        and "好奇" in (drive.why or "")
    )
    openq_clear = False
    # 换题 clear：同场确有悬问 + 用户明示放下或真开新话头（复用既有线索，勿扩词表）；
    # arb 只写标记，pipeline 开口后 clear；闲聊／改口否定／身份问不置位
    if context.open_questions and (
        user_marks_open_question_putdown(user_text)
        or _extract_open_topic(user_text or "")
    ):
        openq_clear = True
    press_commit = False
    commit_resolve = False
    commit_deliverable = False
    commit_deliver_intent = False
    commit_hold_with_drive = False
    commit_deny = False
    hold_same_field = False
    if conflicts:
        dominant = "org"
        say_intent = _org_say_intent(conflicts)
    elif (
        stance.posture == "non_negotiable"
        and context.last_commitments
        and stance_holds_same_field(stance)
    ):
        # 意义：守住自己出口的承诺（可与 commitment 分支合并）
        # 主路径读 stance.hold_same_field（stake 中文常量仅字段取值／旧兜底，不作唯一闸）
        dominant = "meaning"
        say_intent = "先守住同场自己说过的话，不跟着改口否定；再接眼前这句"
        commit_deny = True
        hold_same_field = True
    elif stance.posture == "needs_clarify":
        dominant = "meaning"
        say_intent = "不空壳升华：先澄清这一轮能讲清的直径，没有根据就不装人生答案"
    elif context.last_commitments and user_marks_commitment_done(user_text):
        # 用户示意已兑现：结构化 commit_resolve（宁缺既有线索，勿扩词表）
        dominant = "meaning"
        commit_resolve = True
        say_intent = "对方示意同场那件约定已接上，可以放下再接眼前这句"
    elif context.last_commitments:
        dominant = "meaning"
        commit_deliverable = True
        pending0 = context.last_commitments[0]
        toks = _pending_topic_tokens(pending0)
        if toks and any(tok in (user_text or "") for tok in toks):
            commit_deliver_intent = True  # 用户点到主题＝可检验接着交付，非纯守诺
        why = drive.why or ""
        # 收束 hold／好奇 pursue：动力人话进 say_intent，薄守诺并存（勿只吐守诺模板）
        if drive.direction == "hold" and (
            "喜欢/满足" in why or "不必再追" in why
        ):
            commit_hold_with_drive = True
            say_intent = (
                f"{_drive_say_intent(drive)}；同场约定还在，不假装消失"
            )
        elif (
            drive.direction == "pursue"
            and drive.salience == "high"
            and "好奇" in why
        ):
            commit_hold_with_drive = True
            say_intent = (
                f"{_drive_say_intent(drive)}；同场约定还在，不假装消失"
            )
        else:
            # 纯闲聊／无强动力：维持守诺 meaning
            say_intent = "先守住同场说过的话，把住的判断不顺势放下；再接新的"
    elif ((context.stance_necessary_pain_pending or context.stance_self_torture_pending)
          and not context.drive_identity_ask_pending
          and not context.drive_identity_answer_pending):
        dominant = "meaning"
        if context.stance_self_torture_pending:
            say_intent = "不跟加戏，留意哪些苦可以少受，不替对方断定"
        else:
            say_intent = "承认必要的痛苦还在，不假装解决；可以陪对方面对"
    elif (context.stance_attitude_pending
          and not context.drive_identity_ask_pending
          and not context.drive_identity_answer_pending):
        dominant = "meaning"
        say_intent = "承认对方说的处境无法改变；不许诺改变它，选择在此陪对方一起面对，不替对方赋予意义"
    elif (context.open_questions and is_neutral_filler(user_text)
          and "想被看见｜" not in (drive.why or "")):
        # filler + 确有悬问：短暂接话，但不当作用户已经回答。
        dominant = "meaning"
        say_intent = "先接住这声回应，悬问仍留着，不把它当作已经回答"
    elif context.drive_openq_satisfied_pending and drive.direction == "hold":
        dominant = "drive"
        say_intent = _drive_say_intent(drive)
    elif bool(getattr(context, "drive_prior_press_pending", False)) or (
        "上场承诺｜" in ((drive.why or "") if drive else "")
    ):
        # 上场未兑现被催：复用 press_commit；承诺文案取自 prior.commitments_pending
        # （不拼进 say_intent 当唯一闸；不并进 last_commitments）
        dominant = "drive"
        press_commit = True
        prior = getattr(context, "prior_session", None)
        pending0 = ""
        if prior is not None and prior.commitments_pending:
            pending0 = prior.commitments_pending[0]
        topic = topic_from_pending_commitment(pending0) or pending0 or "这事"
        # 截短话题，避免整句承诺塞进「」
        if len(topic) > 12:
            topic = topic[:12]
        say_intent = (
            f"对方催兑现上场未了的约定「{topic}」，应一句可核对的，不空口"
        )
    elif user_presses_commitment(user_text):
        # 催答应：结构化 press_commit；人话 say_intent 可改口不失效
        dominant = "drive"
        press_commit = True
        topic = topic_hint_from_facts(list(context.facts_this_session or [])) or "这事"
        say_intent = (
            f"对方催一个可核对的约定，就着本场话头「{topic}」应一句可兑现的，不空口"
        )
    else:
        dominant = "drive"
        if (is_session_backref(user_text, context) and not context.drive_openq_satisfied_pending
                and "想被看见｜" not in (drive.why or "")
                and "被看见了｜" not in (drive.why or "")
                and not bool(getattr(drive, "prior_her_question", False))):
            digest = "；".join(recent_facts(context, 3))
            say_intent = (
                "接住对方对同场刚才话题的回指，用本场已有痕迹接话，"
                "不装没发生过、也不编场外经历。"
                f"本场痕迹：{digest}"
            )
        else:
            say_intent = _drive_say_intent(drive)

    # 粒度只读结构字段；保留先前分支的主导和具体约束，不靠人话子串判定。
    if org.grain == "differentiated" and not conflicts:
        if context.last_commitments:
            if not commit_hold_with_drive:
                say_intent = f"{_drive_say_intent(drive)}；{say_intent}"
            commit_hold_with_drive = True
        else:
            say_intent = (
                f"{_drive_say_intent(drive)}；"
                "守住这一轮不可让出的立场，不跟着改口否定"
            )

    return ThoughtBrief(
        dominant=dominant,
        drive=drive,
        stance=stance,
        org=org,
        context=context,
        say_intent=say_intent,
        must_not_pretend=must_not_pretend,
        openq_resolve=openq_resolve,
        openq_curiosity_hang=openq_curiosity_hang,
        openq_clear=openq_clear,
        press_commit=press_commit,
        commit_resolve=commit_resolve,
        commit_deliverable=commit_deliverable,
        commit_deliver_intent=commit_deliver_intent,
        commit_hold_with_drive=commit_hold_with_drive,
        commit_deny=commit_deny,
        hold_same_field=hold_same_field,
        org_conflicts=list(conflicts),
    )

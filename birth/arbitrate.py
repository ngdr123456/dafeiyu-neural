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
from .input_contract import InputSignal, credible_commitment_target, credible_open_question_answer, credible_topic
from .commit_extract import (
    _pending_topic_tokens,
    match_pending_commitment,
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
    SourcedInput,
    ThinContext,
    PriorSessionTrace,
)


def _input_stop_label(drive: DriveSignal | None) -> str | None:
    """读 drive.why 结构前缀，回到「暂停／终止」；不是扫用户原句。"""
    why = (drive.why if drive is not None else "") or ""
    if why.startswith("输入信号｜暂停｜"):
        return "暂停"
    if why.startswith("输入信号｜终止｜"):
        return "终止"
    return None


def _drive_say_intent(drive: DriveSignal) -> str:
    why = drive.why or ""
    # INPUT_INTENT_V1：判停之后台上先应一声就停住——问候、邀请继续、问「要我做什么」
    # 都会把「停」重新说回「接着聊」。
    if why.startswith("输入信号｜暂停｜"):
        return "对方在叫停：先应一声就暂停，不问候、不邀请继续、不问要我做什么、不开新话头"
    if why.startswith("输入信号｜终止｜"):
        return "对方在收束这场：先应一声就停在点子上，不问候、不邀请继续、不问要我做什么、不开新话头"
    if why.startswith("输入理解｜答复悬问｜"):
        return "接住对方给出的回答，这轮不再追问同一个悬问"
    if why.startswith("输入信号｜问句｜"):
        return "对方在问我，先正面接住这个问题；能答就答，答不上来就说清"
    if why.startswith("输入信号｜请求｜"):
        return "对方在请我做事，先接住这件事；能做就说怎么做，不能就直说"
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


def _clip_bounded(text: str, limit: int) -> str:
    return (text or "").strip()[:limit]


def _response_focus(
    user_text: str, context: ThinContext, understanding: InputSignal | None,
) -> tuple[str, str]:
    """只取内容短摘及其来源，不用焦点文案控制主导或销账。"""
    topic = credible_topic(understanding)
    if topic:
        return topic, "本轮理解"
    text = (user_text or "").strip()
    if text and not is_neutral_filler(text):
        return _clip_bounded(text, 60), "本轮原话"
    if context.open_questions:
        return _clip_bounded(context.open_questions[0], 60), "同场悬问"
    if context.last_commitments:
        pending = context.last_commitments[0]
        return _clip_bounded(topic_from_pending_commitment(pending) or pending, 60), "同场承诺"
    prior = context.prior_session
    if prior and prior.commitments_pending:
        pending = prior.commitments_pending[0]
        return _clip_bounded(topic_from_pending_commitment(pending) or pending, 60), "上场承诺"
    if text:
        return _clip_bounded(text, 60), "本轮原话"
    return "", "无实质内容"


def arbitrate(
    drive: DriveSignal,
    stance: StanceSignal,
    org: OrgConstraint,
    context: ThinContext,
    *,
    user_text: str = "",
    understanding: InputSignal | None = None,
) -> ThoughtBrief:
    """四路输入 → 一条 Brief。主导字段把冲突写明白，不藏在语气里。"""
    drive = drive if drive is not None else DriveSignal(why="动力层未给出信号")
    stance = stance if stance is not None else StanceSignal()
    org = org if org is not None else OrgConstraint()
    conflicts = list(getattr(org, "conflicts", None) or [])
    if not conflicts:
        conflicts = detect_org_conflict(user_text)
    focus, focus_source = _response_focus(user_text, context, understanding)
    dominant_why = ""

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
    pressed_commitment = ""
    commit_resolve = False
    commit_deliverable = False
    commit_deliver_intent = False
    commit_hold_with_drive = False
    commit_deny = False
    hold_same_field = False
    # 先认账，再选主导；意义／组织分支不能抹掉用户点名的债。
    prior = context.prior_session
    pending_all = list(dict.fromkeys(
        (prior.commitments_pending if prior else []) + context.last_commitments
    ))
    target = credible_commitment_target(understanding)
    recognized = target if target in pending_all else (match_pending_commitment(
        user_text, PriorSessionTrace(commitments_pending=pending_all)
    ) or "")
    q = credible_open_question_answer(understanding)
    openq_target = q if q in context.open_questions else ""
    prior_target = q if not openq_target and prior and q in prior.her_questions else ""
    recognized_prior = recognized if prior and recognized in prior.commitments_pending else ""
    recognized_same = recognized if recognized in context.last_commitments else ""
    done_same = recognized_same or (
        context.last_commitments[0] if len(pending_all) == 1 and context.last_commitments else ""
    )
    commit_resolve = bool(done_same and user_marks_commitment_done(user_text))
    if conflicts:
        dominant = "org"
        say_intent = _org_say_intent(conflicts)
        if focus:
            say_intent += f"；这一轮要接的原话是「{focus}」，回答要落在这句上"
        dominant_why = (
            f"组织主导｜诚实硬闸优先：本轮命中「{'、'.join(conflicts)}」，"
            "宁可收窄能说清的直径也不编造；动力仍在 Brief，不被否决"
            "（来源：可施工规格 第5层／硬闸3；外补：不可编造来处）"
        )
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
        target = getattr(stance, "held_commitment", "") or ""
        if not target and len(context.last_commitments) == 1:
            target = context.last_commitments[0]  # 唯一一笔，不是猜
        if target:
            focus = _clip_bounded(topic_from_pending_commitment(target) or target, 60)
            focus_source = "同场承诺"
        dominant_why = "意义主导｜同场出口的承诺不可跟着改口否定，压过本轮动力；动力仍在 Brief（来源：外补·同场承诺一致性）"
    elif stance.posture == "needs_clarify":
        dominant = "meaning"
        say_intent = "不空壳升华：先澄清这一轮能讲清的直径，没有根据就不装人生答案"
        dominant_why = "意义主导｜没有根据的意义态度先澄清，不端空壳升华；动力仍在 Brief（来源：《活出生命的意义》态度价值须有根据）"
    elif commit_resolve:
        # 用户示意已兑现：结构化 commit_resolve（宁缺既有线索，勿扩词表）
        dominant = "meaning"
        commit_resolve = True
        say_intent = "对方示意同场那件约定已接上，可以放下再接眼前这句"
        focus = _clip_bounded(topic_from_pending_commitment(done_same) or done_same, 60)
        focus_source = "同场承诺"
        dominant_why = "意义主导｜对方示意同场约定已兑现，先销账再接眼前（来源：外补·同场承诺一致性）"
    elif context.last_commitments:
        dominant = "meaning"
        commit_deliverable = True
        pending0 = recognized_same or context.last_commitments[0]
        focus = _clip_bounded(topic_from_pending_commitment(pending0) or pending0, 60)
        focus_source = "同场承诺"
        dominant_why = "意义主导｜同场还有未兑现的承诺，先守自己的话再接新的；动力仍在 Brief（来源：外补·同场承诺一致性）"
        toks = _pending_topic_tokens(pending0)
        if toks and any(tok in (user_text or "") for tok in toks):
            commit_deliver_intent = True  # 用户点到主题＝可检验接着交付，非纯守诺
        why = drive.why or ""
        # 输入信号判停 + 同场承诺：先说停，再说约定还在；不能让通用守诺模板盖掉这一句停。
        if _input_stop_label(drive) is not None:
            commit_hold_with_drive = True
            say_intent = (
                f"{_drive_say_intent(drive)}；同场约定还在，说清它没消失"
            )
        # 收束 hold／好奇 pursue：动力人话进 say_intent，薄守诺并存（勿只吐守诺模板）
        elif drive.direction == "hold" and (
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
        dominant_why = "意义主导｜必要痛苦/自虐加戏在场，先分辨哪些苦可以少受，不替对方定论（来源：《活出生命的意义》必要痛苦 vs 自虐加戏）"
        if context.stance_self_torture_pending:
            say_intent = "不跟加戏，留意哪些苦可以少受，不替对方断定"
        else:
            say_intent = "承认必要的痛苦还在，不假装解决；可以陪对方面对"
    elif (context.stance_attitude_pending
          and not context.drive_identity_ask_pending
          and not context.drive_identity_answer_pending):
        dominant = "meaning"
        say_intent = "承认对方说的处境无法改变；不许诺改变它，选择在此陪对方一起面对，不替对方赋予意义"
        dominant_why = "意义主导｜处境不可改变时先承认事实，再选择怎么面对（来源：《活出生命的意义》态度价值）"
    elif (context.open_questions and is_neutral_filler(user_text)
          and "想被看见｜" not in (drive.why or "")):
        # filler + 确有悬问：短暂接话，但不当作用户已经回答。
        dominant = "meaning"
        say_intent = "先接住这声回应，悬问仍留着，不把它当作已经回答"
        dominant_why = "意义主导｜轻接话时短暂捡一次同场悬问，接完即收，不让悬问长期占领主导（来源：外补·悬问不过夜）"
    elif context.drive_openq_satisfied_pending and drive.direction == "hold":
        dominant = "drive"
        say_intent = _drive_say_intent(drive)
        dominant_why = "动力主导｜悬问被接住，喜欢/满足侧到了，不必再追（来源：《贪婪的多巴胺》想要 vs 喜欢）"
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
            # 债有身份：认出的那笔优先；认不出回落到最老一笔（同改前）。
            pressed_commitment = (
                match_pending_commitment(user_text, prior)
                or prior.commitments_pending[0]
            )
            pending0 = pressed_commitment
        topic = topic_from_pending_commitment(pending0) or "这事"
        focus = _clip_bounded(topic_from_pending_commitment(pressed_commitment) or pressed_commitment or "这事", 60)
        focus_source = "上场承诺"
        dominant_why = "动力主导｜上场未兑现被催，追着兑现；承诺照结构化身份销（来源：外补·承诺一致性；《贪婪的多巴胺》缺口在外）"
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
        focus, focus_source = _clip_bounded(topic, 60), "同场事实"
        dominant_why = "动力主导｜同场催一个可核对的约定，追着兑现；承诺照结构化身份销（来源：外补·同场承诺一致性；《贪婪的多巴胺》缺口在外）"
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
            dominant_why = "动力主导｜按本场已有痕迹接回指，不编场外经历（来源：《贪婪的多巴胺》缺口在外；外补·薄情境）"
            say_intent = (
                "接住对方对同场刚才话题的回指，用本场已有痕迹接话，"
                "不装没发生过、也不编场外经历。"
                f"本场痕迹：{digest}"
            )
        else:
            say_intent = _drive_say_intent(drive)

    if dominant == "drive" and not dominant_why:
        dominant_why = "动力主导｜无诚实冲突、无未兑现承诺，按本轮推力方向接（来源：《贪婪的多巴胺》想要/喜欢）"

    # 粒度只读结构字段；保留先前分支的主导和具体约束，不靠人话子串判定。
    if org.grain == "differentiated" and not conflicts:
        dominant_why += "；组织层只收粒度、不否决动力（来源：《自我的发展》组织复杂度匹配）"
        if context.last_commitments:
            if not commit_hold_with_drive:
                say_intent = f"{_drive_say_intent(drive)}；{say_intent}"
            commit_hold_with_drive = True
        else:
            say_intent = (
                f"{_drive_say_intent(drive)}；"
                "守住这一轮不可让出的立场，不跟着改口否定"
            )

    # 停优先（含 org 冲突）：凡判停，say_intent 一律是停——真实 LLM 路径读的就是这句。
    # org 冲突／stance／filler／悬问这些更早的分支不得把「停」改写成「接着说」；
    # 组织约束仍写进 org_conflicts＋must_not_pretend，诚实口径不丢。
    if _input_stop_label(drive) is not None:
        dominant_why = "判停优先｜对方明说暂停/终止，本轮心思先应一声停住；组织冲突仍照记，主导字段保留诚实冲突层（来源：INPUT_INTENT_V1；规格硬闸3）"
        say_intent = _drive_say_intent(drive)
        if context.last_commitments:
            say_intent = f"{say_intent}；同场约定还在，说清它没消失"
            commit_hold_with_drive = True

    return ThoughtBrief(
        understanding=understanding,
        user_input=SourcedInput(text=_clip_bounded(user_text, 600), source="user",
                                provenance="birth/pipeline.py:turn"),
        openq_resolve_target=openq_target,
        prior_openq_resolve_target=prior_target,
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
        pressed_commitment=pressed_commitment,
        recognized_prior_commitment=recognized_prior,
        recognized_same_commitment=recognized_same,
        commit_resolve=commit_resolve,
        commit_deliverable=commit_deliverable,
        commit_deliver_intent=commit_deliver_intent,
        commit_hold_with_drive=commit_hold_with_drive,
        commit_deny=commit_deny,
        hold_same_field=hold_same_field,
        org_conflicts=list(conflicts),
        dominant_why=dominant_why or "仲裁未写明取舍（工程师需修复）",
        focus=focus,
        focus_source=focus_source if focus else "无实质内容",
    )

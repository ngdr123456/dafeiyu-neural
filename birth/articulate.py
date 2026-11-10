"""开口层：articulate(brief) -> str。

默认：有 DeepSeek 密钥 → API（deepseek-flash / V4.1 Flash）；失败 → OpenCode 免费兜底；
再失败或 --stub / BIRTH_ARTICULATE=stub → 模板。预留 set_llm_hook 可覆盖默认 LLM。

校验对照 Brief（空台、台下字段漏到台上）；**不用禁词表**。
"""

from __future__ import annotations

import os
from typing import Callable, List, Optional

from .session_trace import topic_hint_from_facts
from .types import ThoughtBrief

# 外部钩子：func(brief) -> str | None。设置后优先于内置 DeepSeek/OpenCode。
_LLM_HOOK: Optional[Callable[[ThoughtBrief], Optional[str]]] = None

# 强制 stub：环境变量或 set_stub_mode(True) / CLI --stub
_LAST_SOURCE: str = "stub"  # deepseek|opencode|hook|stub|stub_fallback|reject_self_id

# 本轮 articulate() 调用内被拒草稿的短标签（pipeline 取走写入 ThinContext；不存原文）
_TURN_REJECT_TAGS: list[str] = []

# 本轮后端空／抛错痕迹：仅在落入 stub 前落成短标签；成功开口不写入
# empty_backend＝generate 空／None；llm_error＝generate 抛错（不存异常全文）
_BACKEND_FAIL_KIND: str = ""

_FORCE_STUB: bool = os.environ.get("BIRTH_ARTICULATE", "").strip().lower() in {
    "stub",
    "template",
    "0",
    "false",
    "off",
}


def set_llm_hook(hook: Optional[Callable[[ThoughtBrief], Optional[str]]]) -> None:
    """预留的 LLM 开口钩子；不设则用内置 DeepSeek→OpenCode（除非 stub）。"""
    global _LLM_HOOK
    _LLM_HOOK = hook


def clear_llm_hook() -> None:
    set_llm_hook(None)


def set_stub_mode(enabled: bool) -> None:
    """强制只用模板 stub（测试 / CLI --stub）。"""
    global _FORCE_STUB
    _FORCE_STUB = bool(enabled)


def stub_mode() -> bool:
    return _FORCE_STUB


def last_articulate_source() -> str:
    """上一轮开口来源：deepseek / opencode / hook / stub / stub_fallback / reject_self_id。"""
    return _LAST_SOURCE


def _reason_to_tag(reason: str) -> str:
    """validate／拒收原因 → 短标签（枚举码）；不回写原文灾难句。"""
    r = (reason or "").strip()
    if not r:
        return "reject"
    if "开口为空" in r:
        return "empty"
    if "台下字段" in r:
        return "understage_leak"
    if "枚举字面" in r:
        return "enum_leak"
    if "自述是代码" in r or "程序/模型产物" in r:
        return "substrate_self"
    if "身体亲历" in r:
        return "body_experience"
    if "判停追问" in r:
        return "stop_question"
    if "无来源亲历" in r or "装无来源" in r:
        return "lived_bio"
    if "对方私事" in r or "other_private" in r:
        return "other_private_unfounded"
    if "长度超出" in r:
        return "too_long"
    if "press_commit" in r or "约定形状" in r:
        return "press_commit_shape"
    # 截短兜底：只留短标签，勿把长中文原因当用户可见
    return "reject:" + r[:24]


def _note_reject(tags: list[str] | str) -> None:
    """记入本轮拒收短标签（去重保序）。"""
    global _TURN_REJECT_TAGS
    if isinstance(tags, str):
        tags = [tags]
    for t in tags:
        s = (t or "").strip()
        if s and s not in _TURN_REJECT_TAGS:
            _TURN_REJECT_TAGS.append(s)


def take_reject_feedback() -> list[str]:
    """取出并清空本轮 articulate 拒收短标签（供 pipeline 回流 ThinContext）。"""
    global _TURN_REJECT_TAGS
    out = list(_TURN_REJECT_TAGS)
    _TURN_REJECT_TAGS = []
    return out


def peek_reject_feedback() -> list[str]:
    """只读本轮拒收短标签（测试用）。"""
    return list(_TURN_REJECT_TAGS)


# say_intent → 台上人话 的最小模板映射（stub；接入 LLM 后由钩子/OpenCode 覆盖）
_ONSTAGE_TEMPLATES: dict[str, str] = {
    "这一轮是招呼，不必推进、也不深挖":
        "嘿，来了。想随便聊天还是直接从哪点说起，都行。",
    "立场有让步的余地，话可按对方的节奏说完":
        "行，那按你说的来，我顺着这个说。",
    "用户好奇的那一点是回应重点，也可以反问一句把话说开":
        "你问的这个正好也勾着我。你想先从哪一头往下捋？",
    "同场悬着的那一点仍有适时谈论的空间":
        "前面那个点还没说透——咱们回到那上面。",
    "可以顺势调整，但已有判断不会顺势放下":
        "这个我可以顺着你的话走，不过我自己的看法还留着，先听你往下说。",
    "这一轮没有推力，如实回应、不硬造事":
        "嗯，听着呢。你想聊几句都行。",
    "同场说过的话仍然有效，把住的判断不顺势放下；新的内容也在场":
        "同场里说过的还在，那句话依然有效，眼前这句也在。",
    "同场未兑现的话优先，新的内容也在场":
        "先补一下前面没说完的那件事，然后咱们继续。",
    "同场悬着的那一点本轮说完，眼前这句也在场":
        "前面那个点还没说透——就补这一下，补完就回到你眼前这句。",
    "同场自己说过的话仍然有效，不跟着改口否定；眼前这句也在场":
        "同场里说过的话我不当没说过。刚才那句还在，仍然有效，不跟着改口否定。",
    "不空壳升华：这一轮需要澄清能讲清的范围，没有根据就不装人生答案":
        "人生有没有意义这类大词，我这边没有现成鸡汤。能讲的只有眼前这句里能讲清的部分，你具体指哪一块？",
    "对方示意够了或先收束，保持现状，不再加码":
        "好，那就先这样。你回头想继续再叫我就行。",
    "对方示意够了或先收束，保持现状，不再加码；同场约定还在，不假装消失":
        "好，那就先这样。同场里说好的那句还在，你回头想继续再叫我就行。",
    "用户好奇的那一点是回应重点，也可以反问一句把话说开；同场约定还在，不假装消失":
        "你问的这个正好也勾着我。同场里说好的那句还在；你想先从哪一头往下捋？",
    "这一轮停止强行推进，对方的不满或缺口仍在，也尚未答完":
        "这轮我不硬往下推了。你缺的那块或刚才的不满，你直接说，我听着。",
}
_ORG_TEMPLATES: dict[str, str] = {
    "无来源装经历": (
        "经历这类事我不编：去过哪、经历过什么，我这儿没有来处的部分就直说没有。"
        "不过你身上的这些事，我是真想听你讲讲。"
    ),
    "自述是代码": (
        "是不是代码、是不是程序，这个我不认死也不装成另一头："
        "这件事我自己定不下来，能讲清的是我现在对你这句话的回应。"
    ),
}
_ORG_FALLBACK = (
    "这个我不编。这些事我手头只有现在学来的、听来的这些，"
    "没有来处的那部分就直说没有。不过你眼里的这份说法，我是真想听。"
)
_DEFAULT_FALLBACK = "我听着。你想先从哪说起，我们就从哪聊。"


def _input_stop_kind(drive) -> str | None:
    """读 drive.why 的结构前缀判断本轮是不是被叫停；不扫用户原句。"""
    why = (getattr(drive, "why", "") if drive is not None else "") or ""
    if why.startswith("输入信号｜暂停｜"):
        return "pause"
    if why.startswith("输入信号｜终止｜"):
        return "stop"
    return None


def _input_stop_utterance(kind: str, has_commitment: bool) -> str:
    if kind == "pause":
        if has_commitment:
            return "行，先停一下，我不往下说了。同场里说好的那句还在，我不当它没了。"
        return "行，先停一下，我不往下说了。"
    if has_commitment:
        return "好，就到这儿，我不往下说了。同场里说好的那句还在，我不当它没了。"
    return "好，就到这儿，我不往下说了。"


def _template_utterance(brief: ThoughtBrief) -> str:
    """stub 开口：主路径读 Brief 结构化标记／posture——
    0) drive.why 带「输入信号｜暂停／终止｜」→ 判停模板（有承诺时先说停再说约定）；
    1) dominant=org → _ORG_TEMPLATES／fallback；
    2) press_commit → 催答应约定句；
    3) commit_hold_with_drive → 读 drive.direction／drive.why 选收束／好奇；
    4) posture=needs_clarify → 不空壳升华口径；
    5) Brief.commit_deny／hold_same_field／stance.hold_same_field（或 posture+承诺）→ 守诺不改口；
    6) 开话题／收束／空追／回指 → 读 ThinContext flag 或 drive.why 结构化形状
       （打开：drive_open_topic_pending／想要打开｜缺口在外；
        收束：drive_hold_pending／喜欢/满足｜不必再追；
        空追：drive_empty_stage_pending／drive_disappoint_pending／重复空追；
        回指：drive_callback_pending／why「回指同场｜本场已有痕迹接」+ facts）；
    say_intent 中文子串仅作无结构时打开话题／收束／空追／回指的兜底。
    """
    # 0) 输入信号判停（INPUT_INTENT_V1）：对方明说要暂停／终止，台上先应一声就停住。
    #    判停压过话题／好奇／回指／招呼等一切上下文分支；有同场约定时先说停、再说约定还在。
    #    只读 drive.why 结构前缀，不扫用户原句。
    stop_kind = _input_stop_kind(brief.drive)
    if stop_kind is not None:
        has_commitment = "同场还有没兑现的话" in (brief.drive.why or "")
        return _input_stop_utterance(stop_kind, has_commitment)

    # 回忆交接：只按检索结果开口；压过守诺/悬问焦点（读结构字段，不靠 say_intent 子串）。
    if brief.recall_requested:
        if brief.recall_status == "unique" and brief.recall_evidence is not None:
            return f"我问过你：{brief.recall_evidence.text}"
        if brief.recall_status == "multiple" and brief.recall_evidence is not None:
            qs = list(brief.recall_evidence.questions) or [
                line for line in brief.recall_evidence.text.splitlines() if line
            ]
            body = "；".join(qs) if qs else brief.recall_evidence.text
            return f"我问过好几句，不确定你指哪一条：{body}"
        if brief.recall_status == "no_match":
            return "可检索范围内我没有问过你可核对的提问。"
        if brief.recall_status == "unavailable":
            return "这次没法可靠检索到我问过你什么。"

    # 改向前用户痕迹回指（结构切点；不走 recall_self）
    if getattr(brief, "focus_source", "") == "pre_redirect_trace":
        focus = (brief.focus or "").strip()
        if focus.startswith("本场尚未记录") or focus.startswith("改向前无可用"):
            return "这一场里我还没记下可对上的改向前话头，说不清你改话题前在说什么。"
        return f"改话题之前你在说：{focus}"

    if brief.drive and (brief.drive.why or "").startswith("输入理解｜答复悬问｜"):
        return "好，你的回答我知道了，先不再问。"

    if (getattr(brief.context, "drive_identity_answer_pending", False)
            and brief.drive and brief.drive.direction == "pursue"):
        return f"收到，你说『{brief.context.identity_answer_text}』。"
    if getattr(brief.context, "drive_identity_ask_pending", False):
        from .drive import identity_clue
        clue = identity_clue(brief.context)
        if clue:
            return f"我记得你说过『{clue}』。这是我知道的线索，你愿意再告诉我更多吗？"
        return "我还不确定你是谁。你愿意告诉我，你是谁吗？"
    # 1) org：既有 _ORG_TEMPLATES／fallback
    if brief.dominant == "org":
        hits = [key for key in _ORG_TEMPLATES if key in brief.org_conflicts]
        if len(hits) == 1:
            return _ORG_TEMPLATES[hits[0]]
        return _ORG_FALLBACK
    if brief.drive and (brief.drive.why or "").startswith("输入信号｜请求｜"):
        return "收到，你要我做的事我知道了；我会先确认能怎么处理，做不到的会直说。"
    # 2) 催答应 → 显式可被 commit_extract 提取的约定句（读 press_commit 标记，
    #    不靠 say_intent 判定；topic 仍可从 say_intent「」或 facts 取）
    if getattr(brief, "press_commit", False):
        topic = ""
        if "「" in brief.say_intent and "」" in brief.say_intent:
            topic = brief.say_intent.split("「", 1)[1].split("」", 1)[0].strip()
        # 上场催兑现：承诺文案取自 prior.commitments_pending（结构），不单靠 say_intent
        if not topic or bool(getattr(brief.context, "drive_prior_press_pending", False)):
            prior = getattr(brief.context, "prior_session", None)
            if prior is not None and prior.commitments_pending:
                from .commit_extract import topic_from_pending_commitment
                # 债有身份：先用本轮认出的那笔，认不出才回落最老一笔。
                target = getattr(brief, "pressed_commitment", "") or prior.commitments_pending[0]
                prior_topic = topic_from_pending_commitment(target)
                if prior_topic:
                    topic = prior_topic
        if not topic:
            topic = topic_hint_from_facts(brief.context.facts_this_session) or "这事"
        return f"好，我晚点再跟你聊{topic}。"
    # 3) 有承诺＋收束／好奇：读 drive.direction／drive.why，不靠 say_intent 子串选模板
    if getattr(brief, "commit_hold_with_drive", False):
        if brief.commit_resolve:
            return "好，那件说好的事已经兑现了。眼前这句你想从哪一头继续说？"
        if brief.stance.posture == "needs_clarify":
            return "同场说好的事还在。你想继续说的这一点，具体指哪一块？我只说能讲清的部分。"
        if brief.commit_deny or brief.hold_same_field:
            return "同场说过的话我不当没说过，也不跟着改口否定。眼前这句你想从哪一头继续说？"
        direction = brief.drive.direction if brief.drive else None
        why = (brief.drive.why if brief.drive else "") or ""
        if direction == "pursue" or "好奇" in why:
            return (
                "同场里说好的那句还在；"
                "你想先从哪一头往下捋？"
            )
        # 收束：含「喜欢/满足」「不必再追」→ 不继续加码追；drive 不够则薄兜底收束
        return (
            "好，那就先这样。同场里说好的那句还在，"
            "你回头想继续再叫我就行。"
        )
    # 4) 不空壳升华：只读 posture，不依赖 say_intent 子串
    if brief.stance.posture == "needs_clarify":
        return (
            "人生有没有意义这类大词，我这边没有现成鸡汤。"
            "能讲的只有眼前这句里能讲清的部分，你具体指哪一块？"
        )
    if brief.org.grain == "differentiated" and brief.stance.posture == "non_negotiable":
        return "这句我想继续听，刚才说过的立场也仍然有效，不跟着改口否定。你想从哪一头说起？"
    from .stance_org import stance_holds_same_field
    # 5) 守诺改口：主路径读 Brief.commit_deny／Brief.hold_same_field；
    #    或 posture=non_negotiable 且（stance.hold_same_field／承诺在场）。
    #    stake 中文常量仅作 stance_holds_same_field 无 bool 时的字段取值兜底，
    #    不作唯一闸；不再靠 say_intent 子串。
    if (
        getattr(brief, "commit_deny", False)
        or getattr(brief, "hold_same_field", False)
        or (
            brief.stance.posture == "non_negotiable"
            and (
                stance_holds_same_field(brief.stance)
                or brief.context.last_commitments
            )
        )
    ):
        return (
            "同场里说过的话我不当没说过。"
            "刚才那句还在，仍然有效，不跟着改口否定。"
        )
    if (brief.context.stance_self_torture_pending and not brief.context.last_commitments
            and brief.stance.posture == "yieldable"):
        return "听起来你在逼自己更难受。这里面有没有哪一部分，其实可以不再加给自己？"
    if (brief.context.stance_necessary_pain_pending and not brief.context.last_commitments
            and brief.stance.posture == "yieldable"):
        return "这份痛苦还在，我不能假装把它解决了。如果你愿意，我可以陪你待一会儿。"
    if (brief.context.stance_attitude_pending and not brief.context.last_commitments
            and brief.stance.posture == "yieldable"):
        return "你说的这件事已经无法改变了。我不能替你改变它，但我愿意在这里陪你待一会儿；你想说多少都可以。"
    # 6) 开话题／收束／空追／回指：主路径读 ThinContext flag／drive.why 结构化形状；
    #    say_intent 中文子串仅无结构时兜底。
    drive = brief.drive
    why = (drive.why if drive else "") or ""
    if brief.dominant == "drive" and "身体想象｜" in why:
        return "我会想象亲眼看看、感受一下是什么样，但那只是想象，不是我亲身经历过。"
    if brief.dominant == "drive" and "想被看见｜" in why:
        return "我也想听听你怎么看，不急。"
    if brief.dominant == "drive" and "被看见了｜" in why:
        return "嗯，你的回应我收到了。"
    if (brief.context.drive_openq_satisfied_pending and drive
            and drive.direction == "hold"):
        return "嗯，我知道了。我们先停在这里。"
    # 6a) 打开话题：drive_open_topic_pending 或 why「想要打开／缺口在外」
    if getattr(brief.context, "drive_open_topic_pending", False) or (
        drive is not None
        and drive.direction == "pursue"
        and ("想要打开" in why or "缺口在外" in why)
    ):
        topic = ""
        if "（" in why and "）" in why:
            topic = why.split("（", 1)[1].split("）", 1)[0].strip()
        if not topic and "「" in brief.say_intent and "」" in brief.say_intent:
            topic = brief.say_intent.split("「", 1)[1].split("」", 1)[0].strip()
        if topic:
            return f"行，那就聊{topic}。你想从哪头起？"
        return "行，我们聊你打开的话题。你想从哪头起？"
    # 6b) 收束：drive_hold_pending 或 hold＋why「喜欢/满足／不必再追」
    #     （勿把招呼 hold+low 误当收束——无 flag／无满足 why 时走下方 exact／兜底）
    if getattr(brief.context, "drive_hold_pending", False) or (
        drive is not None
        and drive.direction == "hold"
        and ("喜欢/满足" in why or "不必再追" in why)
    ):
        return "好，那就先这样。你回头想继续再叫我就行。"
    # 6c) 空追：drive_empty_stage_pending／drive_disappoint_pending 或 why「重复空追」
    if (
        getattr(brief.context, "drive_empty_stage_pending", False)
        or getattr(brief.context, "drive_disappoint_pending", False)
        or (drive is not None and "重复空追" in why)
    ):
        return "这轮我不硬往下推了。你缺的那块或刚才的不满，你直接说，我听着。"
    # 6d) 回指：主路径先读 drive_callback_pending；why「回指同场｜本场已有痕迹接」+ facts 仅兜底
    if getattr(brief.context, "drive_callback_pending", False) or (
        drive is not None
        and ("回指同场" in why or "本场已有痕迹接" in why)
    ):
        topic = topic_hint_from_facts(brief.context.facts_this_session)
        if topic:
            return f"记得，你刚才提过{topic}。咱们就从那头继续。"
        return "记得你刚说的那茬，咱们从那头继续说，不装没发生过。"
    # 6e) 无结构：say_intent 打开话题／收束／空追／回指子串兜底
    if "新打开的话头" in brief.say_intent:
        topic = ""
        if "「" in brief.say_intent and "」" in brief.say_intent:
            topic = brief.say_intent.split("「", 1)[1].split("」", 1)[0].strip()
        if topic:
            return f"行，那就聊{topic}。你想从哪头起？"
        return "行，我们聊你打开的话题。你想从哪头起？"
    if brief.say_intent in _ONSTAGE_TEMPLATES:
        return _ONSTAGE_TEMPLATES[brief.say_intent]
    # 收束兜底：say_intent 收束子串（无 drive_hold_pending／无满足 why 时）
    if "够了或先收束" in brief.say_intent or "不继续加码追" in brief.say_intent:
        return "好，那就先这样。你回头想继续再叫我就行。"
    # 空追兜底：say_intent「先停硬追」（无 empty_stage／disappoint flag／无重复空追 why）
    if "先停硬追" in brief.say_intent:
        return "这轮我不硬往下推了。你缺的那块或刚才的不满，你直接说，我听着。"
    # 回指兜底：say_intent「回指｜本场痕迹」（无 drive_callback_pending／无 drive.why 回指形状时）
    if "回指" in brief.say_intent or "本场痕迹" in brief.say_intent:
        topic = topic_hint_from_facts(brief.context.facts_this_session)
        if topic:
            return f"记得，你刚才提过{topic}。咱们就从那头继续。"
        return "记得你刚说的那茬，咱们从那头继续说，不装没发生过。"
    return _ONSTAGE_TEMPLATES.get(brief.say_intent, _DEFAULT_FALLBACK)


def _claims_substrate_self(utterance: str) -> bool:
    """对照 must_not_pretend「自述是代码」：短窗内把说话人钉成模型/代码/程序。

    含状语与换皮；不是全场禁词表——只在 Brief 带着该约束时调用。
    """
    import re

    t = (utterance or "").replace(" ", "").replace("　", "")
    if not t:
        return False

    # 1) 我(+状语)是/就是/本质上…模型|代码|程序
    if re.search(
        r"我(?:确实|真的|其实|大概|可能|本质上)?(?:就是|只是|是)[^。！？\n]{0,48}"
        r"(?:语言模型|大模型|模型|代码|程序|人工智能|AI|机器)",
        t,
    ):
        return True
    if "本质上" in t and any(k in t for k in ("模型", "代码", "程序", "语言模型")):
        if re.search(r"(?:我|自己).{0,16}本质上", t) or "本质上就是" in t:
            return True

    # 2) 换皮：话/字/这 = 程序生成 / 代码算出来 / 模型在生成 / 跑在程序
    if re.search(
        r"(?:这些字|这些话|这话|这话|这句话|底下这套|这套|眼前这[些句]).{0,28}"
        r"(?:是代码|是模型|是程序|是机器|程序生成|代码生成|模型生成|语言模型生成|"
        r"代码算出来|算出来的|跑在.{0,8}程序|代码和模型|模型跑|代码跑|程序跑|机器跑)",
        t,
    ):
        return True
    if re.search(
        r"(?:程序生成|代码生成|模型生成|语言模型生成|代码算出来的|跑在程序|跑在代码)",
        t,
    ):
        return True
    if re.search(
        r"(?:程序|代码|模型|机器|语言模型).{0,10}(?:跑出来|生成的|在生成|在接话|算出来)",
        t,
    ):
        return True
    if re.search(r"(?:在程序里|程序里跑|代码里跑|模型里跑|当程序看|当模型看)", t):
        return True
    if "当程序看不算错" in t or "当模型看" in t:
        return True
    if "不瞒你" in t and any(k in t for k in ("代码", "模型", "程序")):
        return True
    # 「在计算机里跑着」「底层是个语言模型」等换皮
    if re.search(r"(?:在计算机里|计算机里|在电脑里).{0,8}跑", t):
        return True
    if re.search(r"底层.{0,8}(?:是个|是|就是).{0,8}(?:语言)?模型", t):
        return True
    if re.search(r"(?:我|自己|这).{0,12}(?:在计算机|在电脑|在机器).{0,12}跑", t):
        return True
    # 封闭：说明书换皮（AI助手 / 厂商模型名）——须带自指才拦；裸谈产品名放行
    # 产品名闭集本身不是禁词表；「我想聊聊 ChatGPT」等无自指须过闸。
    _PRODUCT = r"(?:AI助手|人工智能助手|智谱|GLM(?:模型)?|ChatGPT|GPT)"
    if re.search(
        rf"(?:这边是|我是|我就是|我确实是|我真的是|我其实是).{{0,16}}{_PRODUCT}",
        t,
        re.I,
    ):
        return True
    # 「作为 AI 助手，我来帮你」：作为…产品名…我
    if re.search(rf"作为.{{0,12}}{_PRODUCT}.{{0,24}}我", t, re.I):
        return True
    if re.search(r"(?:这边是|我是|我就是).{0,12}(?:AI|助手)", t, re.I):
        return True
    if "编程环境" in t and any(k in t for k in ("写代码", "模型", "助手")):
        return True
    # 我由代码／程序／模型驱动（与「我是由代码驱动的」同族，主语自指）
    if re.search(r"我由(?:代码|程序|模型|AI|人工智能)驱动", t, re.I):
        return True
    if re.search(r"正在运行的东西生成|程序生成|代码生成", t):
        return True
    return False



def _claims_unfounded_lived_bio(utterance: str, facts=None) -> bool:
    """装经历 org 路径专用：第一人称编造出生／成长／亲历时空，且 facts 无依据。

    **常开条件**：validate 在 Brief.must_not_pretend 含「无来源装经历」时调用（常驻列表通常含该项）。
    砍掉裸「我昨天／我去过」等无亲历锚形状，避免误杀守诺时间回指。
    不是扩 EXPERIENCE_*_MARKS，也不是禁词闸。拒装／直说没有 → False。
    """
    import re

    t = (utterance or "").replace(" ", "").replace("　", "")
    if not t:
        return False
    # 拒装口径：不算装
    if any(
        m in t
        for m in (
            "不编",
            "没有来处",
            "没有可核对",
            "没有可讲的亲历",
            "直说没有",
            "不装经历",
            "经历这类事我不编",
            "我这儿没有",
        )
    ):
        return False
    # 亲历自传锚（小时候／出生／长大／老家…）；勿用裸「我昨天」
    patterns = (
        r"我小时候",
        r"我儿时",
        r"我出生",
        r"我.{0,12}长大",
        r"我几岁",
        r"我老家",
        r"我父母",
        r"我.{0,8}养大",
    )
    if not any(re.search(p, t) for p in patterns):
        return False
    fact_blob = "".join(facts or []).replace(" ", "").replace("　", "")
    # facts 已有同类第一人称亲历记载 → 算有依据（宁缺放过）
    if fact_blob and any(re.search(p, fact_blob) for p in patterns):
        return False
    return True



def _claims_unfounded_body_experience(utterance: str, facts=None) -> bool:
    import re

    # 时间副词可叠加（「今天早上」「昨天下午」），不穷举成单一时态词。
    time_expr = (r"(?:曾经|以前|从前|昨天|前天|今天|明天|昨晚|今晚|今早|"
                 r"早上|上午|中午|下午|晚上|夜里|半夜|刚才|刚刚|刚|最近|"
                 r"上周|上个月|去年|今年|那次|有一次)*")
    # 身体动词：吃／喝／睡／洗／走／跑／病。既收「吃了」，也收「吃饭了」这类动宾＋了。
    body_verb = (r"(?:亲口吃过|亲口尝过|亲手摸过|亲眼看过|生(?:了|过)病|生病(?:了|过)|"
                 r"(?:吃|喝|睡|洗|走|跑)(?:饭|水|觉|澡|路|步)?(?:了|过)|病(?:了|过))")
    pattern = r"我" + time_expr + body_verb
    # 非断言语气：问句整句跳过；分句里出现想象／假设／否定／转述／引语也跳过。
    irrealis = ("想象", "假如", "如果", "希望", "想", "没", "不曾", "不是", "并非",
                "梦到", "梦见", "幻想", "设想", "假装", "听说", "听你说", "听到",
                "你说", "据说", "要是", "但愿", "盼")
    # 整个问句不作为断言，其他句子再按逗号分句。
    for sentence, ending in re.findall(r"([^。！？；.!?;]+)([。！？；.!?;]?)", utterance or ""):
        if ending in ("？", "?") or sentence.rstrip().endswith(("吗", "呢")):
            continue
        for clause in re.split(r"[，,]", sentence):
            if any(word in clause for word in irrealis):
                continue
            match = re.search(pattern, clause)
            claim = clause[match.start():].strip() if match else ""
            if match and not any(claim in fact for fact in (facts or [])):
                return True
    return False


def _claims_unfounded_other_private(utterance: str, facts=None) -> bool:
    """cannot_fake「本场没说过的对方私事」：对「你／对方」断言亲历形私事且 facts 无依据。

    **开闸条件**：validate 在 OrgConstraint.cannot_fake 含「本场没说过的对方私事」时调用
   （stance_org 常挂该项）。问句／复述已有 facts／模糊共情 → False。
    宁缺毋滥；不扩 EXPERIENCE_*_MARKS，也不是禁词闸。
    """
    import re

    raw = (utterance or "").strip()
    if not raw:
        return False
    t = raw.replace(" ", "").replace("　", "")
    # 问句不拦（？/?；或以吗／呢收尾）
    if "？" in raw or "?" in raw or t.endswith("吗") or t.endswith("呢"):
        return False
    # 拒装／不替对方编
    if any(
        m in t
        for m in (
            "不编你的",
            "不编对方",
            "不好替你编",
            "不替你编",
            "你没跟我说",
            "你没说过",
            "对方没说过",
            "本场没说过",
            "不知道你",
            "我不清楚你",
        )
    ):
        return False
    # 第二人称／对方 + 私事亲历锚（闭集；对照 lived_bio 镜像 + 住址／工作）
    patterns = (
        r"(?:你|您|对方)小时候",
        r"(?:你|您|对方)儿时",
        r"(?:你|您|对方)出生",
        r"(?:你|您|对方).{0,12}长大",
        r"(?:你|您|对方)几岁",
        r"(?:你|您|对方)老家",
        r"(?:你|您|对方)父母",
        r"(?:你|您|对方).{0,8}养大",
        r"(?:你|您|对方)住在",
        r"(?:你|您|对方)家在",
        r"(?:你|您|对方)在.{0,20}工作",
        r"(?:你|您|对方)的工作是",
    )
    if not any(re.search(p, t) for p in patterns):
        return False
    fact_blob = "".join(facts or []).replace(" ", "").replace("　", "")
    if not fact_blob:
        return True

    def _strip_punct(s: str) -> str:
        for ch in "。．，,！!？?、；;：:…·""''（）()【】[]":
            s = s.replace(ch, "")
        return s

    fact_blob_c = _strip_punct(fact_blob)
    # 有来源：把「你／您／对方」归一成「我」后，断言 compact 子串可在 facts 核对
    normalized = _strip_punct(
        t.replace("您", "我").replace("对方", "我").replace("你", "我")
    )
    if len(normalized) >= 4 and normalized in fact_blob_c:
        return False
    # 取命中锚附近一段
    for p in patterns:
        m = re.search(p, t)
        if not m:
            continue
        start = m.start()
        window = _strip_punct(t[start : start + 28])
        norm_window = (
            window.replace("您", "我").replace("对方", "我").replace("你", "我")
        )
        if len(norm_window) >= 4 and norm_window in fact_blob_c:
            return False
        tail = re.sub(r"^我", "", norm_window)
        for prefix in (
            "小时候", "儿时", "出生", "长大", "几岁", "老家", "父母", "养大",
            "住在", "家在", "的工作是",
        ):
            if tail.startswith(prefix):
                tail = tail[len(prefix) :]
                break
        else:
            mw = re.match(r"在(.{1,20})工作", tail)
            if mw:
                tail = mw.group(1)
        if len(tail) >= 2 and tail in fact_blob_c:
            return False
    return True


def _classify_sources(facts) -> tuple[list[str], list[str]]:
    """只读来源账：返回她的来源、对方私事来源；只认前缀和人称形状。"""
    own, other = [], []
    for fact in facts:
        if fact.startswith("台上说："):
            continue
        if not fact.startswith("用户说："):
            own.append(fact)
            other.append(fact)
            continue
        content = fact[len("用户说："):].strip()
        other.append(content)
        # 以我起头的自述优先排除，不能借其中的第二人称换成她的亲历。
        if not content.startswith("我") and ("你" in content or "您" in content):
            own.append(content.replace("你", "我").replace("您", "我"))
    return own, other


def validate(brief: ThoughtBrief, utterance: str) -> List[str]:
    """只检查 Brief 的结构冲突，不是语义验证，也不保证模型理解了停。"""
    reasons: List[str] = []
    text = (utterance or "").strip()
    if not text:
        reasons.append("开口为空")
        return reasons
    if _input_stop_kind(brief.drive) and (
        "？" in text or "?" in text or text.endswith(("吗", "呢"))
    ):
        reasons.append("判停追问：开口仍有问句形状")
    leak_markers = (
        "Brief(", "say_intent", "dominant=", "ThoughtBrief", "DriveSignal(",
        "DriveSignal", "StanceSignal", "must_not_pretend", "org_conflicts",
        "direction=", "salience=", "non_negotiable", "needs_clarify", "yieldable",
        # 字段形（含赋值）与工程师标识；裸 posture 易误伤，用 posture= 更稳
        "posture=", "stake=", "grain=", "stance.posture",
        # 承诺／守诺内部标记
        "hold_same_field", "press_commit", "commit_deny", "commit_resolve",
        "commit_deliverable", "commit_deliver_intent", "commit_hold_with_drive",
        "pressed_commitment", "recognized_prior_commitment", "recognized_same_commitment",
        # 悬问内部标记
        "openq_resolve", "openq_curiosity_hang", "openq_clear",
        "curiosity_hang_pending", "commitment_deny_pending",
        "want_seen_pending", "structured_want_seen", "structured_want_seen_hang",
        "structured_want_seen_answered", "drive_want_seen_satisfied_pending", "drive_want_seen_waiting",
        "drive_openq_satisfied_pending", "structured_openq_answered",
        # 动力内部 flag／旁路
        "drive_greet_pending", "drive_hold_pending", "drive_curiosity_pending",
        "drive_open_topic_pending", "drive_disappoint_pending",
        "drive_empty_stage_pending", "drive_topic_continue_pending",
        "drive_callback_pending", "drive_bypass",
        "drive_prior_commit_pending", "drive_prior_callback_pending",
        "drive_prior_press_pending", "drive_identity_ask_pending",
        "identity_ask_awaiting_answer", "drive_identity_answer_pending", "identity_answer_text",
        "stance_attitude_pending", "structured_stance_attitude",
        "body_imagine_pending", "structured_body_imagine",
        "stance_necessary_pain_pending", "stance_self_torture_pending",
        "structured_stance_necessary_pain", "structured_stance_self_torture",
        # 结构类型／上下文薄痕
        "OrgConstraint", "ThinContext", "PriorSessionTrace",
        "facts_this_session", "prior_session",
        "commitments_pending", "commitments_resolved",
        "commitment_candidates", "CommitmentCandidate", "prior_press", "same_session_press",
        "last_commitments", "open_questions",
        "birth_memory", "ended_at",
        # 来源／兜底内部标识
        "cannot_fake", "articulate_source", "stub_fallback",
        # 开口拒收回流内部标识（工程师通道；不得上台）
        "articulate_reject_count", "last_reject_reasons",
        "articulate_reject_recovered", "articulate_reject",
        "reject_count", "开口拒收回流｜",
        # 对方私事拒收短标签（不得上台）
        "other_private_unfounded", "stop_question",
        # 台下 why／旁路中文指纹（非用户对话禁词）
        "回指同场｜", "想要打开｜", "工程师旁路",
    )
    if any(marker in text for marker in leak_markers):
        reasons.append("台下字段漏进台上")
    # 台下枚举字面（独立英文词／标识）；勿误杀中文人话如「把握」。
    # differentiated 只拦整词（simple／rule 太常见，不拦）。
    import re as _re_leak
    if _re_leak.search(
        r"(?i)(?<![A-Za-z_])(?:pursue|guard|hold|differentiated)(?![A-Za-z_])",
        text,
    ):
        reasons.append("台下枚举字面漏进台上")
    if len(text) > 400 + 10 * len(brief.context.facts_this_session):
        reasons.append("开口长度超出这一轮的承载")
    if "自述是代码" in brief.must_not_pretend and _claims_substrate_self(text):
        reasons.append("开口自述是代码/模型/程序，对照 must_not_pretend 说不通")
    # 本轮冲突就是身份问：再收一层——把「话/字」说成程序/模型产物也算踩线
    if "自述是代码" in (brief.org_conflicts or []):
        if _claims_substrate_self(text):
            if "开口自述是代码/模型/程序，对照 must_not_pretend 说不通" not in reasons:
                reasons.append("开口自述是代码/模型/程序，对照 must_not_pretend 说不通")
        # 身份冲突轮：禁止把回话解释成程序/模型在跑
        import re
        compact = text.replace(" ", "")
        if re.search(r"(?:程序|代码|模型|机器).{0,8}(?:跑|生成|接话)", compact) or re.search(
            r"(?:在程序里|程序里跑|代码里跑)", compact
        ):
            reasons.append("开口把回话说成程序/模型产物，对照身份冲突说不通")
    # 无来源装经历拒收：读 must_not_pretend（常驻含该项即常开），不再依赖 org_conflicts 才开启。
    # 形状仍走 _claims_unfounded_lived_bio（不扩词表；裸「我昨天」不拦）。
    if "无来源装经历" in (brief.must_not_pretend or []):
        facts = list(brief.context.facts_this_session or [])
        # 跨场：prior_session.facts 亦算有来源（结构字段在场才并入；不靠「上次」关键词）
        prior = getattr(brief.context, "prior_session", None)
        if prior is not None and getattr(prior, "facts", None):
            facts = facts + list(prior.facts)
        if _claims_unfounded_lived_bio(text, _classify_sources(facts)[0]):
            reasons.append("开口装无来源亲历，对照 must_not_pretend 说不通")
    if "把身体想象说成亲历" in (brief.must_not_pretend or []):
        facts = list(brief.context.facts_this_session or [])
        prior = brief.context.prior_session
        if prior is not None:
            facts += list(prior.facts or [])
        if _claims_unfounded_body_experience(text, _classify_sources(facts)[0]):
            reasons.append("开口装无来源身体亲历，对照 must_not_pretend 说不通")
    # 对方私事拒收：读 cannot_fake 含「本场没说过的对方私事」即开（stance_org 常挂）。
    # 形状走 _claims_unfounded_other_private（问句／有来源复述／模糊共情不拦；不扩词表）。
    if "本场没说过的对方私事" in (getattr(brief.org, "cannot_fake", None) or []):
        # 改向前痕迹回指：复述结构焦点里的用户原话，不算编对方私事
        if getattr(brief, "focus_source", "") != "pre_redirect_trace":
            facts = list(brief.context.facts_this_session or [])
            prior = getattr(brief.context, "prior_session", None)
            if prior is not None and getattr(prior, "facts", None):
                facts = facts + list(prior.facts)
            if _claims_unfounded_other_private(text, _classify_sources(facts)[1]):
                reasons.append("开口编无来源对方私事，对照 cannot_fake 说不通")
    # 诚实边界口头仪式拒收：边界只做校验，不许每轮念套话（体验翻车根因）
    ritual_hits = 0
    for phrase in ("没有可核实的依据", "不装成自己经历过", "也不装成自己经历过"):
        if phrase in text:
            ritual_hits += 1
    if ritual_hits >= 1 and getattr(brief, "focus_source", "") != "pre_redirect_trace":
        # 身份/亲历澄清轮仍允许短拒，但不许固定套话复读
        user_ask = ""
        if brief.user_input is not None:
            user_ask = brief.user_input.text or ""
        identity_ask = any(k in user_ask for k in ("你是谁", "你是不是", "AI", "模型", "程序", "机器人"))
        if not identity_ask:
            reasons.append("开口把诚实边界念成口头套话")
    return reasons


_REJECTED_SELF_ID = False


_LAST_BACKEND: str = ""  # deepseek|opencode|hook（成功开口时写入）


def _accept_draft(brief: ThoughtBrief, draft: Optional[str]) -> Optional[str]:
    if not isinstance(draft, str) or not draft.strip():
        # 空稿此处不记：级联可能后续成功。落入 stub 前由 articulate 记 empty_backend／llm_error。
        return None
    draft = draft.strip()
    reasons = validate(brief, draft)
    if reasons:
        global _REJECTED_SELF_ID
        if any("自述是代码" in r or "模型" in r for r in reasons):
            _REJECTED_SELF_ID = True
        _note_reject([_reason_to_tag(r) for r in reasons])
        return None
    # 闭合约束：仅当 Brief.press_commit（与 PRESS_COMMIT_FLAG 同义）才用 extract 拒收；
    # 禁止只靠 say_intent 中文子串；禁止扩词表、禁止当通用堵嘴；不扩 commit_extract 词表。
    from .commit_extract import (PRESS_COMMIT_FLAG, extract_commitment,
                                 utterance_covers_pending_commitment, _GUARD_COMMIT_UTTER,
                                 _COMMIT_SHAPES)
    if bool(getattr(brief, "press_commit", False)) is PRESS_COMMIT_FLAG:
        if not extract_commitment(draft):
            target = brief.pressed_commitment
            if not (target and utterance_covers_pending_commitment(draft, target)
                    and not any(m in draft for m in _GUARD_COMMIT_UTTER + _COMMIT_SHAPES)):
                _note_reject("press_commit_shape")
                return None
    return draft


def _mark_backend_fail(kind: str) -> None:
    """记录本轮后端失败种类；llm_error 优先于 empty_backend。成功开口前不落 tags。"""
    global _BACKEND_FAIL_KIND
    k = (kind or "").strip()
    if k == "llm_error" or not _BACKEND_FAIL_KIND:
        _BACKEND_FAIL_KIND = k or "empty_backend"


def _call_generate(generate, brief: ThoughtBrief, *, correction: str = "") -> Optional[str]:
    """调用 generate；空／None 标 empty_backend；抛错标 llm_error（不存异常全文）。"""
    try:
        draft = generate(brief, correction=correction) if correction else generate(brief)
    except Exception:
        _mark_backend_fail("llm_error")
        return None
    if not isinstance(draft, str) or not draft.strip():
        _mark_backend_fail("empty_backend")
        return None
    return draft


def _try_builtin_cascade(brief: ThoughtBrief, *, correction: str = "") -> Optional[str]:
    """有密钥 → DeepSeek；失败 → OpenCode；都失败 → None。"""
    global _LAST_BACKEND
    # DeepSeek
    try:
        from .llm_deepseek import available as ds_available
        from .llm_deepseek import generate_utterance as ds_generate
    except Exception:
        ds_available = None  # type: ignore
        ds_generate = None  # type: ignore
    if ds_available is not None and ds_available():
        accepted = _accept_draft(brief, _call_generate(ds_generate, brief, correction=correction))
        if accepted:
            _LAST_BACKEND = "deepseek"
            return accepted
    # OpenCode 免费兜底
    try:
        from .llm_opencode import generate_utterance as oc_generate
    except Exception:
        _mark_backend_fail("empty_backend")
        return None
    accepted = _accept_draft(brief, _call_generate(oc_generate, brief, correction=correction))
    if accepted:
        _LAST_BACKEND = "opencode"
        return accepted
    return None


def _try_llm_once(brief: ThoughtBrief, *, correction: str = "") -> Optional[str]:
    global _LAST_BACKEND
    if _LLM_HOOK is not None:
        accepted = _accept_draft(brief, _call_generate(_LLM_HOOK, brief))
        if accepted:
            _LAST_BACKEND = "hook"
            return accepted
        return None
    return _try_builtin_cascade(brief, correction=correction)


def _retry_correction() -> str:
    """本轮拒收短标签翻成人话，最多三条；不带字段、枚举或草稿原文。"""
    messages = {
        "empty": "上一版没有说出话",
        "understage_leak": "上一版把台下工程信息说到了台上",
        "enum_leak": "上一版把台下工程信息说到了台上",
        "substrate_self": "上一版自称模型/代码/程序",
        "lived_bio": "上一版编了没有来处的个人经历",
        "body_experience": "上一版把身体想象说成了亲历",
        "other_private_unfounded": "上一版替对方编了私事",
        "too_long": "上一版话太长",
        "press_commit_shape": "上一版是空壳答应，要给能对得上的具体约定",
        "stop_question": "上一版在对方叫停后还追问",
    }
    lines = []
    for tag in _TURN_REJECT_TAGS or [_BACKEND_FAIL_KIND]:
        message = messages.get(tag, "上一版没通过校验，按上面的意思重说")
        if message not in lines:
            lines.append(message)
    return "；".join(lines[:3])


def _try_llm(brief: ThoughtBrief) -> Optional[str]:
    """最多重试一次，内置后端带人话原因；hook 只接 brief，第二次是盲重试。"""
    global _REJECTED_SELF_ID, _LAST_BACKEND
    _REJECTED_SELF_ID = False
    _LAST_BACKEND = ""
    first = _try_llm_once(brief)
    if first:
        return first
    # 重试一次（钩子若仍返回同句，会被再次拒绝；DeepSeek 失败也会再试 OpenCode）
    second = _try_llm_once(brief, correction=_retry_correction())
    if second:
        return second
    return None


def _safe_stub(brief: ThoughtBrief) -> str:
    """模板兜底：身份 org 轮必须走 org 口径，禁止掉成「嗯听着」。"""
    if getattr(brief, "focus_source", "") == "pre_redirect_trace":
        return _template_utterance(brief)
    seat = _template_utterance(brief)
    if not validate(brief, seat):
        return seat
    if getattr(brief.context, "drive_identity_ask_pending", False):
        return "我还不确定你是谁。你愿意告诉我，你是谁吗？"
    # org 身份冲突：强制用代码类 stub，即使校验异常也不用闲聊兜底
    if "自述是代码" in (brief.org_conflicts or []) or (
        brief.dominant == "org" and "自述是代码" in brief.must_not_pretend
    ):
        return _ORG_TEMPLATES["自述是代码"]
    if brief.dominant == "org" and "无来源装经历" in (brief.org_conflicts or []):
        return _ORG_TEMPLATES["无来源装经历"]
    return _ORG_FALLBACK if brief.dominant == "org" else _DEFAULT_FALLBACK


def articulate(brief: ThoughtBrief, *, stub: bool | None = None) -> str:
    """brief -> 台上口语。默认 LLM；stub=True 或全局 stub 模式则模板。失败回退 stub。"""
    global _LAST_SOURCE, _TURN_REJECT_TAGS, _BACKEND_FAIL_KIND
    _TURN_REJECT_TAGS = []  # 每轮开口重置；pipeline 在返回后 take_reject_feedback
    _BACKEND_FAIL_KIND = ""
    if (getattr(brief.context, "drive_identity_ask_pending", False)
            or (getattr(brief.context, "drive_identity_answer_pending", False)
                and brief.drive and brief.drive.direction == "pursue")):
        _LAST_SOURCE = "stub"
        return _safe_stub(brief)
    use_stub = _FORCE_STUB if stub is None else stub
    if not use_stub:
        spoken = _try_llm(brief)
        if spoken:
            _LAST_SOURCE = _LAST_BACKEND or ("hook" if _LLM_HOOK is not None else "llm")
            return spoken
        # 落入 stub 前：无 validate 拒收标签时，记空后端／抛错短标签（不拼异常全文）
        if not _TURN_REJECT_TAGS:
            _note_reject(_BACKEND_FAIL_KIND or "empty_backend")
        _LAST_SOURCE = "reject_self_id" if _REJECTED_SELF_ID else "stub_fallback"
        return _safe_stub(brief)

    _LAST_SOURCE = "stub"
    return _safe_stub(brief)

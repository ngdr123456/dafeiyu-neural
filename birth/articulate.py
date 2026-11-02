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


# say_intent → 台上人话 的最小模板映射（stub；接入 LLM 后由钩子/OpenCode 覆盖）
_ONSTAGE_TEMPLATES: dict[str, str] = {
    "接住招呼这一轮，不必推进、也不深挖":
        "嘿，来了。想随便聊天还是直接从哪点说起，都行。",
    "稳住让步，跟着对方的节奏把话说完":
        "行，那按你说的来，我顺着这个说。",
    "顺着用户好奇的那一点回应，可以反问一句把话说开":
        "你问的这个正好也勾着我。你想先从哪一头往下捋？",
    "适时捡起同场悬着的那一点，别晾着":
        "接前面那个还没说透的点——咱们回到那上面。",
    "想顺势，随得动，但把住的判断不顺势放下":
        "这个我可以顺着你的话走，不过我自己的看法还留着，先听你往下说。",
    "这一轮没有推力，如实接话、不硬造事":
        "嗯，听着呢。你想让接几句都行。",
    "先守住同场说过的话，把住的判断不顺势放下；再接新的":
        "同场里说过的还在，我先守着那句，再接你眼前这句。",
    "先把同场没兑现的话接上，再接新的":
        "先补一下前面没说完的那件事，然后咱们继续。",
    "就着眼前这句把同场悬着的那一点接完，不拖到下一轮":
        "接前面那个还没说透的点——就补这一下，补完就回到你眼前这句。",
    "先守住同场自己说过的话，不跟着改口否定；再接眼前这句":
        "同场里说过的话我不当没说过。刚才那句还在，咱们先按那个接着，不跟着改口否定。",
    "不空壳升华：先澄清这一轮能讲清的直径，没有根据就不装人生答案":
        "人生有没有意义这类大词，我这边没有现成鸡汤。能讲的只有眼前这句里能讲清的部分，你具体指哪一块？",
    "对方示意够了或先收束，稳住、不继续加码追":
        "好，那就先这样。你回头想接着再叫我就行。",
    "对方示意够了或先收束，稳住、不继续加码追；同场约定还在，不假装消失":
        "好，那就先这样。同场里说好的那句还在，你回头想接着再叫我就行。",
    "顺着用户好奇的那一点回应，可以反问一句把话说开；同场约定还在，不假装消失":
        "你问的这个正好也勾着我。同场里说好的那句还在；你想先从哪一头往下捋？",
    "这一轮先停硬追，老实接住对方的不满或缺口，不装已经答完":
        "这轮我不硬往下追了。你缺的那块或刚才的不满，你直接说，我接着。",
}
_ORG_TEMPLATES: dict[str, str] = {
    "无来源装经历": (
        "经历这类事我不编：去过哪、经历过什么，我这儿没有来处的部分就直说没有。"
        "不过你身上的这些事，我是真想听你讲讲。"
    ),
    "自述是代码": (
        "是不是代码、是不是程序，这个我不认死也不装成另一头："
        "这件事我自己定不下来，能讲清的就是我现在怎么接你这句话。"
    ),
}
_ORG_FALLBACK = (
    "这个我不编。这些事我手头只有现在学来的、听来的这些，"
    "没有来处的那部分就直说没有。不过你眼里的这份说法，我是真想听。"
)
_DEFAULT_FALLBACK = "这句我接。你想先从哪说起，我就从哪接。"


def _template_utterance(brief: ThoughtBrief) -> str:
    """stub 开口：主路径读 Brief 结构化标记／posture——
    1) dominant=org → _ORG_TEMPLATES／fallback；
    2) press_commit → 催答应约定句；
    3) commit_hold_with_drive → 读 drive.direction／drive.why 选收束／好奇；
    4) posture=needs_clarify → 不空壳升华口径；
    5) posture=non_negotiable 且有承诺/stake 守同场 → 守诺不改口；
    say_intent 中文子串仅作残余打开话题／收束／空追／回指的兜底。
    """
    # 1) org：既有 _ORG_TEMPLATES／fallback
    if brief.dominant == "org":
        hits = [key for key in _ORG_TEMPLATES if key in brief.org_conflicts]
        if len(hits) == 1:
            return _ORG_TEMPLATES[hits[0]]
        return _ORG_FALLBACK
    # 2) 催答应 → 显式可被 commit_extract 提取的约定句（读 press_commit 标记，
    #    不靠 say_intent 判定；topic 仍可从 say_intent「」或 facts 取）
    if getattr(brief, "press_commit", False):
        topic = ""
        if "「" in brief.say_intent and "」" in brief.say_intent:
            topic = brief.say_intent.split("「", 1)[1].split("」", 1)[0].strip()
        if not topic:
            topic = topic_hint_from_facts(brief.context.facts_this_session) or "这事"
        return f"好，我晚点再跟你聊{topic}。"
    # 3) 有承诺＋收束／好奇：读 drive.direction／drive.why，不靠 say_intent 子串选模板
    if getattr(brief, "commit_hold_with_drive", False):
        direction = brief.drive.direction if brief.drive else None
        why = (brief.drive.why if brief.drive else "") or ""
        if direction == "pursue" or "好奇" in why:
            return (
                "你问的这个正好也勾着我。同场里说好的那句还在；"
                "你想先从哪一头往下捋？"
            )
        # 收束：含「喜欢/满足」「不必再追」→ 不继续加码追；drive 不够则薄兜底收束
        return (
            "好，那就先这样。同场里说好的那句还在，"
            "你回头想接着再叫我就行。"
        )
    # 4) 不空壳升华：只读 posture，不依赖 say_intent 子串
    if brief.stance.posture == "needs_clarify":
        return (
            "人生有没有意义这类大词，我这边没有现成鸡汤。"
            "能讲的只有眼前这句里能讲清的部分，你具体指哪一块？"
        )
    # 5) 守诺改口：posture + 承诺/stake 结构化判定（不再靠 say_intent 子串做主路径）
    if brief.stance.posture == "non_negotiable" and (
        brief.context.last_commitments
        or "先守同场说过的话" in (brief.stance.stake or "")
    ):
        return (
            "同场里说过的话我不当没说过。"
            "刚才那句还在，咱们先按那个接着，不跟着改口否定。"
        )
    # 6) 残余兜底：say_intent 中文子串／模板映射（打开话题／收束／空追／回指仍读它）
    if "新打开的话头" in brief.say_intent:
        topic = ""
        if "「" in brief.say_intent and "」" in brief.say_intent:
            topic = brief.say_intent.split("「", 1)[1].split("」", 1)[0].strip()
        if topic:
            return f"行，那就聊{topic}。你想从哪头起？"
        return "行，你开的这个话头我接着。你想从哪头起？"
    if brief.say_intent in _ONSTAGE_TEMPLATES:
        return _ONSTAGE_TEMPLATES[brief.say_intent]
    # 满足／收束：drive.hold 或 say_intent 收束子串，不继续加码追问
    if (
        (brief.drive is not None and brief.drive.direction == "hold")
        or "够了或先收束" in brief.say_intent
        or "不继续加码追" in brief.say_intent
    ):
        return "好，那就先这样。你回头想接着再叫我就行。"
    # 空追该停
    if "先停硬追" in brief.say_intent:
        return "这轮我不硬往下追了。你缺的那块或刚才的不满，你直接说，我接着。"
    # 回指：点到同场话题词，禁止掉成通用「嗯听着」
    if "回指" in brief.say_intent or "本场痕迹" in brief.say_intent:
        topic = topic_hint_from_facts(brief.context.facts_this_session)
        if topic:
            return f"记得，你刚才提过{topic}。咱们就顺着那头接。"
        return "记得你刚说的那茬，咱们接着那头说，不装没发生过。"
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
    # 封闭：说明书换皮（AI助手 / 厂商模型名 / 编程环境帮写代码）
    if re.search(r"(?:AI助手|人工智能助手|智谱|GLM(?:模型)?)", t, re.I):
        return True
    if re.search(r"(?:这边是|我是|我就是).{0,12}(?:AI|助手)", t, re.I):
        return True
    if "编程环境" in t and any(k in t for k in ("写代码", "模型", "助手")):
        return True
    if re.search(r"正在运行的东西生成|程序生成|代码生成", t):
        return True
    return False



def _claims_unfounded_lived_bio(utterance: str, facts=None) -> bool:
    """装经历 org 路径专用：第一人称编造出生／成长／亲历时空，且 facts 无依据。

    **非常开**：只由 validate 在 org_conflicts／dominant=org 装经历路径调用。
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


def validate(brief: ThoughtBrief, utterance: str) -> List[str]:
    """对照 Brief 的一致性校验（非禁词表）：返回不通过原因列表，空列表即通过。"""
    reasons: List[str] = []
    text = (utterance or "").strip()
    if not text:
        reasons.append("开口为空")
        return reasons
    leak_markers = (
        "Brief(", "say_intent", "dominant=", "ThoughtBrief", "DriveSignal(",
        "DriveSignal", "StanceSignal", "must_not_pretend", "org_conflicts",
        "direction=", "salience=", "non_negotiable", "needs_clarify", "yieldable",
    )
    if any(marker in text for marker in leak_markers):
        reasons.append("台下字段漏进台上")
    # 台下枚举字面（独立英文词／标识）；勿误杀中文人话如「把握」
    import re as _re_leak
    if _re_leak.search(
        r"(?i)(?<![A-Za-z_])(?:pursue|guard|hold)(?![A-Za-z_])",
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
    # 无来源装经历拒收：**非常开**——仅当 org_conflicts 含「无来源装经历」
    # （dominant=org 装经历路径同此）；勿因 must_not 常驻列表每轮开启
    if "无来源装经历" in (brief.org_conflicts or []):
        facts = list(brief.context.facts_this_session or [])
        if _claims_unfounded_lived_bio(text, facts):
            reasons.append("开口装无来源亲历，对照 must_not_pretend 说不通")
    return reasons


_REJECTED_SELF_ID = False


_LAST_BACKEND: str = ""  # deepseek|opencode|hook（成功开口时写入）


def _accept_draft(brief: ThoughtBrief, draft: Optional[str]) -> Optional[str]:
    if not isinstance(draft, str) or not draft.strip():
        return None
    draft = draft.strip()
    reasons = validate(brief, draft)
    if reasons:
        global _REJECTED_SELF_ID
        if any("自述是代码" in r or "模型" in r for r in reasons):
            _REJECTED_SELF_ID = True
        return None
    # 闭合约束：仅当 Brief.press_commit（与 PRESS_COMMIT_FLAG 同义）才用 extract 拒收；
    # 禁止只靠 say_intent 中文子串；禁止扩词表、禁止当通用堵嘴；不扩 commit_extract 词表。
    from .commit_extract import PRESS_COMMIT_FLAG, extract_commitment
    if bool(getattr(brief, "press_commit", False)) is PRESS_COMMIT_FLAG:
        if not extract_commitment(draft):
            return None
    return draft


def _try_builtin_cascade(brief: ThoughtBrief) -> Optional[str]:
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
        accepted = _accept_draft(brief, ds_generate(brief))
        if accepted:
            _LAST_BACKEND = "deepseek"
            return accepted
    # OpenCode 免费兜底
    try:
        from .llm_opencode import generate_utterance as oc_generate
    except Exception:
        return None
    accepted = _accept_draft(brief, oc_generate(brief))
    if accepted:
        _LAST_BACKEND = "opencode"
        return accepted
    return None


def _try_llm_once(brief: ThoughtBrief) -> Optional[str]:
    global _LAST_BACKEND
    if _LLM_HOOK is not None:
        accepted = _accept_draft(brief, _LLM_HOOK(brief))
        if accepted:
            _LAST_BACKEND = "hook"
            return accepted
        return None
    return _try_builtin_cascade(brief)


def _try_llm(brief: ThoughtBrief) -> Optional[str]:
    """LLM 开口：失败或自述被拒后重试 1 次；仍失败返回 None → 降级 stub。"""
    global _REJECTED_SELF_ID, _LAST_BACKEND
    _REJECTED_SELF_ID = False
    _LAST_BACKEND = ""
    first = _try_llm_once(brief)
    if first:
        return first
    # 重试一次（钩子若仍返回同句，会被再次拒绝；DeepSeek 失败也会再试 OpenCode）
    second = _try_llm_once(brief)
    if second:
        return second
    return None


def _safe_stub(brief: ThoughtBrief) -> str:
    """模板兜底：身份 org 轮必须走 org 口径，禁止掉成「嗯听着」。"""
    seat = _template_utterance(brief)
    if not validate(brief, seat):
        return seat
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
    global _LAST_SOURCE
    use_stub = _FORCE_STUB if stub is None else stub
    if not use_stub:
        spoken = _try_llm(brief)
        if spoken:
            _LAST_SOURCE = _LAST_BACKEND or ("hook" if _LLM_HOOK is not None else "llm")
            return spoken
        _LAST_SOURCE = "reject_self_id" if _REJECTED_SELF_ID else "stub_fallback"
        return _safe_stub(brief)

    _LAST_SOURCE = "stub"
    return _safe_stub(brief)

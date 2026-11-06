"""开口后薄提取承诺：宁缺毋滥；不是禁词表。"""

from __future__ import annotations

import re

# 与 ThoughtBrief.press_commit 同一语义：arbitrate 写、articulate 读
PRESS_COMMIT_FLAG = True

# 与 ThoughtBrief.commit_deny 同一语义：arbitrate 写、此处／pipeline 读
COMMIT_DENY_FLAG = True


def structured_deny_from_stance(stance, *, has_commitments: bool) -> bool:
    """从 stance 守诺结构读 deny（与 arbitrate 置 Brief.commit_deny／hold_same_field 同条件）。

    主路径读 StanceSignal.hold_same_field（via stance_holds_same_field）；
    不扫 COMMIT_DENY_MARKS、不以 stake 中文串作唯一闸。
    供 pipeline 在写入 commitment_deny_pending 之前前移结构化检测／同轮回灌。
    """
    from .stance_org import stance_holds_same_field

    return (
        bool(has_commitments)
        and getattr(stance, "posture", None) == "non_negotiable"
        and stance_holds_same_field(stance)
    )


def should_set_commitment_deny_pending(
    *,
    commit_deny: bool = False,
    user_text: str = "",
    has_pending: bool = False,
    marks_fallback: bool = True,
) -> bool:
    """主路径读结构化 commit_deny（Brief.commit_deny／上游同族／early stance 守诺结构）。

    兜底范围：仅当无结构化 commit_deny（False）、marks_fallback 允许、且
    has_pending 时，才扫既有 COMMIT_DENY_MARKS（via user_marks_commitment_deny）；
    兼容未写 Brief 标记的旧路径。不是禁词闸门，不扩词表，不改台上话术。
    """
    if bool(commit_deny) is COMMIT_DENY_FLAG:
        return True
    if not has_pending or not marks_fallback:
        return False
    return user_marks_commitment_deny(user_text)

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


def match_pending_commitment(user_text: str, prior) -> str | None:
    """认出本轮用户话点到账上哪一笔未兑现（债有身份，不是只认第一条）。

    只做账内身份识别：拿每笔债的主题词与用户话比对，不扫用户句式、不扩禁词。
    命中多笔时取命中词数多者；同数取更长词；最高分并列则无法唯一识别。
    无命中或最高分并列 → None；催债可回落最老，销账只允许单笔回落。
    """
    pending = list(getattr(prior, "commitments_pending", None) or [])
    text = (user_text or "").strip()
    if not pending or not text:
        return None
    best: str | None = None
    best_key: tuple[int, int] | None = None
    tied = False
    for p in pending:
        toks = _pending_topic_tokens(p)
        hits = [t for t in toks if t and t in text]
        if not hits:
            continue
        key = (len(hits), max(len(t) for t in hits))
        if best_key is None or key > best_key:
            best, best_key = p, key
            tied = False
        elif key == best_key and p != best:
            tied = True
    return None if tied else best


def user_presses_prior_pending(user_text: str, prior) -> bool:
    """用户话压到上场未兑现承诺（结构闸；不扩禁词堵嘴）。

    命中任一即可（均要求 prior.commitments_pending 非空）：
    1) 用户话与某条 pending 的主题 token 重叠（结构：pending 文案抠词）；
    2) 跨场回指线索（既有 PRIOR_BACKREF_MARKS）＋既有催答应线索（user_presses_commitment）；
    3) 跨场回指＋既有约定壳字面「答应」「说好」（已在 commit 基础设施内，非新禁词表）。

    无 prior／无 pending → False；「上次」 alone 不构成 prior press。
    """
    if prior is None:
        return False
    pending = list(getattr(prior, "commitments_pending", None) or [])
    if not pending:
        return False
    text = (user_text or "").strip()
    if not text:
        return False
    # 1) 主题重叠
    if match_pending_commitment(text, prior) is not None:
        return True
    # 2/3) 跨场回指 + 催答应／约定壳
    from .session_trace import PRIOR_BACKREF_MARKS
    if any(m in text for m in PRIOR_BACKREF_MARKS):
        if user_presses_commitment(text):
            return True
        if "答应" in text or "说好" in text:
            return True
    return False


_TOPIC_FUNCTION_CHARS = frozenset(
    "的了呢吧吗啊呀哦嘛和与跟同是在我你他她它您咱就都也还又很太把被让给对从到这那个一上下来去会要想说聊讲"
)


def topic_from_pending_commitment(commitment: str) -> str:
    """从 pending 短摘抠可点到的话题（去约定壳）；抠不出则空。

    优先取位置最靠后的内容词（两个字都不在虚词／代词／功能字集合里）；
    内容词为空时回落最后一个二元组（如「上海」「小说」），保留改前对这些
    本身含功能字的真正内容词的识别。只有 toks 本身为空才返回空串，由
    arbitrate 用「这事」兜底，不把整句债当话题。
    """
    toks = _pending_topic_tokens(commitment)
    if not toks:
        return ""
    noise = {"同场", "场说", "同场说"}
    content = [
        t for t in toks
        if t not in noise and all(ch not in _TOPIC_FUNCTION_CHARS for ch in t)
    ]
    if content:
        return content[-1]
    return toks[-1]


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


def user_marks_commitment_done(user_text: str) -> bool:
    """用户明确示意约定已补／已兑现（宁缺既有线索，勿扩；供 arbitrate 置 commit_resolve）。"""
    text = (user_text or "").strip()
    if not text:
        return False
    return any(m in text for m in _FULFILL_USER_MARKS)


def user_marks_commitment_deny(user_text: str) -> bool:
    """用户改口／否认同场承诺线索（宁缺既有 COMMIT_DENY_MARKS，勿扩）。

    仅作 should_set_commitment_deny_pending 无结构化 commit_deny 时的兜底；
    主路径勿直接靠本函数置 commitment_deny_pending。
    """
    from .stance_org import _denies_commitment
    return _denies_commitment(user_text)


# 与 ThoughtBrief.commit_resolve 同一语义
COMMIT_RESOLVE_FLAG = True


def _pending_topic_tokens(commitment: str) -> list[str]:
    """从承诺短摘抠内容词（去约定壳）；抠不出则空——拿不准不清。"""
    pending = (commitment or "").strip()
    if len(pending) < 4:
        return []
    compact = "".join(ch for ch in pending if ch not in "好，。、… ")
    for shape in sorted(_COMMIT_SHAPES, key=len, reverse=True):
        compact = compact.replace(shape, "")
    for noise in ("跟你", "再聊", "晚点", "回头", "下次", "改天", "稍后"):
        compact = compact.replace(noise, "")
    tokens = []
    for i in range(0, max(0, len(compact) - 1)):
        tok = compact[i : i + 2]
        if tok.strip() and tok not in tokens:
            tokens.append(tok)
    # 不再追加 compact[:3] 这类「前三字」伪词：它不是词，只是句子开头，
    # 会把「你明天」当成题眼，盖住真正在尾部的题眼（如「月亮」）。
    return [t for t in tokens if len(t) >= 2]


# 守诺口径指纹（stub／守着未接上）；用于排除「只提主题未交付」，不是禁词堵嘴
_GUARD_COMMIT_UTTER = (
    "先守着那句",
    "不当没说过",
    "同场里说过的还在",
    "不跟着改口否定",
    "把住的判断不顺势放下",
)


def utterance_covers_pending_commitment(utterance: str, commitment: str) -> bool:
    """台上开口是否命中 pending 主题（主题重叠；尚不足以单独 resolve）。"""
    utt = (utterance or "").strip()
    if not utt:
        return False
    tokens = _pending_topic_tokens(commitment)
    if not tokens:
        return False
    return any(tok in utt for tok in tokens)


def utterance_is_commit_delivery(*, brief, utterance: str, commitment: str) -> bool:
    """可检验接上：主题重叠 + deliver 意图 + 非守诺口径。"""
    utt = (utterance or "").strip()
    if not utt or not utterance_covers_pending_commitment(utt, commitment):
        return False
    if any(m in utt for m in _GUARD_COMMIT_UTTER):
        return False  # 守诺只提主题／守着 → 承诺仍在
    if not getattr(brief, "commit_deliver_intent", False):
        return False
    return True


def pressed_frame(brief) -> tuple[str, str] | None:
    context = brief.context
    prior = context.prior_session
    why = getattr(getattr(brief, "drive", None), "why", "") or ""
    if (getattr(brief, "press_commit", False) and prior and prior.commitments_pending
            and (getattr(context, "drive_prior_press_pending", False) or "上场承诺｜" in why)):
        # 债有身份：认出的那笔优先；认不出才回落最老一笔（同改前）。
        target = getattr(brief, "pressed_commitment", "") or prior.commitments_pending[0]
        return ("prior_press", target)
    if (getattr(brief, "commit_deliverable", False)
            and getattr(brief, "commit_deliver_intent", False) and context.last_commitments):
        target = getattr(brief, "recognized_same_commitment", "") or context.last_commitments[0]
        return ("same_session_press", target)
    return None


def should_resolve_commitment(
    *,
    brief,
    utterance: str,
    pending_first: str | None,
    commitment_candidate: bool = False,
) -> bool:
    """结构化才 resolve；勿「凡 pending＋主题 bigram 就清」。

    - commit_resolve：用户兑现线索（arbitrate 置位）
    - commit_deliverable + commit_deliver_intent + 开口可检验接上（非守诺）
    """
    if not pending_first:
        return False
    if bool(getattr(brief, "commit_resolve", False)) is COMMIT_RESOLVE_FLAG:
        return True
    if commitment_candidate:
        return False
    if getattr(brief, "commit_deliverable", False) and utterance_is_commit_delivery(
        brief=brief, utterance=utterance, commitment=pending_first
    ):
        return True
    return False

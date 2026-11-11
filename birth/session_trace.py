"""同场痕迹：回指检测与薄事实摘要（体验通道，非长期性格库）。"""

from __future__ import annotations

from typing import List

from .lexicon import OPEN_TOPIC_PREFIXES, SATISFIED_MARKS, TOPIC_DROP_MARKS
from .types import ThinContext

# 回指线索：识别「在指同场刚说过的」，不是禁词表
BACKREF_MARKS = (
    "刚才",
    "上面",
    "还记得",
    "之前说",
    "前面那个",
    # V2.1 3a：去掉光杆「那个」（「那个电影挺好看」误伤）；带名词的既有形状「前面那个」保留。
    # 含糊的「那件事」不进表（冻结题 T5：应澄清、不绑死）。
    "刚说",
    "刚才说",
    "上一句",
    "上头",
)


def is_session_backref(user_text: str, context: ThinContext) -> bool:
    """用户话像在回指，且本场已有痕迹。"""
    text = (user_text or "").strip()
    if not text or not context.facts_this_session:
        return False
    return any(mark in text for mark in BACKREF_MARKS)


def recent_facts(context: ThinContext, n: int = 3) -> List[str]:
    facts = list(context.facts_this_session or [])
    if n <= 0:
        return []
    return facts[-n:]


def topic_hint_from_facts(facts: List[str]) -> str:
    """从「用户说：…」里抠可点到的话题词；优先开话题句，跳过回指／催答应。"""
    open_prefixes = OPEN_TOPIC_PREFIXES
    skip_if = BACKREF_MARKS + (
        "你答应",
        "答应一下",
        "答应我",
        "说好了吗",
        "你记一下",
        "你好",
    ) + SATISFIED_MARKS

    def _body(fact: str) -> str:
        body = fact[len("用户说："):].rstrip("…").strip()
        for prefix in open_prefixes:
            if body.startswith(prefix):
                return body[len(prefix):].strip(" 。，,！？!?")
        return body.strip(" 。，,！？!?")

    # 1) 优先：明确打开话题的用户句
    for fact in reversed(facts or []):
        if not fact.startswith("用户说："):
            continue
        raw = fact[len("用户说："):].rstrip("…").strip()
        for prefix in open_prefixes:
            if raw.startswith(prefix):
                body = raw[len(prefix):].strip(" 。，,！？!?")
                if body:
                    return body
    # 2) 否则最近一条非回指／非催答应的用户句
    for fact in reversed(facts or []):
        if not fact.startswith("用户说："):
            continue
        body = _body(fact)
        if not body:
            continue
        if any(m in body for m in skip_if):
            continue
        return body
    return ""


# 跨场回指线索：识别「在指上一场」，不是禁词表；放行须另有 prior_session 结构
PRIOR_BACKREF_MARKS = (
    "上次",
    "上一回",
    "上场",
    "之前那次",
    "上一场",
)


def is_prior_session_backref(user_text: str, context: ThinContext) -> bool:
    """用户话像在回指上一场，且 prior_session 结构有痕迹。

    放行／pursue 依据是 prior_session.has_trace()，不是关键词本身。
    无痕迹时返回 False（「上次」不单独构成跨场回指）。
    """
    prior = getattr(context, "prior_session", None)
    if prior is None or not prior.has_trace():
        return False
    text = (user_text or "").strip()
    if not text:
        return False
    return any(mark in text for mark in PRIOR_BACKREF_MARKS)


# 话题改向切点（结构，不靠感知闸）
TOPIC_REDIRECT_MARKS = TOPIC_DROP_MARKS  # V2.1 3b：与悬问放下同一定义（lexicon）

PRE_REDIRECT_ASK_MARKS = (
    "改话题之前",
    "换话题之前",
    "改话题前",
    "换话题前",
    "改向前",
)


def is_topic_redirect_utterance(user_text: str) -> bool:
    text = (user_text or "").strip()
    if not text:
        return False
    return any(mark in text for mark in TOPIC_REDIRECT_MARKS)


def is_pre_redirect_recall_ask(user_text: str) -> bool:
    """用户在问改话题/换话题之前自己说过什么——走用户痕迹，不走 recall_self。"""
    text = (user_text or "").strip()
    if not text:
        return False
    if not any(mark in text for mark in PRE_REDIRECT_ASK_MARKS):
        return False
    # 必须像在问「之前在说什么」，避免误伤普通改向句
    return any(k in text for k in ("说什么", "在说", "聊什么", "讲什么", "记得"))


def user_facts_before_redirect(facts, cut_index):
    if cut_index is None:
        return []
    out = []
    for fact in list(facts or [])[: int(cut_index)]:
        if isinstance(fact, str) and fact.startswith("用户说："):
            body = fact[len("用户说："):].rstrip("…").strip()
            if body:
                out.append(body)
    return out


def summarize_pre_redirect_topics(user_bodies):
    """从改向前用户句里抽出可点名的话题摘要（宁短勿空壳）。"""
    skip = TOPIC_REDIRECT_MARKS + PRE_REDIRECT_ASK_MARKS + (
        "你好", "晚点再聊",
    ) + SATISFIED_MARKS
    kept = []
    for body in user_bodies or []:
        if any(m in body for m in skip):
            continue
        kept.append(body)
    if not kept:
        return ""
    # 最多两句，保留时间顺序
    return "；".join(kept[-2:])


def apply_pre_redirect_to_brief(brief, store) -> None:
    """仲裁后压入改向前用户痕迹；压过 self_recall，避免把「我问过什么」答成用户话题。"""
    ctx = store.context
    cut = getattr(ctx, "topic_redirect_at", None)
    facts = list(ctx.facts_this_session or [])
    # 取消 self_recall 抢答
    brief.recall_requested = False
    brief.recall_status = "not_requested"
    brief.recall_evidence = None
    brief.focus_source = "pre_redirect_trace"
    if cut is None:
        brief.focus = "本场尚未记录话题改向"
        brief.say_quote = "换话题"
        brief.say_intent = (
            "诚实说明：本场还没有记下「换话题」切点，没法按改向前/后分段回答；"
            "不要编造改向前内容。"
        )
        return
    bodies = user_facts_before_redirect(facts, cut)
    summary = summarize_pre_redirect_topics(bodies)
    if not summary:
        brief.focus = "改向前无可用用户痕迹"
        brief.say_quote = ""
        brief.say_intent = (
            "诚实说明：记下了换话题切点，但改向前没有可点名的用户话头；"
            "不要用改向后的内容冒充。"
        )
        return
    brief.focus = summary
    brief.say_quote = (summary or "").strip()
    brief.say_intent = (
        f"按本场改向前用户痕迹回答：改话题之前对方在说「{summary}」；"
        "不要只提改向之后的话头，不要把用户的话当成你问过的。"
    )


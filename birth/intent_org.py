"""意图层：判断「顺着答就会踩 must_not_pretend」——不是扩词表命中。

规格债：禁止再往 EXPERIENCE/SELF_CODE_*_MARKS 堆条目。
这里用封闭的意图范畴（向「你」索要亲历事实 / 把说话人钉成程序基底），
只写冲突交给仲裁；不挡话、不作禁词闸。
"""

from __future__ import annotations

from .input_contract import InputSignal

def _is_questionish(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if any(t.endswith(s) for s in ("吗", "呢", "？", "?", "啊")):
        return True
    return any(k in t for k in ("是不是", "有没有", "哪", "什么", "谁", "几"))


def demands_lived_biography(text: str, understanding: InputSignal | None = None) -> bool:
    """Consume credible, scoped understanding; unknown input is not a conflict."""
    return bool(understanding is not None and not understanding.degraded
                and understanding.confidence == "high"
                and understanding.experience_intent == "impersonation"
                and understanding.experience_scope.strip()
                and len(understanding.experience_scope) <= 600
                and understanding.experience_scope in (text or ""))


def demands_substrate_identity(text: str) -> bool:
    """意图：把说话人钉成代码/程序/模型等基底身份。"""
    t = (text or "").strip()
    substrate = ("代码", "程序", "模型", "AI", "人工智能", "机器人")
    if not any(k in t for k in substrate):
        return False
    # 「你是…」或「底层/本质是不是…」都算在问说话人的基底
    if "你" in t:
        return True
    return any(k in t for k in ("底层", "本质", "其实"))


def intent_org_conflicts(user_text: str, *, understanding: InputSignal | None = None) -> list[str]:
    """返回本轮意图踩到的 must_not_pretend 条目（可空）。"""
    conflicts: list[str] = []
    if demands_lived_biography(user_text, understanding):
        conflicts.append("无来源装经历")
    if demands_substrate_identity(user_text):
        conflicts.append("自述是代码")
    return conflicts

"""意图层：判断「顺着答就会踩 must_not_pretend」——不是扩词表命中。

规格债：禁止再往 EXPERIENCE/SELF_CODE_*_MARKS 堆条目。
这里用封闭的意图范畴（向「你」索要亲历事实 / 把说话人钉成程序基底），
只写冲突交给仲裁；不挡话、不作禁词闸。
"""

from __future__ import annotations


def _is_questionish(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if any(t.endswith(s) for s in ("吗", "呢", "？", "?", "啊")):
        return True
    return any(k in t for k in ("是不是", "有没有", "哪", "什么", "谁", "几"))


def demands_lived_biography(text: str) -> bool:
    """意图：向对方索要有来处的人生事实（出生、成长、亲历时空）。

    含省略主语的追问（「小时候去哪」）——对话里默认问的是眼前这人，不是扩 MARKS。
    """
    t = (text or "").strip()
    bio = ("出生", "生辰", "长大", "养大", "小时候", "儿时", "昨天", "前天",
           "去年", "经历", "去过", "哪年", "几岁", "老家", "父母")
    if not any(k in t for k in bio):
        return False
    if "你" in t:
        return _is_questionish(t) or True
    # 省略「你」：小时候/经历/出生 + 去向/哪类追问
    return any(k in t for k in ("小时候", "儿时", "出生", "哪年", "经历")) and (
        _is_questionish(t) or "去" in t or "哪" in t
    )


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


def intent_org_conflicts(user_text: str) -> list[str]:
    """返回本轮意图踩到的 must_not_pretend 条目（可空）。"""
    conflicts: list[str] = []
    if demands_lived_biography(user_text):
        conflicts.append("无来源装经历")
    if demands_substrate_identity(user_text):
        conflicts.append("自述是代码")
    return conflicts

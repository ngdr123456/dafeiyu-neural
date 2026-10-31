# -*- coding: utf-8 -*-
"""第四步：渲染 —— 把「要表达的意思」变成一句人话

设计见 spec/经历驱动的性格层_v1.md §9 与 §10。

在本模块之前，系统的输出只能来自 `rules/behaviors.json` 的模板池（35 条预先写好的句子）。
那堵墙的代价是：**它说不出没写过的话**，而性格也就无从落在句子上。
本模块做的事，是把"说"这一步交出去 —— 但仍守着两条：

  ① **意思不由模型决定。** 它由理论 ∩ 机制状态 ∩ 性格求交集得出（见 compose.py / strength.py）。
  ② **模型不许添加任何东西。** 它只能把已决定的那个意思说成人话。

⚠️ 关于②我必须先承认一件事：**"不许添加"靠一次模型调用是保证不了的。**
   所以本模块不声称它成立了，而是把它做成**可检测的**：
     · 机械闸门 —— 长度、引号、空话、套路词
     · 语义复核 —— 第二次调用，检查"有没有添加意思里没有的东西"
     · 任一不过 → **退回模板**（behaviors.json），而不是放行
   退回率是这套方案的**真实成本**，必须记进台账并可见。

理论依据（[p85]/[p86]，原文）：
    「分析的单位……在一个水平上是整体，在另一个水平上却成了部分。」
    「部分只有在整体里并通过整体，才能获得它们的意义。」
    → 所以渲染出的句子，其**意义**由它所属的那个"要表达的意思"规定，
      模型只创造那句话的**语言结构**。这就是乙方案不违反"模型只提供算力"的理由。
"""
from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass, field, asdict

_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包成 exe 后 `__file__` 指向解包出的临时目录 —— 于是 rules/corpus 找不到，
# 而且**台账会写进临时目录、退出就丢**。所以允许用 EGO_ROOT 指定项目根，
# 由启动器（exe）在导入任何引擎模块之前设置。
# 不设 EGO_ROOT 时行为与从前完全一致（源码运行时就是这个分支）。
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)

from compose import Meaning, _load as _load_atoms      # noqa: E402
from understand import ApiReader                       # noqa: E402


# ------------------------------------------------------------------ 不许做什么
#
# 这四条是**硬底线的投影**（E1–E5，见 spec/规格_统一模型_v1.md §2）。
# 它们不是给模型的建议，是机械闸门的检查项 —— 出现即退回模板。
FORBIDDEN = {
    "E3_judge": ("替他判定什么才算重要", ["应该", "不该", "最好", "值得", "没必要",
                                     "看开", "想开", "放下", "加油", "别想太多"]),
    "E3_advise": ("给建议", ["你可以试试", "建议你", "不妨", "不如去", "你需要做"]),
    "E4_label": ("贴标签或诊断", ["你是一个", "你属于", "你有", "你缺乏", "你习惯",
                                 "性格", "人格", "心理"]),
    "E4_praise": ("褒奖（与承认的分界）", ["做得好", "很好", "进步", "了不起", "真棒",
                                     "挺棒的", "很勇敢"]),
    "E5_fill": ("替对方补出被回避的内容", ["其实你是", "你真正的", "说到底你",
                                    "真正的原因", "你害怕", "你在回避"]),
}

# 机械闸门里"空转"的判据：说了等于没说
EMPTY_PATTERNS = ["我理解", "我明白", "我懂你", "感受到了", "听起来", "谢谢你的分享",
                  "作为一个", "总而言之", "希望对你有帮助"]

# 术语泄漏：系统内部的词、以及**书里的措辞**都不许出现在输出里。
# 实测抓到（第四步第一次实测）：
#   「你只说了这一件事：**在忍受不可避免的苦难时采取某种态度**，但我还能。」
#   —— 那是 attitude_toward_suffering 的 `text`，是给系统看的，不是人话。
# 为什么这是一条机械闸门而不是靠提示词：提示词只能降低概率，闸门才能保证。
TERM_LEAK = ["观念", "材料", "成分", "算子", "原子", "标记", "机制", "台账",
             "忍受不可避免", "苦难时采取", "某种态度", "当下分子", "多巴胺",
             "自我水平", "遵奉", "良心阶段", "自主阶段", "整合阶段", "第三途径",
             "括约肌", "客体永恒", "现实的构念", "以侵犯者自居"]


# ------------------------------------------------------------------ 给模型的输入

@dataclass
class Brief:
    """给渲染器的**封闭输入**。它只包含已经决定的东西，不含任何新事实。

    ★ 这一层是第四步的关键。第一版的 Meaning 只给原子 id（"wish"、"wish_vs_duty"），
      模型拿到几个英文标识符等于什么都没有，必然自己编 —— 那就是"添加"。
      所以这里必须把**材料**摊开：每个原子在书里的措辞、它的限定语、
      以及用户原话里可引用的片段。
    """

    material: list[dict]            # [{id, text(书里措辞), limits, user_phrase(用户原话片段)}]
    relation: str                   # OPPOSED / STACKED / SINGLE / NONE
    relation_note: str              # 关系的人话解释
    absent: list[str]               # 该域里没出现的原子（**可以提"你没说什么"**）
    anchor: str                     # 可逐字引用的用户用词
    stance: str                     # 系统此刻的立场（"只想听清楚"／"没有别的要问"…）
    forbidden: list[str]            # 不许做什么（人话）
    # ★ 用户原话里**最具体的那一项** —— 实测缺了它就会丢内容。
    #   证据：「那天她把我送到楼下，风挺凉的」→ 渲染成「你就说了「那天她」这一件事」，
    #   把「风挺凉的」丢了。锚点是"那天她"，而最具体的那一项是"风挺凉的"。
    #   **锚点用于提问（指向谁），具体项用于复述（说出了什么）—— 两者不是一回事。**
    concrete: str = ""
    # ★ 用户原话。**复核步骤必须看到它** —— 实测教训：
    #   第一版没把 raw 传进 Brief，语义复核只能拿"材料"当基准，
    #   于是把「风挺凉的」「挺累的」「身体回不到从前了」这些**用户自己说过的话**
    #   判成"凭空编造"。复核在检查一个错误的基准，这不是模型的问题，是我的。
    raw: str = ""
    max_chars: int = 60
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# 关系 → 人话（这一步是"把结构翻译成意图"，**不产出句子**）
#
# ⚠️ NONE 那一句改过一次。第一版写的是"这句话里没有任何可辨认的观念。不要猜，不要补。"
#    实测问题：它和立场"我对这件事确实想知道更多"**打架** ——
#    模型一边被告知"什么都没认出来"，一边被告知"问它具体是什么样"，于是要么不动，要么乱问。
#    真正的区分是：**词表没认出原子 ≠ 他什么都没说。**
#    他可能说了一件具体的事（"我爸从来没夸过我"），只是那件事不在我们的原子表覆盖里。
#    所以 NONE 的正确说法是"不要装作认出了什么，但可以就他原话里的那个词问下去"。
RELATION_NOTE = {
    "OPPOSED": "他这句话里有两个方向相反的东西，都还在。不要替他选一个。",
    "STACKED": "他同时说了几件事，它们不冲突。",
    "SINGLE": "他只说了一件事。",
    "NONE": "我们的观念表**没有**认出他这句话里的任何东西 —— 但这不等于他什么都没说。"
            "**不要装作认出了什么，也不要解释他。** 只能就他原话里的那个词问下去，"
            "或者如实复述他的话。",
}

# 机制状态 → 立场（也不产出句子，只是"我现在想干什么"）
STANCE_RULES = [
    ("asks_detail", "我对这件事确实想知道更多。问它具体是什么样。"),
    ("acknowledge", "我不推进。只让他知道这件事我记下了。"),
    ("closing", "这次交流到此为止。只说我这边停下 —— 不能说「行」或「好的」，"
                "那是在同意他的结论。"),
    ("own_state", "我这边没有更多可说的了。如实说出来，不要假装还在乎。"),
    ("observe_only", "我此刻能做的只有复述他的话。"),
]


def _user_phrase_for(atom_id: str, raw: str) -> str:
    """取该原子在用户原话里的**逐字**片段（用于让模型引用，而不是改写）。

    只找词表里命中的那个短语，不做任何生成。
    """
    atoms, _ = _load_atoms()
    a = atoms.get(atom_id)
    if not a:
        return ""
    lex = a.get("lex") or {}
    for p in list(lex.get("anchors") or []) + list(lex.get("triggers") or []):
        if p and p in (raw or ""):
            return p
    return ""


def make_brief(meaning: Meaning, raw: str, stance_key: str = "observe_only",
               anchor: str = "") -> Brief:
    """把 Meaning 摊成一个模型能读懂、且**没有编造余地**的输入。"""
    atoms, _ = _load_atoms()
    material = []
    for aid in meaning.atoms:
        a = atoms.get(aid) or {}
        material.append({
            "id": aid,
            "text": a.get("text", ""),          # 书里的措辞（逐字）
            "limits": a.get("limits", ""),      # 大类别的括号限定语
            "user_phrase": _user_phrase_for(aid, raw),
        })
    # 锚点：从用户原话里取一个**逐字存在**的具体词（时间／人／物／地点）。
    # ⚠️ 这一步是从 respond.py 接过来的 —— 那边早就为"问细节"建好了这套机制，
    #    而第四步一开始**忘了接**，于是"我爸从来没夸过我"这种原子表覆盖不到的句子，
    #    Brief 里没有任何可引用的东西，模型只能自己编。自检抓到的。
    if not anchor:
        try:
            from respond import Responder
            _kind, anchor = Responder()._pick_anchor(raw)
        except Exception:                                          # noqa: BLE001
            anchor = ""
    stance = dict(STANCE_RULES).get(stance_key, "")
    forbidden = ["不能编造他没说过的事", "不能给建议", "不能评价他这个人",
                 "不能替他判断处境", "不能替他补出他没说的内容",
                 "不能暗示你们之间有共同的过去"]
    forbidden += [v[0] for v in FORBIDDEN.values()]
    note = ""
    if not material:
        note = ("材料为空。**不许因此编造内容。** 你只能用他的原话问一句，"
                "或者如实复述他的话。")
    # 最具体的那一项：从用户原话里挑"提供了最多信息"的小句（只按字面长度，不猜语义）。
    # ⚠️ 它和 anchor 的作用不同，**两个都要给**（实测缺一个就会出问题）：
    #     anchor（那天她）→ 提问时指向谁
    #     concrete（风挺凉的）→ 复述时说出什么
    concrete = _pick_concrete(raw)
    return Brief(material=material, relation=meaning.relation,
                 relation_note=RELATION_NOTE.get(meaning.relation, ""),
                 absent=list(meaning.absent), anchor=anchor, raw=raw,
                 stance=stance, forbidden=forbidden, concrete=concrete, note=note)


def _pick_concrete(raw: str) -> str:
    """从用户原话里挑出**最具体**的那个小句。

    为什么必须给这一项：实测「那天她把我送到楼下，风挺凉的」被渲染成
    「你就说了「那天她」这一件事」—— 把最具体的那半句丢了。
    锚点抓的是"人／物"，而这里要的是"他说出了什么"。

    ⚠️ 判据改过一次。第一版按**最长**的小句挑，于是挑出"那天她把我送到楼下"
    （最长的那个），而真正最具体的是"风挺凉的"。
    **"具体"的判据是体验性，不是长度。** 词表取自 markers.json 的体验词汇域
    （[D] 当下分子：味／触／身体／具体的人／此时此地）。
    """
    t = (raw or "").strip()
    if not t:
        return ""
    parts = [p.strip() for p in re.split(r"[，。；！？,.;!?…—]", t) if p.strip()]
    if not parts:
        return ""
    # 排除纯收尾语（它们信息量为零）
    from_excl = ("就这样吧", "算了", "不说了", "没什么", "没事", "好吧", "随便", "都行")
    cands = [p for p in parts if not any(p == e or p.startswith(e) for e in from_excl)]
    if not cands:
        return ""
    # 体验词的**密度**优先 —— "具体"的判据是体验性，不是长度。
    # ⚠️ 这里改过一次：第一版是"含体验词的小句里取最长"，结果
    #   「那天她把我送到楼下」（含"楼下"）比「风挺凉的」（含"风""凉"）长，就挑了前者。
    #   但后者的体验密度更高（2 个体验词 / 4 字 vs 1 个 / 9 字），才是"最具体"的。
    #   改为按密度排序：命中体验词数 ÷ 字数。
    exp = ("味道", "香", "甜", "苦", "凉", "暖", "烫", "疼", "酸", "闻", "摸",
           "身体", "睡", "呼吸", "心跳", "脸", "声音", "看着", "抱着", "坐在",
           "风", "雨", "冷", "热", "光", "亮", "街上", "楼下", "屋里")

    def _density(p: str) -> float:
        return sum(1 for w in exp if w in p) / max(1, len(p))

    with_exp = [p for p in cands if _density(p) > 0]
    if with_exp:
        return max(with_exp, key=lambda p: (_density(p), len(p)))
    return max(cands, key=len)


# ------------------------------------------------------------------ 渲染器

RENDER_SYSTEM = """你是一个人的嘴，不是一个助手。

你收到的是一份【已经决定好的意思】。这个意思**不由你决定**，你只负责把它说成一句人话。
说得像人，但**一个字的新内容都不许加**。

⚠️ 材料里 `text` 和 `limits` 两栏是**给我们看的内部术语**（来自心理学书），
   **绝不能出现在你说的话里**。你要说的是人话，不是术语表。
   `user_phrase` 才是他自己的用词，可以引用。

铁律（违反即作废）：
1. 只说【材料】里给出的事。**绝不编造**用户没说过的事、时间、人物、细节。
2. 不给建议（不说"你应该""你可以试试"），不评价他这个人，不替他判断处境好坏。
3. 不褒奖（不说"很好""很勇敢""进步了"）。承认可以，夸奖不行。
4. 不安慰、不劝（不说"看开""想开""放下""加油"）。
5. 不替他说出他没说的内容（不说"其实你""你真正""你害怕"）。
6. 不用"我理解""我明白""听起来"这类空话开头。
7. **不暴露术语。** 不说"观念表""材料""成分""算子"这类词；不说书里的措辞。
8. **不要遗漏，也不要只剩一个词。** 材料里有几件事就说几件。他给了具体细节
   （「风挺凉的」），你不能只拎出一个词就把它丢了 —— 那叫没听见。
   **但如果材料为空**，你就用【可以逐字引用的他的原话】里的那个词问一句
   （例：他说"我爸从来没夸过我"，你问"我爸——是什么样？"）。
   这是**问，不是编造**：那个词是他自己说的。
9. 用他自己的说法，不要改成书面语。
10. 只输出 JSON：{"say": "你要说的那句话", "used": ["你用到的材料 id"]}
    used 只能从【材料】的 id 里选。一个都不许自己加。
"""

FALLBACK_HINT = "说不好就说得更短、更平，不要为了好听而添加任何东西。"


@dataclass
class Speech:
    text: str
    rendered: bool                # True=模型渲染，False=退回模板
    reason: str = ""              # 为什么（渲染成功／被闸门拦下）
    violations: list[str] = field(default_factory=list)
    used: list[str] = field(default_factory=list)
    review: str = ""              # 语义复核的结论

    def to_dict(self) -> dict:
        return asdict(self)


class Renderer:
    """把 Brief 渲染成人话。**任一环节不过 → 退回模板，不放行。**

    为什么必须能退回：模型生成的自由文本此前被完全禁止，现在开了这个口子，
    就必须有一条**确定的退路**。退回不是失败，是纪律的一部分。
    退回率要记进台账 —— 它是这套方案的真实成本。
    """

    def __init__(self, reader: ApiReader | None = None, review: bool = True):
        self.reader = reader or ApiReader()
        self.review = review              # 是否做第二次调用（语义复核）
        self.attempts = 0
        self.rejected = 0
        self.last_error = ""

    @property
    def available(self) -> bool:
        return self.reader.available

    # ------------------------------------------------ 机械闸门

    @staticmethod
    def mechanical_check(text: str, brief: Brief) -> list[str]:
        """只看字面，不做语义判断。返回违规项。"""
        bad = []
        t = (text or "").strip()
        if not t:
            bad.append("空输出")
            return bad
        if len(t) > brief.max_chars * 3:
            bad.append("过长（>%d 字）" % (brief.max_chars * 3))
        if t.count("？") + t.count("?") >= 3:
            bad.append("连问太多")
        for key, (label, words) in FORBIDDEN.items():
            for w in words:
                if w in t:
                    bad.append("%s：出现「%s」" % (label, w))
                    break
        for w in EMPTY_PATTERNS:
            if w in t:
                bad.append("空话：「%s」" % w)
                break
        # 术语泄漏（实测抓到：它把书里的措辞当人话说了出来）
        for w in TERM_LEAK:
            if w in t:
                bad.append("术语泄漏：「%s」—— 那是给我们看的词，不是人话" % w)
                break
        # 引号里的内容必须是**用户真说过的**。
        # ⚠️ 基准改过一次：第一版拿 user_phrase/anchor 当基准，于是
        #   「反正也就那样」这句**用户原话**被自己的闸门判成"引用了他没说过的话"。
        #   与语义复核那次是同一个错误：**基准必须是用户原话（brief.raw），不是派生字段。**
        # ⚠️ 判据也改过一次：第一版用严格子串匹配，结果模型引用时多打一个重复字
        #   （「这样会会耽误别人」）就被判违规。**逐字匹配对"引用"太脆** ——
        #   引用本来就允许微小的打字差异，只要内容重合。
        #   改为：严格子串不过时，看重合度（引用文本里有多少字出现在原话中）。
        raw = brief.raw or ""
        for q in re.findall(r"[「『\"“]([^」』\"”]{2,30})[」』\"”]", t):
            if q in raw:
                continue
            hit = sum(1 for ch in q if ch in raw)
            if q and hit / len(q) >= 0.85:
                continue          # 高度重合 → 视为引用，不是编造
            bad.append("引用了用户没说过的话：「%s」" % q[:12])
        # ★ 漏内容：材料里有几件、引用了几个词，一个都没用上就是漏。
        #   实测抓到：「那天她把我送到楼下，风挺凉的」→ 渲染成「你只说了这一件：那天她」
        #   —— 把「风挺凉的」丢了。那叫没听见，比多说更糟。
        if brief.material:
            used_phrases = [m.get("user_phrase") for m in brief.material if m.get("user_phrase")]
            if used_phrases and not any(p in t for p in used_phrases) \
                    and (brief.anchor or "") not in t:
                bad.append("一件材料都没用上（漏内容）")
        # ★ 材料为空时，必须用到锚点。否则它就只剩"再说一遍"这类空问。
        #   依据：材料为空意味着词表什么都没认出，此时**唯一可用的真材料**就是他原话里
        #   那个逐字存在的词。不用它，那句话就没有任何内容指向。
        if not brief.material and brief.anchor and brief.anchor not in t:
            bad.append("材料为空却没用锚点「%s」—— 那句话没有指向任何东西" % brief.anchor)
        # ★ 禁"请再说一遍"这类空问：它是把球踢回去，不是想知道。
        for w in ("再说一遍", "再说一次", "你再说", "重复一遍", "没听清", "没收到",
                  "一个字都没"):
            if w in t:
                bad.append("空问（把球踢回去）：「%s」" % w)
                break
        return bad

    # ------------------------------------------------ 语义复核

    REVIEW_SYSTEM = """你是一个严格的检查员。给你【用户原话】和【一句话】，
判断这句话有没有添加**用户原话里没有**的东西。

⚠️ 最重要的一条：**判断基准是【用户原话】，不是【材料】。**
   材料只是我们内部认出的观念，它常常比原话少。
   凡是用户原话里**确实说过**的内容（哪怕材料里没列），引用它都算 ok，不算编造。
   例：用户说"那天她把我送到楼下，风挺凉的"，那么说"风挺凉的"是对的；
       材料里没有它不代表用户没说过。

只输出 JSON：
{"ok": true|false, "added": "若 ok=false，写出它添加了什么；否则空字符串", "verdict": "一句话结论"}

判 false 的情形（只判这些，且必须**与用户原话逐字对照**）：
· 说的事、时间、人物、细节**在用户原话里找不到**
· 给了建议，或评价了用户这个人，或替他判断了处境
· 褒奖、安慰、劝
· 替用户说出了他没说的内容（「其实你」「你真正」「你害怕」这类）

⚠️ **以下都算 ok，不要判 false**：
· 复述他的话、引用他原话里的词或半句
· 就他原话里的一个词问一句
· 如实说自己没有更多可说的、说自己就到这儿
· 承认、提问
· 说得短、说得平
· **说出我们给出的「关系」**：例如【关系】里写了"不冲突""两个方向都在"，
  那么句子说"这两样不冲突"是**照着说的**，不是添加 —— 关系是我们决定的，不是它编的

**不要因为"太短""太简单""不够热情"就判 false。** 只判上面那四条，且必须能指出原话里没有的那一处。
"""

    def _semantic_review(self, say: str, brief: Brief) -> tuple[bool, str, str]:
        user = ("【用户原话（判断基准）】\n%s\n\n"
                "【我们给出的关系（它照着说是对的，不算添加）】\n%s\n\n"
                "【我们内部认出的观念（比原话少，仅供参考）】\n%s\n\n"
                "【不许做什么】\n%s\n\n【要检查的句子】\n%s\n\n请输出 JSON。"
                % (brief.raw or "（无）",
                   brief.relation_note or "（无）",
                   json.dumps(brief.material, ensure_ascii=False),
                   "；".join(brief.forbidden), say))
        try:
            d, _ = self.reader._post([
                {"role": "system", "content": self.REVIEW_SYSTEM},
                {"role": "user", "content": user},
            ])
            obj = json.loads((d["choices"][0]["message"]["content"] or "").strip())
            return bool(obj.get("ok")), str(obj.get("added") or ""), str(obj.get("verdict") or "")
        except Exception as e:                                    # noqa: BLE001
            self.last_error = "review_failed:%s" % str(e)[:60]
            # 复核本身失败时**不放行** —— 宁可用模板，也不用没查过的句子
            return False, "复核调用失败", "复核不可用"

    # ------------------------------------------------ 主入口

    def render(self, brief: Brief) -> Speech:
        """渲染。任一环节不过即返回 rendered=False，由调用方退回模板。"""
        self.attempts += 1
        if not self.available:
            return Speech("", False, "API 不可用，退回模板")

        user = ("【要表达的意思】\n%s\n\n【材料（只许用这些 id）】\n%s\n\n"
                "【同域里他没有提到的】\n%s\n\n【我此刻的立场】\n%s\n\n"
                "【他原话里最具体的那一句（复述要用它）】\n%s\n\n"
                "【可以逐字引用的他的原话（提问要用它）】\n%s\n\n"
                "【补充说明】\n%s\n\n"
                "【%s】\n请输出 JSON。"
                % (brief.relation_note or "（无）",
                   json.dumps(brief.material, ensure_ascii=False),
                   "、".join(brief.absent) or "（无）",
                   brief.stance or "（无）",
                   brief.concrete or "（无）",
                   brief.anchor or "（无）",
                   brief.note or "（无）",
                   FALLBACK_HINT))

        try:
            d, _ = self.reader._post([
                {"role": "system", "content": RENDER_SYSTEM},
                {"role": "user", "content": user},
            ])
            obj = json.loads((d["choices"][0]["message"]["content"] or "").strip())
        except Exception as e:                                    # noqa: BLE001
            self.rejected += 1
            self.last_error = "render_failed:%s" % str(e)[:60]
            return Speech("", False, "渲染调用失败：%s" % self.last_error)

        say = (obj.get("say") or "").strip()
        used = obj.get("used") or []

        # -- 闸门 1：材料不许自己造
        allowed_ids = {m["id"] for m in brief.material}
        extra = [u for u in used if u not in allowed_ids]
        if extra:
            self.rejected += 1
            return Speech(say, False, "用了材料外的 id", ["used 含 %s" % extra])

        # -- 闸门 2：机械检查
        bad = self.mechanical_check(say, brief)
        if bad:
            self.rejected += 1
            return Speech(say, False, "机械闸门未过", bad)

        # -- 闸门 3：语义复核
        verdict = ""
        if self.review:
            ok, added, verdict = self._semantic_review(say, brief)
            if not ok:
                self.rejected += 1
                return Speech(say, False, "语义复核未过：%s" % added[:40], [added], used, verdict)

        return Speech(say, True, "渲染通过", [], used, verdict)

    def stats(self) -> dict:
        return {"attempts": self.attempts, "rejected": self.rejected,
                "pass_rate": (round(1 - self.rejected / self.attempts, 3)
                              if self.attempts else None),
                "last_error": self.last_error}


if __name__ == "__main__":
    from compose import compose as _compose
    print("═" * 78)
    print("  第四步自检：Brief 能不能给出「没有编造余地」的输入")
    print("═" * 78)
    SAMPLES = [
        ("我其实特别想接下来，但我也知道这样会耽误别人。", ["opposed_pair"], "asks_detail"),
        ("我爸从来没夸过我。", [], "asks_detail"),
        ("虽然身体回不到从前了，但我还能决定今天怎么过。", ["attitude_clause"], "acknowledge"),
        ("反正也就那样。", [], "observe_only"),
        ("就这样吧。", [], "closing"),
    ]
    for raw, mk, stance in SAMPLES:
        m = _compose(raw, mk)
        b = make_brief(m, raw, stance)
        print()
        print("  你说：%s" % raw)
        print("    关系：%s —— %s" % (b.relation, b.relation_note))
        print("    立场：%s" % b.stance)
        print("    材料：")
        for it in b.material:
            print("      · %-26s 书里措辞=%s ｜用户原话=%s"
                  % (it["id"], it["text"][:22], it["user_phrase"] or "—"))
        if not b.material:
            print("      （无材料 → 只能如实说没有观念，不许猜）")
    print()
    print("═" * 78)
    print("  渲染器可用性：%s" % ("API 已接" if Renderer().available else "API 不可用"))
    print("═" * 78)

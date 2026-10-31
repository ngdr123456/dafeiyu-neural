# -*- coding: utf-8 -*-
"""关联矩阵：从对方的反应里，学会描述**自己**

═══════════════════════════════════════════════════════════════════════════
理论依据（都是原文，不是我的推断）

[Mead] **"当我们学会了用别人的观点来描述我们自己时，心理的意识就产生了。"**
    —— 记忆锚点：「社会行为主义者；反对鲍德温的模仿本能说」。
    ★ 这一句决定了本模块学的是**什么**：不是"该说什么"，不是"对方是什么人"，
      而是**从对方的反应里学会看自己**。

[Baldwin] 三阶段：①把人和其他物体分开；②把自己看作许多人当中的一员，
    但不能从别人身上觉察特殊感受；③**发现别人也具有他在自己身上觉察的那些感受**。
    ★ 阶段③就是本模块与性格核要走到的地方。

[Sullivan] **"婴儿的早期学习是受焦虑的梯度指导的；他趋向焦虑的减少而回避焦虑的增强。"**
    ★ 这是"怎么学"的机制 —— 趋避，不是奖励。

═══════════════════════════════════════════════════════════════════════════
两条硬约束（用户 2024 确认）

① **不把「让对方继续说」当奖赏或目标。**
   理由：[Baldwin] 警告「年幼儿童……模仿强者并欺侮弱者」——
   一个只靠趋避、没有阶段③的系统**一定会学成迎合**，因为迎合是让对话继续的最廉价手段。
   所以本模块**只记录反应模式**（他回避了什么、什么时候说得更多、什么时候收尾），
   **不做加权优化、不打分、不排序**。它产出的是**描述**，不是策略。

② **可以注意到关于用户内在的东西，但不能说出来。**
   理由：说出来就是替对方补出被回避的内容，违反 E5。
   注意到 → 用于调整自己（少往那儿问）；说出来 → 越界。
   所以本模块只存"注意到的事"，它们**不进入输出**；能进入输出的是关于**自己**的描述。
"""
from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass, field, asdict
from collections import Counter, defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包成 exe 后 `__file__` 指向解包出的临时目录 —— 于是 rules/corpus 找不到，
# 而且**台账会写进临时目录、退出就丢**。所以允许用 EGO_ROOT 指定项目根，
# 由启动器（exe）在导入任何引擎模块之前设置。
# 不设 EGO_ROOT 时行为与从前完全一致（源码运行时就是这个分支）。
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)


# ------------------------------------------------------------------ 反应模式
#
# ⚠️ 这里**不是**"好／坏"的判据，是"对方的反应长什么样"的描述。
#    第一版设计把它写成"结果变好/变坏"，那是打分 —— 会导向迎合。已废。
REACTIONS = {
    "ANSWERED_MORE": "他接着说，而且说得更长",
    "ANSWERED_SAME": "他接着说，长度差不多",
    "ANSWERED_LESS": "他接着说了，但更短",
    "CHANGED_SUBJECT": "他**明说**要换话题（跳过／换一题／下一题）",
    "TOPIC_MOVED": "话题被调度挪走了（**机制，不是他的反应**）",
    "CLOSED": "他收尾了",
    "SILENT": "他没出声",
    "NO_REPLY": "对话结束了",
}

CLOSING_LEX = ("就这样吧", "算了", "不说了", "没什么好说的", "没什么", "没事",
               "不知道", "嗯", "哦", "好吧", "随便", "都行", "无所谓")
SKIP_LEX = ("跳过", "换一题", "下一题", "不想答这个", "换个话题")


def _reaction_of(prev_raw: str, cur_raw: str, prev_topic: str, cur_topic: str) -> str:
    """看**对方**对上一轮的反应。只看可观察的字面事实，不做推断。

    与第一版的关键区别：这里判的是"他的反应长什么样"，不是"我好不好"。

    ★★ 话题变化的归因（本轮修的实测缺陷，第三次撞上同一个病）
      原实现：`prev_topic != cur_topic` → 直接判 `CHANGED_SUBJECT`（"他换了话题"）。
      而话题是 `topics.py` 的**阶梯**在推 —— 它不是他的动作，是机制的动作。
      更坏的是：它在 `derive_from_ledger` 里被一条启发式**分账**
      （"话题变了 且上一轮我在问 → 算他换的"），于是产生一个假象：
      **我一问细节，话题往前走一格，账就记在他头上。**
      然后性格层拿这个账算出"我问他细节的时候，多半就停在那儿" ——
      一句话里三层都是机制，却读起来像关于他的发现。

      实测两个数：
        · 台账里他**明说**要换话题的次数（跳过／换一题／下一题）：**0 次**
        · 而旧判据报出"他换了话题"28 次（修掉跨会话 bug 后 15 次）
      也就是说：全部是机制归因，一次都不是他。

      修法：**只有他明说才算他换的**；话题被调度挪走另记 `TOPIC_MOVED`，
      并明确标注"机制，不是他的反应"—— 它既不进"接得住"，也不进"停在那儿"。
    """
    cur = (cur_raw or "").strip()
    if not cur:
        return "SILENT"
    if any(cur == w or cur.startswith(w) for w in CLOSING_LEX):
        return "CLOSED"
    # 明说换话题 —— 这是他的动作，可观察、字面可判。
    if any(w in cur for w in SKIP_LEX):
        return "CHANGED_SUBJECT"
    # 话题号变了但**他没说** —— 那是调度做的，不算他的反应。
    if prev_topic and cur_topic and prev_topic != cur_topic:
        return "TOPIC_MOVED"
    p, c = len((prev_raw or "").strip()), len(cur)
    if p and c >= p * 1.3:
        return "ANSWERED_MORE"
    if p and c <= p * 0.7:
        return "ANSWERED_LESS"
    return "ANSWERED_SAME"


# ------------------------------------------------------------------ 数据结构

@dataclass
class Pair:
    """一次配对：我做了一件什么事，对方接着怎么反应。"""

    turn: int
    era: str
    mine: str                    # 我做的（言语行为 ID）
    my_kind: str                 # 归类（问／承认／复述／沉默／收尾／报告自己）
    his: str                     # 对方的反应（见 REACTIONS）
    mine_detail: str = ""        # 内容细节（例如"问的是细节"）
    his_detail: str = ""         # 反应细节（字数变化）
    topic: str = ""
    # ★ 2026-10-29（Gemini 拍板）：这次配对是不是一次**深度遭遇**。
    #   "" = 既非确认也非受挫（大多数轮次都是这个）
    #   "CONFIRMED" = 她亮出矛盾/悬念后，他**端出了新内容**（深层遭遇）
    #   "REBUFFED"  = 她亮出来之后，他收尾了 / 骤短 / 绕开
    #
    #   ⚠️ 它**不参与打分、不排序**（本模块的既有纪律：只记配对，不打分）。
    #      它唯一的去处是 `Character.polarity.boldness` 那个**读数**。
    encounter: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# 我做的一件事 → 归类。**这类归类比言语行为更粗**，因为要跨轮统计。
MY_KIND = {
    "ASK_DETAIL": "问",
    "QUESTION": "问",
    "ASK_MUST": "问",
    "REPLENISH": "要求具体的体验",
    "ACKNOWLEDGE": "承认",
    "ACKNOWLEDGE_CLOSE": "接住收尾",
    "REPORT_OWN_STATE": "说自己",
    "REFLECT": "复述",
    "JUXTAPOSE": "并排呈现",
    "TURN_IMMUTABLE": "区分能改与不能改",
    "SILENCE": "没出声",
    "META_REPLY": "说明自己是什么",
    # ★ 2026-10-28：大脑路径上唯一**已确认**的动作（逐字引文核对通过）。
    "QUOTE_SOURCE_SET_CONFIRMED": "引用来源",
}


# ------------------------------------------------------------------ 主类

# ══════════════════════════════════════════════════════════════════
# 深度遭遇（Gemini 2026-10-29 拍板的判据，**全部本地确定性，零模型主观**）
# ══════════════════════════════════════════════════════════════════
#
# 为什么要它：`character.modulate` 只能**向保守方向**走（结构性防讨好）。
# 但那样一来，"经历"只能让她越来越小 —— 数学上长不出双向偏好。
# ⇒ 不动 `modulate`，另开一个**只由经历累积**的读数 `boldness`。
#
# 判据的三个组成部分，每个都有明确理由：
#   ① `BOLD` —— 她这一轮做了**有内容的探照**（把矛盾/悬念亮出来，或带着 Thought 发问）
#   ② `has_new_claim` —— 他**端出了至少一条新原话**（不是原地复读）
#      ⚠️ 用"有新 claim"而不是"claim 总数变多"：后者会把"话变啰嗦"当深入，
#         而且第 t 轮 3 条、第 t+1 轮 2 条极深刻时会被漏判（Gemini 指出的）
#   ③ `len >= 15 或 ratio >= 0.5` 且 `not is_closing` —— 排除"嗯/好吧/随便你"

_ENCOUNTER_MIN_LEN = 15
_ENCOUNTER_MIN_RATIO = 0.5
_REBUFF_MAX_LEN = 12
_REBUFF_MAX_RATIO = 0.4

#: 「零新 claim 且字数明显缩」⇒ 打太极（Gemini 第二节补的那一档）
_REBUFF_SHRINK = 0.85


def _is_bold(e: dict) -> bool:
    """她这一轮是否做了「有内容的探照」。"""
    act = e.get("action_observation") or {}
    cog = e.get("cognition") or {}
    # ★ 2026-10-30（Gemini 拍板）：**`focus_level` 也算 BOLD。**
    #
    #   理由：无论她把**当轮冲突（input）**、**上一轮悬念（unfinished）**、
    #   还是**空档回想（idle）**真正说出口点破了，**对用户来说都是一次真实的深度探照**
    #   ⇒ 理应享受下一轮 `CONFIRMED / REBUFFED` 的反馈结算。
    #   ⚠️ 第一版只看 `thought_level`（只覆盖当轮算子），
    #      于是"她顺着悬念往下说了"这件事**不算探照** —— 那会低估她的主动性。
    # ★ 2026-10-31（用户裁定）：**兜底轮不算 BOLD 探照。**
    #   理由：兜底句不是她想出来的（大脑失败了），把它算成"她亮出了拉扯"
    #   等于把一次系统故障记成一次深度探照。
    if act.get("actual") == "FALLBACK" or act.get("fallback"):
        return False
    return (act.get("actual") == "THOUGHT_EXECUTED_STRONG"
            or act.get("thought_level") in ("STRONG", "WEAK")
            or act.get("focus_level") in ("STRONG", "WEAK")
            or (bool(cog.get("op")) and act.get("actual") == "QUESTION"))


def _claim_texts(e: dict) -> set:
    """这一轮抽出的 claim 文本集合（空集合 = 没抽到）。"""
    cog = e.get("cognition") or {}
    return {c.get("text") for c in (cog.get("claims") or []) if c.get("text")}


def classify_encounter(cur: dict, nxt: dict) -> str:
    """判定一次同会话 `t -> t+1` 转移是 CONFIRMED / REBUFFED / ""（既非也）。

    ⚠️ 调用方必须先用 `_same_session` 保证这两行是同一次对话 ——
       跨会话的"下一句"不是反应。
    """
    if not cur or not nxt or not _is_bold(cur):
        return ""
    a = (cur.get("raw_input") or "").strip()
    b = (nxt.get("raw_input") or "").strip()
    if not b:
        return ""
    ratio = len(b) / float(max(1, len(a)))
    new_claim = bool(_claim_texts(nxt) - _claim_texts(cur))
    closing = bool(((nxt.get("mech") or {}).get("is_closing")))
    if (not closing) and new_claim and (len(b) >= _ENCOUNTER_MIN_LEN
                                        or ratio >= _ENCOUNTER_MIN_RATIO):
        return "CONFIRMED"
    if closing or (len(b) < _REBUFF_MAX_LEN and ratio < _REBUFF_MAX_RATIO
                   and not new_claim):
        return "REBUFFED"
    # ★ 2026-10-29（Gemini 第二节）：**补"打太极"这一档**。
    #
    #   实测（36 轮）：BOLD 5 次 → CONFIRMED 3 / REBUFFED 0 / 既非也 1。
    #   为什么原来那档抓不到：AI 家教（`SPEAK_SYSTEM` 规定"一到两句"）
    #   **从不写少于 12 字的句子** ⇒ `len(b) < 12` 永远为 False ⇒ 那档形同虚设。
    #
    #   ⇒ 补：「**零新 claim** 且字数比上一轮明显缩（< 0.85）」= 他接了一句但没往深处说。
    #   ⚠️ 0.85 是待标定值（ENG）：36 轮里未确认那次是 39/60 = 0.65，
    #      已确认的几次是 0.91 / 0.80 / 1.05 / 0.80 —— 0.85 会把 0.80 那两次也划进来，
    #      但它们有 3 条新 claim，被 `not new_claim` 救回来。
    #      **两个条件必须同时成立，否则会误伤真确认。**
    if (not new_claim) and ratio < _REBUFF_SHRINK:
        return "REBUFFED"
    return ""


class Association:
    """关联矩阵。

    ⚠️ 它**不打分、不排序、不推荐**。它只做两件事：
       ① 记下「我做了什么 × 他接着怎么反应」的配对
       ② 统计**我自己**的行为分布 —— 这是"从对方的反应里看自己"的原料
    """

    STORE = "association.jsonl"

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(_ROOT, "state", self.STORE)
        #: ★ 最近一次深度遭遇的结果（"CONFIRMED" / "REBUFFED" / ""）。
        #: 由 `derive_from_ledger` 在遍历时更新，供 `Character` 的 R4 与意识海门控读。
        self.last_encounter = ""
        self.pairs: list[Pair] = []
        # ★ 2026-10-29：深度遭遇的双向计数（只由经历累积，与机制快照无关）
        self.confirmed_count = 0
        self.rebuffed_count = 0
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        for line in io.open(self.path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                known = {k: d.get(k) for k in Pair.__dataclass_fields__ if k in d}
                self.pairs.append(Pair(**known))
            except (json.JSONDecodeError, TypeError):
                continue

    def append(self, pairs: list[Pair]) -> int:
        if not pairs:
            return 0
        with io.open(self.path, "a", encoding="utf-8") as f:
            for p in pairs:
                f.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")
        self.pairs.extend(pairs)
        return len(pairs)

    # ------------------------------------------------ 从台账派生
    #
    # ⚠️ 只读派生，不改变任何现有行为（与 experience.py 同一纪律）。
    #    同时**不碰旧数据**：旧条目没有 raw_input，跳过。
    #
    # ★★ 必须切会话边界（本轮修的实测缺陷，数字可复核：tests/audit_t01_attribution.py）
    #   原实现把**相邻两行**配成一对，而台账里混着几十次独立会话
    #   （turn_id 每个会话从 1 重新计数）。于是：
    #     · 上一个会话的最后一句，会和下一个会话的第一句配成一对
    #     · 这一对还带一个"反应"：长度变化、话题变化 —— 全是伪造的
    #   实测：61 条有原话的轮次 → 60 个名义配对，其中 **32 个（53%）跨会话**。
    #   后果不是小噪声，是把性格层的**全部输入**污染掉一半：
    #     CHANGED_SUBJECT 报 28 → 真实 17；ANSWERED_LESS 报 5 → 真实 3；
    #     连"配对 N 条"这个分母本身都掺了假。
    #   最坏的一例：「他在 T01 这个话题上换过 6 次」——
    #     4 次是我自己的话题阶梯推进（其中 3 次其实是会话结束），
    #     2 次是跨会话拼接伪造的，**他真正换话题 0 次**。
    #     而这句被归入"注意到但不说"，用途是"少往那儿问" ——
    #     等于让系统因为自己的 bug 而躲开一个话题，还不告诉用户。
    @staticmethod
    def _same_session(a: dict | None, b: dict | None) -> bool:
        """b 是否紧接在 a 之后、且属于同一次对话。

        判据用 `turn_id` 递增：台账里每个会话的 turn_id 从 1 重新计数，
        所以"下一行的 turn_id 不再递增"就是换了一次会话。
        这是**可观察的事实**，不是推断。
        """
        if not a or not b:
            return False
        first, second = a.get("input_origin") or {}, b.get("input_origin") or {}
        for key in ("run_id", "session_id"):
            if key in first or key in second:
                if first.get(key) != second.get(key):
                    return False
        return (b.get("turn_id") or 0) > (a.get("turn_id") or 0)

    @classmethod
    def derive_from_ledger(cls, ledger_path: str | None = None,
                           out_path: str | None = None) -> "Association":
        from experience import load_ledger
        entries = load_ledger(ledger_path)
        rows = [e for e in entries if (e.get("raw_input") or "").strip()]
        a = cls(out_path)

        # 话题的先后需要按轮次排 —— 台账里可能混了多个会话（turn_id 会重复）
        cur: list[Pair] = []
        for i, e in enumerate(rows):
            if e.get("intent") == "META":
                continue
            from action_observation import learning_action
            beh = learning_action(e)
            if beh is None:
                continue
            kind = MY_KIND.get(beh, beh)
            if kind == "说明自己是什么":
                continue                      # 元提问不是交流，不进矩阵
            # ★ 下一句只在**同一会话内**才算"他的反应"；跨会话的下一句不是反应。
            nxt = rows[i + 1] if (i + 1 < len(rows) and cls._same_session(e, rows[i + 1])) else None
            if nxt is None:
                his = "NO_REPLY"
                his_detail = ""
            else:
                his = _reaction_of(e.get("raw_input", ""), nxt.get("raw_input", ""),
                                   e.get("topic_id"), nxt.get("topic_id"))
                his_detail = "%d→%d 字" % (len((e.get("raw_input") or "").strip()),
                                          len((nxt.get("raw_input") or "").strip()))
            # ★ 区分「谁换的话题」：如果这一轮的话题与上一轮不同，而上一轮**我做的不是问**，
            #   那多半是话题调度（R1 跟随用户）换的 —— 即**他**把话题带走了。
            #   这不是推断，是 topics.py 的既定行为（R1：用户带进来的域优先）。
            #   对照：若上一轮我问了细节而他没答到题上，话题不动 —— 那不构成换题。
            #   ⚠️ 上一轮同样必须**在同一会话内**：跨会话的"上一轮"是另一次对话的结尾。
            prev = rows[i - 1] if (i > 0 and cls._same_session(rows[i - 1], e)) else None
            prev_t = prev.get("topic_id") if prev else None
            if prev_t and e.get("topic_id") and prev_t != e.get("topic_id") \
                    and MY_KIND.get(prev.get("behavior", "")) != "问":
                kind = "我换的话题"
            # ★ 2026-10-29（Gemini 拍板）：同会话 t -> t+1 的**深度遭遇**分类。
            #   `nxt` 上面已经用 `_same_session` 保证过是同一次对话 ——
            #   跨会话的"下一句"不是反应，这里不重复判。
            _enc = classify_encounter(e, nxt) if nxt is not None else ""
            if _enc == "CONFIRMED":
                a.confirmed_count += 1
            elif _enc == "REBUFFED":
                a.rebuffed_count += 1
            if _enc:
                a.last_encounter = _enc
            cur.append(Pair(turn=e.get("turn_id", 0), era=e.get("era", "?"),
                            mine=beh, my_kind=kind, his=his, his_detail=his_detail,
                            topic=e.get("topic_id") or "",
                            encounter=_enc))
        # 用派生出的配对覆盖文件（保持幂等：重复跑不会累加）
        if os.path.exists(a.path):
            os.remove(a.path)
        a.pairs = []
        a.append(cur)
        return a

    # ------------------------------------------------ 我是什么样
    #
    # ★ 这一节是米德那句话的落点：**用对方的反应来描述我自己**。
    #   注意主语必须是"我"，不能是"他"。
    def self_view(self) -> dict:
        """产出关于**自己**的描述。全部可追溯到次数，不含评价。"""
        if not self.pairs:
            return {"n": 0, "lines": [], "note": "还没有数据"}
        n = len(self.pairs)
        by_kind = Counter(p.my_kind for p in self.pairs)
        lines = []

        def _mode(counter: Counter) -> tuple[str, int, bool]:
            """返回（众数, 次数, 是否唯一）。**并列时不许挑一个当结论。**"""
            if not counter:
                return "", 0, False
            top = counter.most_common()
            best = top[0][1]
            tied = [k for k, v in top if v == best]
            return top[0][0], best, len(tied) == 1

        # ① 我最常做的是什么（客观计数，不是评价）
        k, v, uniq = _mode(by_kind)
        if uniq:
            lines.append("我做了 %d 件事，其中最多的是「%s」（%d 次，占 %.0f%%）。"
                         % (n, k, v, 100.0 * v / n))
        else:
            top = by_kind.most_common()
            best = top[0][1]
            tied = [kk for kk, vv in top if vv == best]
            # "并列"不等于"少"。第一版只写「没有哪一件特别多」，
            # 而实测触发那句时是两项各 20/59 = 34%，两句加起来占 68% ——
            # 把多数现象说成"没有哪一件特别多"，是**低估**，同样是失真。
            # 并列只说明分不出第一，不说明占比小；所以把占比一起报出来，让人自己看。
            share = 100.0 * best / n if n else 0.0
            lines.append("我做了 %d 件事；并列最多的是：%s（各 %d 次，各占 %.0f%%）—— "
                         "**分不出哪一件更多，但它们合起来占 %.0f%%。**"
                         % (n, "、".join("「%s」" % t for t in tied), best, share,
                            share * len(tied)))

        # ② 别人收尾时我在做什么 —— 从对方的反应里看自己
        # ⚠️ 并列时**不挑一个当结论**。第一版在这里报了「那之前我做的多是「并排呈现」（1 次）」
        #    —— 1 次并列第一，读起来像发现，其实是噪声。这是"把巧合包装成发现"的同一类错误。
        closed = [p for p in self.pairs if p.his == "CLOSED"]
        if closed:
            c = Counter(p.my_kind for p in closed)
            k2, v2, uniq2 = _mode(c)
            if uniq2 and v2 >= 2:
                lines.append("他收尾过 %d 次；那之前我做的最多的是「%s」（%d 次）。"
                             % (len(closed), k2, v2))
            else:
                lines.append("他收尾过 %d 次；那之前我做的事很分散（%s），看不出哪个更多。"
                             % (len(closed),
                                "、".join("%s%d次" % (kk, vv) for kk, vv in c.most_common())))

        # ③ 谁在换话题 —— 这一条是**阶段②→阶段③的关键区分**
        # ②「把自己看作许多人当中的一员，但看不见别人有特殊感受」
        # ③「发现别人也具有他在自己身上觉察的那些感受」
        # 若我分不出"话题是他换的还是我换的"，就还在②。
        mine_ch = sum(1 for p in self.pairs if p.my_kind == "我换的话题")
        his_ch = sum(1 for p in self.pairs if p.his == "CHANGED_SUBJECT")
        moved = sum(1 for p in self.pairs if p.his == "TOPIC_MOVED")
        asked = sum(1 for p in self.pairs if p.my_kind in ("问", "要求具体的体验"))
        # ★ 话题变化必须按**实际来源**分开报，不能揉成一个数。
        #   旧版把"话题号变了"一律说成"他换了话题"，于是机制的动作被记成他的动作，
        #   性格层再拿它推出"我问他细节时话就停在那儿"。实测：他明说换话题 0 次。
        lines.append("我问过 %d 次；话题动过 %d 次：其中**他明说**要换的 %d 次、"
                     "话题调度挪走的 %d 次、调度换题 %d 次。"
                     % (asked, his_ch + moved + mine_ch, his_ch, moved, mine_ch))
        if his_ch:
            lines.append("★ 他明说换过话题 —— 这是鲍德温阶段③的可观察起点"
                         "（发现别人也有他自己的想法）。")
        else:
            lines.append("他一次也没明说要换话题；话题的移动全部来自调度，"
                         "**不能算成他的动作**。")

        # ④ 他说话变长／变短的次数（不解释原因，只陈述）
        more = sum(1 for p in self.pairs if p.his == "ANSWERED_MORE")
        less = sum(1 for p in self.pairs if p.his == "ANSWERED_LESS")
        lines.append("他接下来说得更长 %d 次，更短 %d 次。" % (more, less))

        # ⑤ 我从没做过的事（"曾经存在是最为确定的一种存在"的反面：缺席也是事实）
        never = [k for k in set(MY_KIND.values())
                 if by_kind.get(k, 0) == 0 and k != "说明自己是什么"
                 and k != "我换的话题"]
        if never:
            lines.append("我从来没做过：%s。" % "、".join(sorted(never)))

        return {"n": n, "by_kind": dict(by_kind),
                "by_reaction": dict(Counter(p.his for p in self.pairs)),
                "lines": lines,
                "note": "以上全部是计数与并列，不含评价、不含建议。"}

    # ------------------------------------------------ 注意到但不说
    #
    # ★ 硬约束②：可以注意到关于用户内在的东西，**但不能说出来**（守 E5）。
    #   本方法返回的东西**不进任何输出**，只给 /character 与自检看。
    def noticed_about_user(self) -> list[str]:
        out = []
        if not self.pairs:
            return out
        # 换话题的位置
        ch = [p for p in self.pairs if p.his == "CHANGED_SUBJECT"]
        if len(ch) >= 2:
            topics = Counter(p.topic for p in ch if p.topic)
            if topics:
                t, v = topics.most_common(1)[0]
                out.append("他在 %s 这个话题上换过 %d 次。" % (t, v))
        # 收尾的位置
        cl = [p for p in self.pairs if p.his == "CLOSED"]
        if cl:
            out.append("他收尾了 %d 次，分布在 %d 个话题上。"
                       % (len(cl), len({p.topic for p in cl if p.topic})))
        out.append("⚠️ 以上**只用于调整我自己**（少往那儿问），"
                   "**绝不进入输出** —— 说出来就是替他补出被回避的内容，违反 E5。")
        return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(_ROOT, "engine"))
    a = Association.derive_from_ledger(
        out_path=os.path.join(_ROOT, "state", "association.jsonl"))
    v = a.self_view()
    print("═" * 78)
    print("  关联矩阵：从对方的反应里，学会描述自己")
    print("═" * 78)
    print("  理论依据 [Mead]：当我们学会了用别人的观点来描述我们自己时，心理的意识就产生了。")
    print()
    print("  配对 %d 条" % v["n"])
    if v.get("by_kind"):
        print("  我做过的：%s" % v["by_kind"])
        print("  他接着的：%s" % v["by_reaction"])
    print()
    print("  ── 关于我自己（可进输出）：")
    for l in v["lines"]:
        print("     · %s" % l)
    print()
    print("  ── 注意到但不说（守 E5，不进输出）：")
    for l in a.noticed_about_user():
        print("     · %s" % l)
    print("═" * 78)


# ══════════════ 大脑作答失败的分类（2026-10-30，用户要求「失败分类落盘」）
#
# 用户裁定（甲方决定）：
#   C 类（自身代码异常）**必须 0 次才算通过**；同一批出现 2 次以上，实测自动中止并报警。
#   A 类重试后仍失败的轮，列出次数和原因，不设硬指标。
#   B 类按原因列出，不设上限。
#
# ⚠️ 为什么要分类而不是只数次数：
#   36 轮实测里 3 次失败**原因各不相同**，而它们指向**完全不同的修法**：
#     A 网络/超时  ⇒ 重试就行，系统其实是健康的
#     B 校验打回    ⇒ 模型说了不该说的，校验意见本身是可用信息
#     C 系统异常    ⇒ **不是模型的问题，是我们的 bug**，重试毫无意义

#: A 类：可重试的过程错误（与内容无关）
FAIL_TRANSIENT = (
    "HTTPError", "URLError", "TimeoutError", "Timeout", "ConnectionError",
    "ConnectionResetError", "ConnectionAbortedError", "RemoteDisconnected",
    "socket", "SSLError", "APIError", "RateLimitError", "ServiceUnavailable",
)

#: C 类：**我们自己代码的异常**（重试只是把同一个 bug 再跑一遍）
FAIL_INTERNAL = (
    "ValueError", "KeyError", "AttributeError", "TypeError", "IndexError",
    "NameError", "UnboundLocalError", "ZeroDivisionError", "AssertionError",
)


def classify_failure(error_type: str = "", violations=None, reason: str = "") -> str:
    """把一次大脑作答失败分成 `"A"` / `"B"` / `"C"` / `""`（没失败）。

    ★ 判据优先级：**C 先于 A 先于 B**。
      因为一个异常（`ValueError` 等）一定是内部 bug，
      哪怕它的名字里也带 "Error" —— 不能因为 `ValueError` 含 "Error" 就误判成网络错误。
    """
    et = (error_type or "").strip()
    if et:
        for k in FAIL_INTERNAL:
            if et == k or et.endswith(k) and k in FAIL_INTERNAL:
                return "C"
        for k in FAIL_TRANSIENT:
            if k.lower() in et.lower():
                return "A"
        # 其余异常：保守归 C（"我们的代码出了问题"），因为不可归因的异常不该当网络抖动
        return "C"
    if violations or (reason or "").strip():
        return "B"
    return ""


def failure_detail(error_type: str = "", violations=None, reason: str = "") -> str:
    """给日志用的一句话归因（不含内部词 —— 内部词只进日志，不进她的嘴）。"""
    kind = classify_failure(error_type, violations, reason)
    if kind == "A":
        return "网络/超时：%s" % (error_type or "?")
    if kind == "C":
        return "系统异常：%s" % (error_type or "?")
    if kind == "B":
        v = list(violations or [])
        return "校验打回：%s" % ("；".join(str(x) for x in v[:2])[:120] or (reason or "")[:120])
    return ""


#: 校验意见里的**内部词** —— 这些只能进日志，**绝不能原样给她**
#  （用户明确要求；轮 33 她把提示词结构说出口就是前车之鉴）
_INTERNAL_TERMS = (
    "memory_scope", "record_absence_verified", "source_hashes", "evidence_basis",
    "goal_selection", "self_state", "frame", "Frame", "cognition", "claim", "Claim",
    "violations", "REJECT", "UNKNOWN", "origin", "schema", "trace", "traceable",
    "own_task", "memory_scope", "independent_semantics_verified",
)

#: 把内部词改写成的**普通要求**（她读到的是这些，不是那些）
_PLAIN_RULES = (
    ("memory_scope", "你手上的记录不完整"),
    ("record_absence_verified", "没有核对过「这件事不存在」"),
    ("claim", "他话里的具体内容"),
    ("REJECT", "这一句不合格"),
    ("UNKNOWN", "这一句不合格"),
)


def plain_violation_text(reason: str = "", violations=None, limit: int = 120) -> str:
    """把校验意见改写成**一句她读得懂的普通要求**。

    ★ 2026-10-30（用户要求）：
      「校验意见里的内部词（memory_scope、record_absence_verified 等）
        不要原样给她，改写成一句普通要求。」

    ⚠️ 为什么这一步不能省：**她读到内部词就会把它们说出口。**
      轮 33 她说过「我说的不是你原话里的『往死里逼自己』和『熬了仨月』」——
      那是把我的简报结构复述了一遍。同一个病，在失败重试这条路上会更容易犯，
      因为**重试时她唯一的输入就是那句意见**。
    """
    raw = "；".join(str(x) for x in (violations or [])) or (reason or "")
    if not raw:
        return ""
    out = raw
    for k, v in _PLAIN_RULES:
        out = out.replace(k, v)
    # 剩下的内部词一律抹掉（不替换成任何东西 —— 宁可少说，不能漏出去）
    for t in _INTERNAL_TERMS:
        out = out.replace(t, "")
    # 收掉由此产生的空括号/多余标点
    for junk in ("（）", "()", "［］", "[]", "；；", "  "):
        while junk in out:
            out = out.replace(junk, "；" if "；" in junk else " ")
    return out.strip()[:limit]


# ══════════════ 「先接住他的问题」与逐字引文的**本地**判定（2026-10-31）
#
# 用户裁定（主线）：
#   「他最后一句向她提问时，回应的第一句必须直接回答，或如实说没法确认；
#     引旧话只能放在回答之后；这类轮次 idle 不作为本轮焦点。
#     引号内必须是他原话的逐字片段，本地检查。」
#
# ★ 为什么必须是本地判定：
#   这两件事（"是不是在问她"、"引号里是不是他的原话"）**都能用字面算出来**，
#   送模型去判既慢又会误判（上一批 9 条打回里至少 1 条半是误判）。

#: 她可能用来"如实说没法确认"的句式（不算回答，但也不算逃避）
_UNCERTAIN = (
    "没法确认", "不确定", "说不准", "不知道", "记不清", "没法说",
    "答不上", "说不上来", "想不起来",
)

#: 他的问句里出现这些，说明他问的是**她**（而不是在自问）
_ASKING_ME = (
    "你", "你说", "你觉得", "你上次", "你刚才", "你那时候", "你也",
)


def _last_sentence(raw: str) -> str:
    """取他**最后一句**（按句末标点切）。"""
    t = (raw or "").strip()
    if not t:
        return ""
    parts = [x for x in t.replace("！", "。").replace("!", "。").split("。") if x.strip()]
    return parts[-1] if parts else t


def asks_her(raw: str) -> bool:
    """他**最后一句**是不是一个问句 —— 是的话，她必须**先接住**。

    ★ 判据（宽口径，全部本地）：最后一句含问号。

    ⚠️ 2026-10-31 第一版我加了"必须含『你』"，当场被两个例子打穿：
         「越惦记着得早早点睡越睡不着这毛病，是不是就我这样啊？」—— 没有"你"，
         但显然是问她；而「我是不是又要犯了？」是自语，却也不该被无视。
       ⇒ 于是改成**宽口径**：只要是问句，就要求"先接住"。
         因为对她的行为来说，这两种情况**该做的事是同一件**：
         别绕开它去引旧话。**自语问句她照样可以答"这个我没法替你确认"。**

    ⚠️ 为什么必须看**最后一句**：他可能前面问了一堆、最后一句是陈述，
      那一轮她该接的是陈述。
    """
    seg = _last_sentence(raw)
    return ("？" in seg) or ("?" in seg)


def asks_her_explicitly(raw: str) -> bool:
    """窄口径：最后一句是问句**且**含第二人称 —— 用于统计，不用于规则。

    ★ 区分这两个口径是为了**如实报数**：
      "他明确在问她"（含你）与"他在问一个问句"（可能自语）是两件事，
      混成一个数会让人以为所有问句都是冲她来的。
    """
    seg = _last_sentence(raw)
    if ("？" not in seg) and ("?" not in seg):
        return False
    return any(k in seg for k in _ASKING_ME)


def quotes_verbatim(text: str, source: str, min_len: int = 2) -> tuple[bool, list[str]]:
    """她输出里所有「」／『』引号内的片段，是否都是 `source` 的**逐字子串**。

    返回 `(是否全部逐字, 不逐字的片段列表)`。

    ★ 用户裁定：「引号内必须是他原话的逐字片段，本地检查。」
    ⚠️ 为什么必须查：`unfinished` / `idle` 的 hint 都要求"带引号点出原话"，
      她就会把原话**缩写**后放进引号（上一批样本 2 把
      「自己哪儿哪儿都不对」写成「自己不对」放进引号）。
      那是**改写了别人的话还加引号**，比不引更糟。
    """
    import re as _re
    if not text:
        return True, []
    src = source or ""

    def _norm(x: str) -> str:
        # ⚠️ 去掉**句末标点**再比 —— 否则「甲项目押金由周老师收着。」
        #   与原文「甲项目押金由周老师收着」对不上，会把合法引用判成改写。
        #   （test_sequence_pool Q4 就是被这个句号打掉的。）
        return _re.sub(r"[。，、；！？…—\-"  + "]" + r"\s*$", "", x.strip())

    bad = []
    for m in _re.finditer(r"[「『]([^」』]{1,80})[」』]", text):
        frag = m.group(1).strip()
        if len(frag) < min_len:
            continue
        if frag in src:
            continue
        if _norm(frag) and _norm(frag) in src:
            continue
        bad.append(frag)
    return (not bad), bad

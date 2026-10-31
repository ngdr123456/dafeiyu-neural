# -*- coding: utf-8 -*-
"""L2 标记层引擎

职责：把一段自由文本解析成「可观察的结构标记」。
纪律（[E]）：『我们试图在最低限度的推理水平上陈述观察。』
    因此本模块只做字面匹配 + 反例过滤，**不做任何语义推断**。

纯标准库实现，无外部依赖。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any


# ---------------------------------------------------------------- 数据加载

_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RULES_DIR = os.path.join(_ROOT, "rules")
_CORPUS_DIR = os.path.join(_ROOT, "corpus")


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_marker_rules(rules_dir: str | None = None) -> dict:
    d = rules_dir or _RULES_DIR
    return _load(os.path.join(d, "markers.json"))


def load_topics(corpus_dir: str | None = None) -> dict:
    d = corpus_dir or _CORPUS_DIR
    return _load(os.path.join(d, "topics.json"))


# ---------------------------------------------------------------- 数据结构

@dataclass
class MarkerHit:
    """一次标记命中。evidence 保留命中的字面片段，供 L6 台账追溯。"""
    id: str
    kind: str
    label: str
    level_hint: str | None
    direction: str | None          # UP / DOWN / None
    confidence: float
    evidence: list[str] = field(default_factory=list)
    sub_kind: str | None = None    # 用于 voice_shift 的 passive/active


@dataclass
class ParseResult:
    raw: str
    topic_id: str | None
    hits: list[MarkerHit]
    markers: list[str]
    signature: dict
    signature_key: str
    underdetermined: bool
    opposed_pair: bool
    relation_hint: str
    intent: str = "ANSWER"        # ANSWER | META | CLARIFY
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- 元提问识别（规则版）

def _load_meta(rules_dir: str | None = None) -> dict:
    """加载元提问库，返回 {"questions": [...], "states": [...]}。

    v2 起分两类（见文件内 _what_changed）：
      QUESTION = 用户在问系统本身      → 走 META 通道，不进水平判定
      STATE    = 用户在说自己的状态    → 走正常轮次，进水平判定与台账
    """
    d = rules_dir or _RULES_DIR
    p = os.path.join(d, "meta_responses.json")
    if not os.path.exists(p):
        return {"questions": [], "states": []}
    with open(p, "r", encoding="utf-8") as f:
        d_obj = json.load(f)
    return {
        "questions": [r for r in d_obj.get("responses", []) if r.get("type", "QUESTION") == "QUESTION"],
        "states": [r for r in d_obj.get("states", []) if r.get("type", "STATE") == "STATE"],
    }


def _norm_exact(text: str) -> str:
    """精确匹配用的归一化：去掉空白、零宽字符与首尾标点。

    只用于 `exact_patterns`（整句相等）这条路，**绝不用于子串匹配** ——
    子串匹配必须保持逐字敏感，否则会扩大误判面。
    """
    t = text or ""
    for ch in "\ufeff\u200b\u200c\u200d\u2060\ufffd \t\r\n":
        t = t.replace(ch, "")
    return t.strip("？?！!。.，,、；;：:~～…—-·")


def _exact_index(meta: dict) -> dict:
    """把所有 QUESTION 条目的 exact_patterns 编成 {归一化短语: 条目}。

    为什么需要这条路（甲案，用户选定）：
      用户只打「干嘛」两个字时，句中没有第一人称，唯一可能的听话人就是对话对象。
      但**不能用子串收法**收它：『我在想干嘛』『我不知道要干什么』是用户在说自己，
      子串会把它们误判成在问系统 —— 那正是 v2 修掉的范畴错误。
      所以判据只能是『整句归一化后完全相等』。
    实测（`tests/probe_api_role.py`）：模型对「干嘛」判 META（对的），
      却被 `_addresses_system` 这道手写闸门挡回去了。这条路让正确的判断过得去。
    """
    idx = {}
    for r in (meta.get("questions") or []):
        for p in (r.get("exact_patterns") or []):
            k = _norm_exact(p)
            if k and k not in idx:
                idx[k] = r
    return idx


def _is_second_person_question(t: str) -> bool:
    """这句话是不是『明确指着我问』：有第二人称 + 是疑问句。

    模块级函数（不是类方法），因为 `rule_intent` 与 `meta_response` 都要用它 ——
    两处若各写一份，迟早不一致，然后意图判 META、回应却查不到模板（或反过来）。
    """
    if "你" not in (t or "") and "您" not in (t or ""):
        return False
    s = (t or "").strip()
    if not s:
        return False
    if s[-1] in _Q_TAIL:
        return True
    return any(w in s for w in _Q_WORDS)


# 疑问标记：句末疑问语气，或疑问代词。只做字面判断（[E] 最低限度推理）。
_Q_TAIL = ("？", "?", "吗", "呢", "么", "嘛")
_Q_WORDS = ("为什么", "怎么", "什么", "是不是", "有没有", "能不能", "可不可以",
            "多少", "哪", "谁", "何时", "多久")


def rule_intent(text: str, meta_rules) -> str:
    """规则版的意图识别：只认明确指向系统本身的问句。

    宁可漏判（判不出就当 ANSWER），不可误判 —— 与标记层同一条纪律。

    v2 修正：**只有 QUESTION 类**才能判 META。
    原先遍历整个库（含 STATE 类），于是「好累」被判成"在问系统"——
    用户说自己的状态，系统却当成对它的提问。这是范畴错误。
    meta_rules 允许传 dict（新格式）或 list（旧格式，向后兼容）。
    """
    t = text or ""
    if isinstance(meta_rules, dict):
        rules = meta_rules.get("questions", [])
        state_rules = meta_rules.get("states", [])
    else:
        rules = [r for r in (meta_rules or []) if r.get("type", "QUESTION") == "QUESTION"]
        state_rules = [r for r in (meta_rules or []) if r.get("type") == "STATE"]

    # STATE 类命中只说明"用户在说自己的状态"，明确定为 ANSWER。
    for r in state_rules:
        for p in r.get("rule_patterns", []):
            if p in t:
                return "ANSWER"

    # ★ 精确整句匹配（甲案）优先于子串：它是最具体的证据。
    #   顺序不能反 —— 若先算子串，纯标点差异（「干嘛？」）也可能被子串规则抢走。
    if _norm_exact(t) in _exact_index({"questions": rules}):
        return "META"

    hits = 0
    for r in rules:
        for p in r.get("rule_patterns", []):
            if p in t:
                hits += 1
                break
    if hits == 0:
        # ★ 窄兜底：明确指着我问、但库里没有这一问 → 仍判 META，
        #   让管线走元提问分支，由 meta_response 给出那句"我没接住"。
        #   不这么写的话会有一个死结：intent 判 ANSWER → 根本不查元提问库 →
        #   兜底永远轮不到（"写了等于没写"，本模块已犯过四次的那种）。
        if _is_second_person_question(t):
            return "META"
        return "ANSWER"
    # 只在句子短或带问号/第二人称指向系统时才判 META，避免把"我该怎么办"误判
    if len(t) <= 24 or "你" in t:
        return "META"
    return "ANSWER"


# ---------------------------------------------------------------- 引擎

class MarkerEngine:
    def __init__(self, rules: dict | None = None, topics: dict | None = None,
                 visible: set[str] | None = None):
        self.rules = rules or load_marker_rules()
        self.topics = topics or load_topics()
        self._markers = {m["id"]: m for m in self.rules["markers"]}
        self._exp_lex = self._markers["present_missing"]["_experience_lexicon"]
        self._topic_index = {t["id"]: t for t in self.topics["topics"]}
        self.meta_rules = _load_meta()
        # ★ 箭头 A1 的门控：**系统自己的发展水平决定它能看见哪些标记**。
        #
        #   [E] E-900：「评定人员觉察的程度……取决于他们自己的自我水平」
        #
        #   `visible=None` = 不门控（旧行为，向后兼容）。
        #   传进来一个集合时，不在集合里的标记**根本不进入检测** ——
        #   注意是"根本没看见"，不是"看见了但不用"。
        #   这两者的差别就是这一整条设计的意义：一个低水平的系统
        #   **不可能**靠"先看见再忍住不用"来表现得像高水平。
        self.visible = visible

    # ---- 元提问回应（模板，非生成）

    def meta_response(self, raw: str) -> tuple[str | None, str | None]:
        """返回 (response_id, text)，**只在确实是"在问系统"时命中**。

        v2 起不再有运行期兜底：
          判不出来就返回 (None, None)，由上层沉默并把这件事记进反事实条目。
          理由见 rules/meta_responses.json 的 _no_runtime_fallback。

        匹配分两级，**精确整句优先**：
          1. exact_patterns —— 整句归一化后完全相等（甲案，见 _exact_index）
          2. rule_patterns  —— 子串包含
        必须先查精确：它是最具体的证据，且子串查法会误伤
        「我在想干嘛」这类"用户在说自己"的句子。
        """
        t = raw or ""
        exact = _exact_index(self.meta_rules)
        hit = exact.get(_norm_exact(t))
        if hit is not None:
            return hit["id"], hit["text"]
        for r in self.meta_rules.get("questions", []):
            for p in r.get("rule_patterns", []):
                if p in t:
                    return r["id"], r["text"]
        # ★ 窄兜底：明确指着我问、但我表里没有这一问。
        #
        # 为什么三条必须同时成立（缺一条都不行）：
        #   ① 前面全没命中 —— 否则会抢掉已有条目
        #   ② 有第二人称「你／您」—— 它确实是冲着系统说的
        #      （缺这条会把「我今天特别累」当成在问系统，那正是 v2 修掉的范畴错误）
        #   ③ 是疑问句 —— 缺这条会把「你说得对」这类陈述也兜进来
        #
        # 它与被删掉的 v1 GENERIC 的区别：GENERIC 把**识别失败**伪装成一次回应，
        # 让人分不出系统懂没懂；这里只在**意图明确指向系统、只是词表没覆盖**时才开口，
        # 而且回话本身承认"我没接住"—— 一眼看得出。
        #
        # 实测来由（用户截图第 5 轮）：「你在和我说话吗」被沉默了。
        # 那不是"判不出意图"，是识别失败 —— 意图很清楚。
        if self._is_second_person_question(t):
            for r in self.meta_rules.get("questions", []):
                if r.get("is_narrow_fallback"):
                    return r["id"], r["text"]
        return None, None

    # 疑问标记：句末疑问语气，或疑问代词。只做字面判断（[E] 最低限度推理）。
    _Q_TAIL = ("？", "?", "吗", "呢", "么", "嘛")
    _Q_WORDS = ("为什么", "怎么", "什么", "是不是", "有没有", "能不能", "可不可以",
                "多少", "哪", "谁", "何时", "多久")

    @classmethod
    def _is_second_person_question(cls, t: str) -> bool:
        return _is_second_person_question(t)

    def state_response(self, raw: str) -> tuple[str | None, str | None]:
        """返回 (response_id, text)，命中不到返回 (None, None)。

        这是"用户说自己的状态"的固定回应。它与元提问分开，
        因为**用户说自己 ≠ 用户在问系统**。
        """
        t = raw or ""
        for r in self.meta_rules.get("states", []):
            for p in r.get("rule_patterns", []):
                if p in t:
                    return r["id"], r["text"]
        return None, None

    # ---- 基础工具

    @staticmethod
    def _hits(text: str, patterns: list[str]) -> list[str]:
        return [p for p in patterns if p in text]

    def _regex_hits(self, text: str, pattern: str | None) -> list[str]:
        if not pattern:
            return []
        return [m.group(0) for m in re.finditer(pattern, text)]

    # 这些短语自身即是否定式或抑制式表达，**不得**再被否定窗口过滤。
    # 依据：[E] 前意识/抑制的区分是"机制指标"，不是"信念断言"；
    #      「我不去想」本身就是一个抑制机制指标，而不是对某个命题的否定。
    _NEGATION_IMMUNE = (
        "我不去想", "不去想", "不想谈", "不想说这个", "别提了", "别提",
        "算了不说", "改变不了", "改不了了", "没有办法了", "回不去了", "再也",
        "没什么好说的", "不必再说", "不可能了", "没用",
    )

    @staticmethod
    def _is_negated_or_quoted(text: str, phrase: str) -> bool:
        """反例的粗判：短语出现在否定/引用语境里。

        最小实现：查看短语前 6 个字符是否含否定词。
        这不是语义理解，只是一次字面检查 —— 宁可漏判，不可误判。
        """
        if phrase in MarkerEngine._NEGATION_IMMUNE:
            return False
        idx = text.find(phrase)
        if idx <= 0:
            return False
        window = text[max(0, idx - 6):idx]
        negators = ["不", "没", "别", "并非", "不是", "谁说", "有人说"]
        return any(n in window for n in negators)

    def _experience_count(self, text: str) -> int:
        """体验词汇域命中数（ENG）。用于 present_missing 与 want_like_gap 的联合判定。"""
        n = 0
        for words in self._exp_lex.values():
            if isinstance(words, list):
                n += sum(1 for w in words if w in text)
        return n

    @staticmethod
    def _is_dissented(text: str, phrase: str) -> bool:
        """反例：引用群体观点但随即表示不认同。

        [E] 遵奉阶段的反面情形 —— 引用规范不等于接受规范。
        实现为窗口检查（短语后 8 字内出现转折+否定），不做语义理解。
        """
        idx = text.find(phrase)
        if idx < 0:
            return False
        tail = text[idx + len(phrase): idx + len(phrase) + 10]
        turn = ["但", "可是", "不过", "然而", "其实", "我不", "未必", "不一定"]
        neg = ["不", "没", "未必", "别"]
        return any(t in tail for t in turn) and any(n in tail for n in neg)

    # ---- 各类标记的判定

    def _detect(self, mid: str, text: str) -> MarkerHit | None:
        rule = self._markers[mid]
        patterns = rule.get("patterns") or []
        # ★ 子模式的例子也算门控候选。
        #   实测缺陷：voice_shift 的判定是「patterns 过粗判 → sub_patterns 定方向与证据」。
        #   若某条证据写在 sub_patterns 里却不在顶层 patterns 里，它就**永远进不了门**
        #   （raw_hits 为空 → 直接 return None），写了等于没写。
        #   「控制不住」「没控制住」正是这样被挡在外面的：词表里加了也不生效，
        #   加词的人会以为已经修好 —— 这比单纯的漏词更坏。
        #   把门控候选扩成 patterns ∪ sub_patterns.examples，这一类缺陷就不存在了。
        gate = list(patterns)
        for _v in (rule.get("sub_patterns") or {}).values():
            if isinstance(_v, dict):
                gate += list(_v.get("examples") or [])
        raw_hits = self._hits(text, gate)
        rx_hits = self._regex_hits(text, rule.get("regex"))

        # ---- 反例的**机器可判**部分：显式抑制正则
        #
        # 为什么需要这一层（实测缺陷，见 tests/attribute_probe_failures.py）：
        #   `counterexamples` 一直是**给人读的散文**，没有任何代码读它。
        #   于是「都怪我，是我当时没把话说清楚」命中 blame_external ——
        #   因为 patterns 里有「都怪」，而它后面跟的是"我"。
        #   5 处误判全部属于这一类：**写了反例，但反例不生效。**
        #
        # 为什么只收"机器可判"的那部分：
        #   反例分两种。一种是字面就能判的（「都怪我」＝内指，不是外指），
        #   写成正则即可，无歧义。另一种是语义的（「我被堵在路上」算不算
        #   有行动含义的被动），子串匹配**根本做不到**，硬写成特例只会制造
        #   更多"写了等于没写"的条目。后者留给模型那一位评定人（见 understand.py
        #   的 refute 通道）—— 语义判断本来就该是它的活。
        for pat in (rule.get("counterexample_regex") or []):
            if re.search(pat, text):
                return None

        # 反例粗判：若全部命中都落在否定语境，则视为未命中
        kept = [p for p in raw_hits if not self._is_negated_or_quoted(text, p)]
        # 反例：引用群体观点但随即不认同（group_sanction 专有）
        if mid == "group_sanction":
            kept = [p for p in kept if not self._is_dissented(text, p)]
        if not kept and not rx_hits:
            return None

        evidence = kept + rx_hits

        # ---- 特殊联合判定 ----
        if mid == "want_like_gap":
            # 判定条件 = 命中 patterns 之一，且全篇无可体验性描述
            if self._experience_count(text) > 0:
                return None
        if mid == "present_missing":
            # 判定条件 = 未来指向词密集，且体验词汇域命中数为 0
            if self._experience_count(text) > 0 or len(kept) < 2:
                return None

        # ---- voice_shift 的双极处理 ----
        sub_kind = None
        direction = rule.get("direction")
        if mid == "voice_shift" and "sub_patterns" in rule:
            passive = self._hits(text, rule["sub_patterns"]["passive"]["examples"])
            active = self._hits(text, rule["sub_patterns"]["active"]["examples"])
            if active and not passive:
                sub_kind, direction = "active", "DOWN"
                evidence = active
            elif passive:
                sub_kind, direction = "passive", "UP"
                evidence = passive
            else:
                return None

        # ---- attitude_clause 只在不不可改变处境下算方向证据，但标记本身仍记录 ----
        return MarkerHit(
            id=mid,
            kind=rule["kind"],
            label=rule["label"],
            level_hint=rule.get("level_hint"),
            direction=direction,
            confidence=rule.get("confidence", 0.5),
            evidence=evidence[:6],
            sub_kind=sub_kind,
        )

    # ---- 签名

    def _signature(self, text: str, topic_id: str | None, hits: dict[str, MarkerHit]) -> dict:
        spec = self.rules and None  # 占位，签名定义在 schema 中
        topic = self._topic_index.get(topic_id or "", {})
        blame = "EXTERNAL" if "blame_external" in hits else "INTERNAL"
        time_pref = "FUTURE" if "present_missing" in hits else "PRESENT"
        immutable = "IMMUTABLE" if ("immutable" in hits or topic.get("immutable")) else "CHANGEABLE"
        intensity = min(2, len(hits))
        return {"blame": blame, "time": time_pref,
                "mutability": immutable, "intensity": intensity}

    @staticmethod
    def _sig_key(topic_id: str | None, sig: dict) -> str:
        return "%s:%s|%s|%s|%s" % (
            topic_id or "NA", sig["blame"], sig["time"], sig["mutability"], sig["intensity"])

    # ---- relation（三值关系）

    def _relation(self, text: str, hits: dict[str, MarkerHit]) -> str:
        # 只认机制指标，不解释内容（[E] 最低限度推理；E5）
        suppressed = ["我不去想", "别提", "不去想", "不想谈", "不想说这个", "算了不说"]
        displaced = ["不知道为什么", "我一直在说别的", "跑题", "说远了", "扯远了"]
        deferred = ["我没想起", "没想到", "想不起来", "忘了"]
        if any(p in text for p in suppressed):
            return "SUPPRESSED"
        if any(p in text for p in displaced):
            return "DISPLACED"
        if any(p in text for p in deferred):
            return "DEFERRED"
        return "NONE"

    # ---- 主入口

    def parse(self, text: str, topic_id: str | None = None) -> ParseResult:
        text = (text or "").strip()
        hits_list: list[MarkerHit] = []
        blocked: list[str] = []
        for mid in self._markers:
            if self.visible is not None and mid not in self.visible:
                blocked.append(mid)               # A1：还没长到能看见它
                continue
            h = self._detect(mid, text)
            if h:
                hits_list.append(h)
        hits = {h.id: h for h in hits_list}

        sig = self._signature(text, topic_id, hits)
        notes: list[str] = []

        # 未判定提示：完全没有任何命中，即无法判定 → 废纸篓（[E]）
        underdetermined = len(hits_list) == 0
        if underdetermined:
            notes.append("无标记命中：按【废纸篓类别】记于遵奉水平 [E]")

        # E1 / 燃料优先 的提前标注（不在本层执行，只上报）
        if "immutable" in hits:
            notes.append("E1 生效：禁止任何水平提升型回应")
        if "present_missing" in hits:
            notes.append("fuel_priority 生效：先补当下，不提水平")
        if "over_intention" in hits:
            notes.append("过度意向：仅允许 REFLECT / ASK_MUST")

        # 方向线（两条，独立）
        dopamine_line = "UP" if "want_like_gap" in hits else None
        frankl_line = "DOWN" if ("attitude_clause" in hits and sig["mutability"] == "IMMUTABLE") else None

        return ParseResult(
            raw=text,
            topic_id=topic_id,
            hits=hits_list,
            markers=[h.id for h in hits_list],
            signature=sig,
            signature_key=self._sig_key(topic_id, sig),
            underdetermined=underdetermined,
            opposed_pair="opposed_pair" in hits,
            relation_hint=self._relation(text, hits),
            notes=notes + [
                "dopamine_line=%s" % dopamine_line,
                "frankl_line=%s" % frankl_line,
            ],
        )


if __name__ == "__main__":
    import sys
    eng = MarkerEngine()
    for line in sys.argv[1:]:
        r = eng.parse(line)
        print(json.dumps(r.to_dict(), ensure_ascii=False, indent=1))

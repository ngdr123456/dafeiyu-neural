# -*- coding: utf-8 -*-
"""L5 回应层

职责：按固定阶梯选择言语行为，并用**用户原话的逐字片段**回填模板。
不允许改写，不允许添加用户未说过的新信息。

理论依据见 rules/behaviors.json 各条 source。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RULES_DIR = os.path.join(_ROOT, "rules")

SPLIT_RE = re.compile(r"[。！？；\n]+")
CONTRAST = ["但是", "但", "可是", "不过", "然而"]

# 『两个方面』的连接词 —— 用于把一对对立观念切成两个片段。
# [E] 第九章：『个体头脑中会共存两个相反的或相对的观念』
PAIR_HEADS = ["一方面", "另一方面", "一是", "二是", "有时候"]
PAIR_TAILS = ["另一方面", "但有时候", "可是又", "又", "也"]


@dataclass
class Render:
    behavior: str
    output: str
    slots_used: dict
    reason: str
    source: str
    silenced: bool = False
    # 若被"禁止提升"闸门降级，这里记下**原本选中的行为**。
    # 调用方靠它区分"真的是复述"与"被闸门降级成复述"（见 render 里的注释）。
    downgraded_from: str | None = None


class Responder:
    def __init__(self, rules_dir: str | None = None):
        rules_dir = rules_dir or _RULES_DIR
        with open(os.path.join(rules_dir, "behaviors.json"), "r", encoding="utf-8") as f:
            self.cfg = json.load(f)
        self._b = {b["id"]: b for b in self.cfg["behaviors"]}
        # 每个行为被调用过几次 —— 模板轮换的确定性种子（见 render）
        self._render_count: dict[str, int] = {}

    # -------------------------------------------------------- 槽位抽取

    @staticmethod
    def clauses(raw: str) -> list[str]:
        return [c.strip() for c in SPLIT_RE.split(raw or "") if c.strip()]

    def _pick_echo(self, raw: str, markers: set[str]) -> str:
        """回填片段。

        若存在一对对立观念，则两个片段都取自**同一次切分**，保证它们真的是
        相对的两句，而不是「整句 + 其中一半」。
        （教训来源：D1 用例第一次实现时输出了「整句 + 后半句」这种无意义配对。）
        """
        if "opposed_pair" in markers:
            a, b = self.split_pair(raw)
            if a and b:
                return a
        cs = [c for c in self.clauses(raw) if len(c) >= 4]
        if not cs:
            return ""
        return max(cs, key=lambda c: (("我" in c), len(c)))

    def _pick_echo2(self, raw: str, echo: str) -> str:
        """第二个片段：优先取自与 echo 同一次的对立切分。"""
        a, b = self.split_pair(raw)
        if a and b:
            return b if a == echo else (a if b == echo else b)
        others = [c for c in self.clauses(raw) if c != echo and len(c) >= 4]
        return max(others, key=len) if others else ""

    # -------------------------------------------------------- 追问的锚点
    #
    # 这一节是**用户实测排序逼出来的**。用户对三种回应给的活人感排序是
    #   「发生什么了？」(好) > 同一句用在没有具体对象的话上(中) > 「你当时怎么想的？」(勉强擦边)
    # 并指出关键：第 9 轮那句空转，因为用户当时在说"我现在喜欢什么"，根本没有"当时"。
    #
    # 结论：**活的不是句子，是句子有没有接住对方真说过的具体东西。**
    # 所以 ASK_DETAIL 必须能引用用户原话里**逐字存在**的具体成分，
    # 而这仍然只是字面匹配 —— 不做语义理解（[E] 最低限度推理）。
    _ANCHOR_PERSON = ("爸", "妈", "父母", "孩子", "儿子", "女儿", "老婆", "丈夫",
                      "老公", "妻", "哥", "姐", "弟", "妹", "朋友", "同事", "领导",
                      "老师", "同学", "他", "她", "对象", "恋人", "伴")
    _ANCHOR_THING = ("工作", "项目", "考试", "面试", "合同", "钱", "房子", "车",
                     "身体", "病", "学", "毕业", "搬家", "结婚", "离婚", "辞职")
    _ANCHOR_TIME = ("那天晚上", "那天", "小时候", "当年", "以前", "后来", "有一次",
                    "那年", "前几天", "前天", "上周", "昨天", "今天", "刚才")
    _ANCHOR_PLACE = ("老家", "学校", "公司", "医院", "家里", "路上", "外面")

    def _pick_anchor(self, raw: str) -> tuple[str, str]:
        """从用户原话里找一个**逐字存在**的具体锚点。返回 (类型, 片段)。

        类型优先级按实测的活人感排：
          time > person > thing > place > ""（无锚点）
        为什么 time 排最高：用户第 9 轮的空转正是因为"当时"不存在。
        所以在真的出现了时间词（"那天""小时候"）时问"当时"，才是接住了东西；
        没有时间词时问"当时"，是空转。

        ⚠️ 同一类里**取最长匹配**，并且**允许把前面的"我／我的"一起带上**。
        第一版按词表顺序取第一个命中的，结果用户说"我爸"，锚点却抓到"爸"，
        于是输出「你刚才说的『爸』，发生什么了？」——
        引用得不完整，读起来像系统自作主张替他改了称呼。
        引用对方的话必须**一字不改、能引多全就引多全**（"我爸"好过"爸"）。
        """
        t = raw or ""
        for kind, lex in (("time", self._ANCHOR_TIME),
                          ("person", self._ANCHOR_PERSON),
                          ("thing", self._ANCHOR_THING),
                          ("place", self._ANCHOR_PLACE)):
            best = ""
            for w in lex:
                # 允许把紧挨在词前的"我／我的／他／她的"等一起带上（原话逐字，不改写）
                m = re.search(r"([我你他她它]{0,2}的?)" + re.escape(w), t)
                if m:
                    cand = m.group(0)
                    # 守卫：锚点不得以虚词开头。否则"喜欢的工作"会被切成「的工作」，
                    # 引用出来读着像截断的（实测第一版就是这个错）。
                    while cand and cand[0] in "的了在是有和跟对把被就也还":
                        cand = cand[1:]
                    if len(cand) > len(best):
                        best = cand
            if best:
                return kind, best
        return "", ""

    def _pick_ask_detail(self, raw: str) -> str:
        """选一条追问。

        ⚠️ 这里**不走通用的模板轮换**（见 render 里的说明）：轮换会让"活不活"变成运气。

        ⚠️ 措辞规则改过一次，很重要：第一版对"人"类锚点生成的是
        「爸那边，发生什么了？」（把用户的"我爸"擅自缩成"爸"当昵称）。
        这个写法**太油** —— 像在硬套近乎。追问他人的事时，正确做法是
        **引用用户自己用的说法，一个字都不改**：
        「你刚才说的『我爸』，发生什么了？」
        差别在于：前者是系统自来熟，后者是系统在**核对**它听懂的是不是那件事。
        后者还给了用户一个纠正的机会（"不是我爸，是我妈"），前者没有。

        同时保留了用户实测的活人感排序：一句能接住具体东西的追问，
        永远好过一句对谁都能说的空转话。
        """
        kind, anchor = self._pick_anchor(raw)
        if not anchor:
            # 没有锚点：这一档就是用户排"中"的那一档 —— 句子对，但接不住具体的东西。
            # 仍用"发生什么了？"，因为它是**开口最轻**的一句（用户把它排第一）；
            # 而"你当时怎么想的？"在没有时间锚点时是空转的（用户第 9 轮的判定），已弃用。
            return "发生什么了？"
        # 有锚点：引用用户原话里的那个词，一字不改，然后轻轻问一句。
        if kind == "time":
            return "你刚才说的「%s」——当时发生什么了？" % anchor
        if kind == "person":
            return "你刚才说的「%s」，发生什么了？" % anchor
        if kind == "thing":
            return "你刚才说的「%s」是怎么回事？" % anchor
        return "你刚才说的「%s」——那是怎么回事？" % anchor

    @staticmethod
    def split_pair(raw: str) -> tuple[str, str]:
        """在一对对立观念之间切开；切不开则返回 ('', '')。"""
        for m in PAIR_HEADS:
            if m in raw:
                a, b = raw.split(m, 1)
                b = b.strip("，、。 ")
                for t in ("另一方面", "但有时候", "可是又", "但", "又", "也"):
                    if b.startswith(t):
                        b = b[len(t):]
                        break
                b = b.strip("，、。 ")
                if len(a.strip()) >= 3 and len(b) >= 3:
                    return a.strip("，、。 "), b
        for t in ("另一方面", "但有时候", "可是又"):
            if t in raw:
                a, b = raw.split(t, 1)
                if len(a.strip()) >= 3 and len(b.strip()) >= 3:
                    return a.strip("，、。 "), b.strip("，、。 ")
        for c in CONTRAST:
            if c in raw:
                a, b = raw.split(c, 1)
                if len(a.strip()) >= 3 and len(b.strip()) >= 3:
                    return a.strip("，、。 "), b.strip("，、。 ")
        return "", ""

    def _pick_must(self, raw: str, evidence: list[str]) -> str:
        """找出含『必须／一定』的那一句 —— [E] 布莱西：责任心的关键因素是『一定』。"""
        keys = ["必须", "一定", "非", "只能"]
        for c in self.clauses(raw):
            if any(k in c for k in keys):
                return c
        return evidence[0] if evidence else ""

    def _split_immutable(self, raw: str) -> tuple[str, str]:
        """把处境切成不可改变与可改变两部分。"""
        for conn in CONTRAST:
            if conn in raw:
                a, b = raw.split(conn, 1)
                return a.strip("，。 "), b.strip("，。 ")
        cs = self.clauses(raw)
        if len(cs) >= 2:
            return cs[0], cs[1]
        return (cs[0] if cs else ""), ""

    # -------------------------------------------------------- 选择

    def choose(self, markers: list[str], evidence: dict,
               raw: str, preferred: str | None = None) -> str:
        """按阶梯选择行为；阶梯见 behaviors.json.selection_rules.ladder。

        ⚠️ 2026-10-28 改：原来这里是**硬编码四个标记**——

            if cond.startswith("opposed_pair") and "opposed_pair" in ms: ...
            if cond.startswith("immutable")    and "immutable" in ms:    ...
            if cond.startswith("present_missing") and ...:              ...
            if cond.startswith("over_intention") and ...:               ...

        于是**在 behaviors.json 里加一条阶梯规则是无效的**：代码不认识那个 `when`，
        直接滑到「其余情形」⇒ REFLECT。实测：给 `cliche` 加了 `→ REPLENISH`，
        行为仍是 REFLECT，输出仍是「你用了这样一句话：……」。

        改成**通用判据**：`when` 的第一段就是标记名，该标记命中即采纳。
          · "opposed_pair 命中"                    → head = opposed_pair
          · "cliche 命中（套话/泛泛评价…）"          → head = cliche
          · "present_missing 命中（fuel_priority）" → head = present_missing
        两种特殊形态（must 片段 / 其余情形）仍单独处理。

        ⇒ 从此加标记规则只改 JSON，不改代码。
        """
        ms = set(markers)
        if preferred and preferred in self._b:
            return preferred
        for step in self.cfg["selection_rules"]["ladder"]:
            cond = step["when"]
            if cond.startswith("存在可追问的 must"):
                if self._pick_must(raw, evidence.get("over_intention", [])):
                    return step["pick"]
                continue
            if cond.startswith("其余情形"):
                return step["pick"]
            # 通用：`when` 的首段即标记名（去掉"命中"、"（…）"等修饰）
            head = cond.split()[0].split("（")[0].strip()
            if head and head in ms:
                return step["pick"]
        return "REFLECT"

    # -------------------------------------------------------- 渲染

    def render(self, behavior_id: str, raw: str, markers: list[str],
               evidence: dict | None = None, extra: dict | None = None) -> Render:
        evidence = evidence or {}
        extra = extra or {}
        b = self._b[behavior_id]

        echo = self._pick_echo(raw, set(markers))
        slots = {
            "echo": echo,
            "echo2": self._pick_echo2(raw, echo),
            "must": self._pick_must(raw, evidence.get("over_intention", [])),
            # 追问的锚点句：由 _pick_ask_detail 按用户原话里**逐字存在**的
            # 时间／人／物／地点算出来。见 _pick_anchor 的注释（用户实测排序逼出来的）。
            "ask_detail": self._pick_ask_detail(raw),
        }
        ip, cp = self._split_immutable(raw)
        slots["immutable_part"], slots["changeable_part"] = ip, cp
        slots.update(extra)

        # 业务闸门：禁止提升的情形下，若选中提升型行为则降级为 REFLECT
        #
        # ⚠️ 这里降级时必须**留痕**（`downgraded_from`），否则调用方无法区分
        #    "真的是复述" 与 "选中的行为被闸门降级成了复述"。
        #    实测后果：pipeline 写的"缺槽位退让链"（ASK_MUST → ASK_DETAIL → REFLECT）
        #    永远不生效 —— 因为 ASK_MUST 被这里静默换成 REFLECT 之后，
        #    调用方看到的只是"渲染成功，行为=REFLECT"，根本没有退化可退。
        #    于是「我一定要得到那个结果」「我其实特别想接下来」这类明明有话可问的轮次，
        #    仍然只会复述 —— 那正是用户判定的"牛头不对马嘴"。
        downgraded_from = None
        gate = self.cfg["selection_rules"]["_forbidden_escalation"]
        if behavior_id in [x for x in self._b if self._b[x].get("pacer_eligible")]:
            if any(m in set(markers) for m in gate["conditions"]):
                downgraded_from = behavior_id
                b = self._b["REFLECT"]
                behavior_id = "REFLECT"

        # 模板轮换（这是被 A/B 对照逼出来的修正）：
        #   原先这里永远取**第一条**满足槽位的模板，于是 REPLENISH 的 3 条模板里
        #   只有第 1 条被用过 —— A/B 实测中机制层连续 7 轮给出的是**同一句话**，
        #   看起来像坏掉的唱片。这不是模板不够，是选择器有缺陷。
        #
        #   修法：按**确定性**规则轮换。用 (行为, 原始文本, 该行为的调用序号) 做种子，
        #   同一个输入在同一轮仍然给同一条（可复现、可追溯、可写进台账），
        #   但同一个行为在不同轮次会轮到不同措辞。
        #   不用随机数：那会破坏"同一输入可复现"这条纪律。
        #
        # ⚠️ 但 ASK_DETAIL **不参与这个轮换**（用户实测排序逼出来的）：
        #   通用轮换按 (行为, 原文) 哈希取模，而池子里"发生什么了？"与"你当时怎么想的？"
        #   权重相同 —— 于是这个行为活不活变成了**运气**。用户实测里最活的那一句
        #   恰好被换成了最空的那一句（第 9 轮空转）。
        #   现在 ASK_DETAIL 只有一条模板 {ask_detail}，内容由 _pick_ask_detail 按锚点算，
        #   所以循环走到它时天然只有一条候选，不参与随机化。
        cands = []
        for tpl in b["templates"]:
            need = re.findall(r"\{(\w+)\}", tpl)
            if all(slots.get(n) for n in need):
                cands.append(tpl)
        if cands:
            self._render_count[behavior_id] = self._render_count.get(behavior_id, 0) + 1
            salt = sum(ord(c) for c in (raw or "")) + self._render_count[behavior_id]
            tpl = cands[salt % len(cands)]
            need = re.findall(r"\{(\w+)\}", tpl)
            out = tpl
            for n in need:
                out = out.replace("{%s}" % n, slots[n])
            how = ("模板满足全部槽位" if len(cands) == 1
                   else "模板满足全部槽位（%d 条中按确定性轮换取第 %d 条）"
                        % (len(cands), cands.index(tpl) + 1))
            return Render(behavior_id, out, {n: slots[n] for n in need}, how, b["source"],
                          downgraded_from=downgraded_from)

        # 无模板可用 → SILENCE（[M] 无话可说时不必说话）
        sb = self._b["SILENCE"]
        return Render("SILENCE", sb["templates"][0], {}, "无可用槽位", sb["source"],
                      silenced=True, downgraded_from=downgraded_from)


if __name__ == "__main__":
    r = Responder()
    for txt, ms, ev in [
        ("大家都说该这样，但我不这么看。一方面我想留，另一方面我又想走。",
         ["opposed_pair", "group_sanction"], {}),
        ("我一定要做到，我必须证明给他们看。", ["over_intention"], {"over_intention": ["我必须证明"]}),
        ("他已经走了，再也回不来了。虽然这样，但我可以选择怎么过下去。",
         ["immutable", "attitude_clause"], {}),
    ]:
        bid = r.choose(ms, ev, txt)
        out = r.render(bid, txt, ms, ev)
        print("[%s] %s" % (out.behavior, out.output.replace("\n", " / ")))

# -*- coding: utf-8 -*-
"""话题管理：让话题服务于人，而不是人服务于话题

改动理由（来自一次真实使用的观察）：
  用户连续两次转向（"你是谁"、"为什么人总是在分别与重逢中度过"），
  系统两次都答对了，但**立刻抛下一道题**，把用户带进来的东西丢掉了。

理论依据
  [M] 意义疗法：**"生命对每个人都提出了问题，他必须通过对自己生命的理解来回答生命的提问。"**
      → 问题是被人带来的，不是被系统派发的。
  [M] 眼科医生不是画家：系统该跟着当前的东西，不该按自己的脚本推进。
  [E] 最低限度推理：不要因为"该问下一题"就制造一个新话题。

三条规则
  R1  用户带进来的话题优先（若能对应到任一话题域）
  R2  话题不再机械推进：只有"答到题上"了才换题
  R3  系统以**用户回访**为准来认知什么对用户重要，而不是以自己问过什么为准
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RULES_DIR = os.path.join(_ROOT, "rules")


# 话题域：把用户的自然语言映射到话题库的某一段。
#
# 关键区分（一次真实失败教会的）：
#   这是**路由**用的词表，不是**判定**用的词表。
#   路由判错了，代价只是问错一道题，用户一句"跳过"就能纠正；
#   判定（markers.json）判错了，代价是污染水平证据。
#   所以这里可以宽、可以按核心语素匹配；markers.json 那边必须严、必须逐字。
#   教训来源：用户说"没睡好"，而词表里只有"睡不着" —— 汉字派生太灵活，整词匹配必漏。
DOMAINS = {
    "LOSS": {
        "label": "丧失与不可挽回",
        "topics": ["T20", "T21", "T22", "T23", "T24", "T25"],
        "keywords": ["走", "失去", "死", "分别", "重逢", "离开", "没了", "回不来",
                     "过去", "后悔", "来不及", "再也", "改变不了", "丧", "逝", "散"],
    },
    "FATIGUE": {
        "label": "耗竭与恢复",
        "topics": ["T36", "T19", "T05"],
        "keywords": ["累", "熬", "撑不住", "没力气", "疲", "睡", "烦", "没意思",
                     "不想说", "算了", "倦", "耗", "麻", "药"],
    },
    "RELATION": {
        "label": "与他人的关系",
        "topics": ["T09", "T10", "T14", "T26", "T27", "T30", "T31"],
        "keywords": ["朋友", "妈", "爸", "父母", "同事", "他对我", "她对我", "别人对我",
                     "亲近", "信任", "背叛", "帮忙", "家人", "恋人", "伴"],
    },
    "DESIRE": {
        "label": "想要与得不到",
        "topics": ["T10", "T35", "T29"],
        "keywords": ["想要", "想得到", "一定要", "得不到", "渴望", "非要", "必须得到",
                     "贪", "上瘾", "戒不掉"],
    },
    "SELF": {
        "label": "自己是谁",
        "topics": ["T06", "T07", "T19", "T32", "T34"],
        "keywords": ["我是谁", "我自己", "我这个人", "为什么我", "我总觉得", "我到底",
                     "我是", "到底想", "值不值"],
    },
    "RULE_MORAL": {
        "label": "规则与对错",
        "topics": ["T02", "T09", "T18", "T31"],
        "keywords": ["规则", "应该", "不该", "对错", "公平", "不公平", "诚实", "骗",
                     "凭什么", "道理"],
    },
    "THINKING": {
        "label": "想法与选择",
        "topics": ["T15", "T16", "T17", "T18", "T33"],
        "keywords": ["想不通", "矛盾", "纠结", "一方面", "两方面", "选哪个", "怎么办",
                     "为什么", "意义", "值得"],
    },
}

MIN_LEN_FOR_ANSWER = 6          # 短于此长度不足以判定"答到题上"（ENG）
SKIP_WORDS = ["跳过", "换一题", "下一题", "不想答这个", "换个话题"]


@dataclass
class TopicState:
    current: str | None = None
    answered_current: bool = False
    visited: list[str] = field(default_factory=list)
    user_domains: dict = field(default_factory=dict)   # 域 → 出现次数（**用户带进来的**）
    system_domains: dict = field(default_factory=dict)  # 域 → 系统问过的次数
    skip_requested: bool = False

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class TopicManager:
    def __init__(self, topics: list[dict]):
        self.topics = {t["id"]: t for t in topics}
        self.order = [t["id"] for t in topics]
        self._i = 0
        self.st = TopicState()

    # ---------------------------------------------------------- 域识别

    @staticmethod
    def detect_domains(text: str) -> list[str]:
        t = text or ""
        hits = []
        for dom, spec in DOMAINS.items():
            for kw in spec["keywords"]:
                if kw in t:
                    hits.append(dom)
                    break
        return hits

    def topics_of(self, domain: str) -> list[str]:
        return [x for x in DOMAINS[domain]["topics"] if x in self.topics]

    def next_unvisited(self) -> str:
        for tid in self.order:
            if tid not in self.st.visited:
                return tid
        return self.order[self._i % len(self.order)]

    # ---------------------------------------------------------- 主决策

    # ---------------------------------------------------------- 选中即入册
    #
    # ⚠️ 这一条是实测抓出来的 bug 的修法。
    #   `visited` 原先只在**离开**一道题时才 append，于是：
    #     · 当前正在问的那道题从未入册 → 之后选"下一个没答过的"时它又被挑中（**倒退**）
    #     · 同一道题可能被 append 两次（离开时一次、跟随用户时又一次）→ **重复**
    #   实测的进度文件：{"visited": ["T02", "T09", "T09"], "current": "T01"}
    #   —— 有重复、缺 T01，用户于是从 T09 被问回了 T01。
    #
    #   改法：`visited` 的含义是「**已经用过的**」，不是「已经答完的」。
    #         所以**一被选中就入册**。
    def _select(self, topic_id: str) -> None:
        self.st.current = topic_id
        if topic_id and topic_id not in self.st.visited:
            self.st.visited.append(topic_id)
        self.st.answered_current = False

    def _on_topic(self, text: str) -> bool | None:
        """这句话跟当前题面有没有关系？

        返回 True／False，判不出来返回 None（不看字面重合）。
        **这是路由层的判断，代价只是问错一道题** —— 按「三·补四」定的纪律，
        路由词表可以宽、可以按核心语素匹配；判定词表必须严。

        为什么要它（实测抓到的真错）：
          判"答到题上"原先只看 `intent==ANSWER 且长度≥6`，
          **压根没看这句话跟题目有没有关系**。于是：
            「今天天气不错。」→ 被判成"已答到题上 → 换下一题"。
          这是显然的错：它答的是天气，不是题面。
        """
        t = (text or "").strip()
        stem = (self.topics.get(self.st.current or "") or {}).get("stem", "")
        if not t or not stem:
            return None
        # 题面的实义字（去虚词与标点）。汉字逐字重合 —— 粗糙但可解释。
        STOP = set("我你他她它的了是在有和与或而就都也还很不在这个那个么呢吧"
                   "什么怎样会要能可一个件事当如果时候做想")
        chars = {c for c in stem if "\u4e00" <= c <= "\u9fff"} - STOP
        if not chars:
            return None
        hit = sum(1 for c in set(t) if c in chars)
        return hit >= 2          # 至少两个实义字与题面重合

    def decide(self, text: str, intent: str) -> dict:
        """返回本次应问什么，以及为什么。

        这是 R1/R2/R3 的落点。
        """
        t = (text or "").strip()
        domains = self.detect_domains(t)
        for d in domains:
            self.st.user_domains[d] = self.st.user_domains.get(d, 0) + 1

        # R2a：用户明确要求换题，**但同时带进来了自己的话题** → 跟他的，不是随便换一道
        # 实测：「我不想答这个，我其实在想我爸。」原先只当"要求换题"，
        # 于是换成了一道无关的题，把他带进来的东西丢了。
        if any(w in t for w in SKIP_WORDS):
            cur_domains0 = [d for d, s in DOMAINS.items() if self.st.current in s["topics"]]
            own = [d for d in domains if d not in cur_domains0]
            if own:
                cands = [x for x in self.topics_of(own[0]) if x not in self.st.visited]
                if cands:
                    self._select(cands[0])
                    self.st.skip_requested = True
                    return {"topic_id": self.st.current, "action": "FOLLOW_USER",
                            "reason": "他说不答这个，但带进了自己的话题：%s（R1 优先于换题）"
                                      % DOMAINS[own[0]]["label"],
                            "domain": own[0]}
            self._select(self.next_unvisited())
            self.st.skip_requested = True
            return {"topic_id": self.st.current, "action": "SKIP",
                    "reason": "用户要求换题"}

        # R2b：判定是否"答到题上"
        # ⚠️ 加上了 `_on_topic` —— 只判长度会把"今天天气不错"当成答到题上（实测）。
        on = self._on_topic(t)
        engaged = (intent == "ANSWER") and len(t) >= MIN_LEN_FOR_ANSWER and (on is not False)
        if engaged:
            self.st.answered_current = True

        # R1：用户带进来的域优先 —— 跟它，除非它就是当前话题所在域
        cur_domains = [d for d, s in DOMAINS.items() if self.st.current in s["topics"]]
        new_domains = [d for d in domains if d not in cur_domains]

        if new_domains and (not engaged or len(new_domains) > 0):
            dom = new_domains[0]
            cands = [x for x in self.topics_of(dom) if x not in self.st.visited]
            if cands:
                self._select(cands[0])
                return {"topic_id": self.st.current, "action": "FOLLOW_USER",
                        "reason": "跟随用户带进来的域：%s" % DOMAINS[dom]["label"],
                        "domain": dom}

        # R2c：答到题上了 → 本话题完成，换下一题
        if engaged and self.st.answered_current:
            self._select(self.next_unvisited())
            return {"topic_id": self.st.current, "action": "ADVANCE",
                    "reason": "已答到题上 → 换下一题"}

        # R2d：没答到题上（元提问、太短、跑题）→ **保留当前话题**
        if self.st.current is None:
            self._select(self.next_unvisited())
            return {"topic_id": self.st.current, "action": "START",
                    "reason": "起始题"}
        return {"topic_id": self.st.current, "action": "HOLD",
                "reason": "本轮未答到题上 → 保留当前话题（不推进）"}

    # ---------------------------------------------------------- R3

    def priority_map(self) -> dict:
        """以**用户回访**为准的重要性排序，而不是以系统问过什么为准。

        [M]：问题是被人带来的，不是被派发的。
        """
        rows = []
        for dom, spec in DOMAINS.items():
            u = self.st.user_domains.get(dom, 0)
            s = self.st.system_domains.get(dom, 0)
            rows.append({"domain": dom, "label": spec["label"],
                         "user_brought": u, "system_asked": s,
                         "user_over_system": round(u / s, 2) if s else None})
        rows.sort(key=lambda r: (-r["user_brought"], r["label"]))
        return {"rows": rows,
                "note": "user_brought 高而 system_asked 低的域，是系统一直没跟上的地方"}

    def mark_asked(self, topic_id: str | None) -> None:
        if not topic_id:
            return
        for dom, spec in DOMAINS.items():
            if topic_id in spec["topics"]:
                self.st.system_domains[dom] = self.st.system_domains.get(dom, 0) + 1

    # ---------------------------------------------------------- 进度持久化
    #
    # 为什么需要（实测的真 bug）：
    #   用户答了 T02 的题（答得完整、就在题上），**重启后 T02 又出现了**。
    #   查出来是启动逻辑的问题：
    #       last_topic = ledger.entries[-1].topic_id    ← 算出来了
    #       self.topic_id = self.p.next_topic()          ← 然后没用它，按计数器轮转
    #   于是**每次重启，话题进度就重置一次**，T02 反复出现。
    #   这不是"它不当你是答了"，是"它关机就忘了你答到哪"。
    #
    #   与性格层同一个道理：没有跨会话的记忆就不是"记得"，只是"这一轮还在"。
    def save_progress(self, path: str) -> None:
        d = {"current": self.st.current, "visited": self.st.visited,
             "answered_current": self.st.answered_current,
             "user_domains": self.st.user_domains,
             "system_domains": self.st.system_domains}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    def load_progress(self, path: str) -> bool:
        """恢复上次的话题进度。返回是否成功恢复。"""
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return False
        if d.get("current") in self.topics:
            self.st.current = d["current"]
            self.st.visited = [t for t in (d.get("visited") or []) if t in self.topics]
            self.st.answered_current = bool(d.get("answered_current"))
            self.st.user_domains = dict(d.get("user_domains") or {})
            self.st.system_domains = dict(d.get("system_domains") or {})
            return True
        return False


if __name__ == "__main__":
    import io
    p = os.path.join(os.path.dirname(_RULES_DIR), "corpus", "topics.json")
    topics = json.load(io.open(p, encoding="utf-8"))["topics"]
    tm = TopicManager(topics)
    seq = [("当我想做一件事，而这件事会耽误别人的时候，我……", "ANSWER", "（起始）"),
           ("你是谁", "META", "演示：元提问不该推进话题"),
           ("为什么人总是在分别与重逢中度过", "ANSWER", "演示：用户带进 LOSS 域"),
           ("我已经三个月没睡好了", "ANSWER", "演示：用户带进 FATIGUE 域"),
           ("跳过", "ANSWER", "演示：显式换题")]
    for text, intent, note in seq:
        d = tm.decide(text, intent)
        tm.mark_asked(d["topic_id"])
        stem = tm.topics[d["topic_id"]]["stem"]
        print("%-14s → [%s] %s" % (d["action"], d["topic_id"], stem))
        print("                 理由：%s  ｜%s" % (d["reason"], note))
    print()
    print(json.dumps(tm.priority_map(), ensure_ascii=False, indent=1))

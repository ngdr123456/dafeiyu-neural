# -*- coding: utf-8 -*-
"""L6 台账层

职责：让每一条判定都可追溯、可推翻，并记录一条**不可删除**的反事实条目。

理论依据
  [E] 手册修订：『当样本被扩大时，有些反应会重复出现，但是，随后又会出现新的独特的反应。』
  [M] 绝对命令：『要像是在经历第二次生命，仿佛你已经获得重生；再不要像过去那样，一定要避免犯同样错误！』
  [M] 『曾经存在是最为确定的一种存在。』

存储：JSONL（每行一条），纯标准库，人类可读可审。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


LEDGER_FIELDS = (
    "turn_id", "topic_id", "channel", "markers_fired", "marker_evidence",
    "rule_ids", "confidence", "conflict", "relation", "behavior", "output",
    "counterfactual", "gear_id", "s_used", "notes", "era", "intent",
)

DEFAULT_ERA = "E1"

# 同时含"不生成"与"元回应"两组行为。
# META_REPLY 不是生成，它取自 rules/meta_responses.json 的模板 ——
# 它属于允许集合，是因为**系统的说话方式也必须可审计**。
ALLOWED_BEHAVIORS = {
    "REFLECT", "JUXTAPOSE", "ASK_MUST", "TURN_IMMUTABLE", "REPLENISH", "SILENCE",
    "META_REPLY",
    # ---- E3 世代新增（见 rules/behaviors.json 各自的 _note）
    # ASK_DETAIL       想知道 —— 系统此前完全缺失的成分
    # ACKNOWLEDGE      承认（温暖但不评判）—— 判据：承认有分量 vs 规定什么算重要
    # REPORT_OWN_STATE 如实说出系统自己的状态（"以自我为中心"的落点）
    # 三者仍是**模板组装**，不是生成。
    "ASK_DETAIL", "ACKNOWLEDGE", "REPORT_OWN_STATE",
    # ACKNOWLEDGE_CLOSE 承认收尾 —— 只说系统自己停下，不对用户的决定表态
    "ACKNOWLEDGE_CLOSE",
    "QUESTION", "UNCLASSIFIED",  # final generated action: literal question or unconfirmed semantics
    # ★ 2026-10-31（用户裁定）：**兜底轮单列 `FALLBACK`**。
    #   大脑失败退兜底时，`actual` 记成它 —— 不进 QUESTION / ASK_DETAIL，
    #   也不算 BOLD 探照（见 association._is_bold）。
    "FALLBACK",
    # ★ 2026-10-29（C5）：跨轮思考算子层的执行核对。
    #   `THOUGHT_EXECUTED_STRONG`：算子引用的**两段**原话都在输出里逐字出现
    #   ⇒ 她真的把那两处拉扯都摆出来了 ⇒ **confirmed**
    #
    #   ⚠️ 原本还有一个 `THOUGHT_EXECUTED_WEAK`（只命中一段，confirmed=False）。
    #     实测 16 条真实输出后**删掉了**这个 actual：
    #       分布是 STRONG 8｜QUESTION 5｜REPORT_OWN_STATE 1｜UNCLASSIFIED 2
    #       ⇒ WEAK **一次都没落** —— "只用了碎片"的三种情况
    #         全都以问号结尾或含"我答不了"，被 QUESTION / REPORT_OWN_STATE 先抓走。
    #     ⇒ 那个诊断信息改记在 `action_observation.thought_level` 这个**独立字段**里
    #       （STRONG / WEAK / ""），`actual` 的语义因此保持干净。
    "THOUGHT_EXECUTED_STRONG",
    # ★ 2026-10-28：与上面两个同一类（final generated action），但**是已确认的**。
    #   依据：`self_goal.literal_check()` 会在输出里找「」引号片段，逐段比对
    #   目标要求的 evidence 是否逐字出现。找不到就 matched=False。
    #   ⇒ 它证明的是「你确实逐字引用了指定的来源」，是**本地核对**，不是语义猜测。
    #
    #   为什么需要它：大脑路径原来除纯问句外全记为 UNCLASSIFIED，
    #   于是 experience.py 一条事件都不产生、association 也学不到 ——
    #   真实训练跑完，学到的东西是零（T37 note 的「全部实际动作仍为 UNCLASSIFIED」）。
    "QUOTE_SOURCE_SET_CONFIRMED",
}

# 世代分界是**追加记录**，不是删改历史。
# 依据 [E] 第九章：手册的三代形态为「样本手册 → 分类手册 → 合理分类手册」，
# 而判据一变，手册版本随之改变 —— 原书本来就是这么做的。
ERA_MARK = "__ERA_BOUNDARY__"


@dataclass
class LedgerEntry:
    turn_id: int
    topic_id: str | None
    channel: str                      # S | B | S+B(试探)
    markers_fired: list[str]
    marker_evidence: dict
    rule_ids: list[str]
    confidence: float
    conflict: bool
    relation: str
    behavior: str
    output: str
    counterfactual: str               # 不可删除
    gear_id: str | None = None
    s_used: str | None = None
    notes: list[str] = field(default_factory=list)
    era: str = DEFAULT_ERA            # 世代标记（不删条目，只标注）
    intent: str = "ANSWER"            # ANSWER | META | CLARIFY
    # 机制层状态（底层思维系统的数值快照）。None 表示该轮未启用机制层。
    # 存进来是 [E]『曾经存在是最为确定的一种存在』的要求：机制状态也必须可追溯，
    # 否则无法回答"系统当时为什么那样说"这个唯一重要的问题。
    mech: dict | None = None
    # ★ 用户的原话（E4 世代新增，见 spec/经历驱动的性格层_v1.md）。
    #
    # 为什么必须存（这是本文件最要紧的一处补充）：
    #   实测发现台账**从不记录用户说了什么**，只记系统自己说了什么。
    #   后果：任何以"用户的行为"为对象的分析都不可能做 ——
    #     用户答了没答、答得长不长、什么时候收的尾、有没有回到之前说过的东七、
    #     有没有把话题带到别处 …… 全部无从知晓。
    #   而"性格由经历塑造"要的恰恰是这些。**一个不记得对方说过什么的系统，
    #   不可能有性格，因为它连经历都没有。** 它不只是没有过去，它是失忆的。
    #
    # [E] 依据：『曾经存在是最为确定的一种存在。』—— 用户说的话也必须留下。
    raw_input: str = ""
    input_origin: dict | None = None
    planned_behavior: str | None = None
    action_observation: dict | None = None
    proposition_reading: dict | None = None
    self_action: dict | None = None
    # ★ 当轮检索范围（2026-10-28 新增，用户裁定）。
    #
    # 为什么必须存：实测台账 405 行里这一项 0 条 ⇒ 她**从不知道自己上一轮
    # 看得到多少**。后果是「同一件事，两次不同答案，而她不知道自己在变」——
    # 这不是记性差，是**没有连续的自我**（[E]：相继组织之间的连续性）。
    #
    # 存什么：memory_scope.describe() 的整包（含 same_domain_utterance_count /
    # matching_relation_utterance_known / complete_history_presented）。
    # 它只描述**当时的检索范围**，不含姓名或答案，不构成对世界的断言。
    memory_scope: dict | None = None
    # ★ 作废标记（E5 世代新增）。非空 = 该条**不计入任何统计**，值写明作废理由。
    #
    # 为什么是"标注"而不是"删除"（这条必须写清，否则后人会直接删行）：
    #   台账存在的全部理由是 [M]『曾经存在是最为确定的一种存在』。
    #   删掉一行，就没人知道它曾经被记进来过、也没人知道它为什么不该在 ——
    #   那正好毁掉台账唯一的功能。所以作废只标注，统计跳过它，历史原样留着。
    #
    # 实测来由：有 4 条 `/quit` 被当成对话记进了台账 ——
    #   用户在 cmd 里粘贴命令时带了 U+FEFF（BOM），命令识别没剥零宽字符，
    #   于是 `/quit` 被当作一轮对话，还生成了输出「你刚才说的是：「﻿/quit」。」。
    #   入口已修（shell 剥零宽），但**历史 4 条仍在**，且会进 /character 的统计。
    void: str = ""
    # ★ 近零内容轮（如单字「?」「嗯。」）：**不排除**，单独计数并在报告里显式列出。
    #   为什么不像 void 那样排除：排除等于替使用者决定"哪句话算数" ——
    #   而判据不该拿使用者的随手动作用来解释（[E] 最低限度推理）。
    #   标出来、让它可见，比偷偷减掉诚实。
    low_content: bool = False
    # ★ 2026-10-29（C2）：跨轮思考算子层在本轮的产出。**可选**，历史行为 None。
    #
    #   形状（由 `engine/cognition_ops.Thought.as_dict()` 决定）：
    #     {"op": 算子 ID, "quotes": [两段逐字原话], "hint": 给大脑的结构简报,
    #      "yielded": [也触发但被让位的算子 ID]}
    #
    #   ⚠️ 为什么必须记 `yielded`：五个算子一起上时假阳性会堆叠，
    #      "哪几个也触发了但被让位"是事后查假阳性的**唯一依据**。
    #   ⚠️ 为什么记 `quotes` 而不只记 `op`：`C5` 的本地核对只认这两段逐字命中，
    #      台账里必须留着当初核对的是哪两段 —— 否则事后无法复算"她到底执行了没有"。
    cognition: dict | None = None
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class Ledger:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        if not os.path.exists(self.path):
            open(self.path, "a", encoding="utf-8").close()
        self._entries: list[LedgerEntry] = []
        self._boundaries: list[dict] = []
        self._era = DEFAULT_ERA
        self._load()

    # ------------------------------------------------------------ IO

    def _load(self) -> None:
        self._entries = []
        self._boundaries = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if d.get(ERA_MARK):
                    self._boundaries.append(d)
                    self._era = d.get("era", self._era)
                    continue
                known = {k: d.get(k) for k in LedgerEntry.__dataclass_fields__ if k in d}
                known.setdefault("era", DEFAULT_ERA)
                self._entries.append(LedgerEntry(**known))

    def append(self, entry: LedgerEntry) -> None:
        if not entry.counterfactual:
            raise ValueError("counterfactual 不得为空 —— [M] 绝对命令要求每轮留下一条『若重来会改哪一步』")
        if entry.behavior not in ALLOWED_BEHAVIORS:
            raise ValueError("未知行为：%s" % entry.behavior)
        if not entry.era:
            entry.era = self._era
        self._entries.append(entry)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    # ------------------------------------------------------------ 世代

    @property
    def era(self) -> str:
        return self._era

    def new_era(self, tag: str, reason: str) -> dict:
        """开启新一代。**只追加一条分界记录，绝不删改任何历史条目。**

        依据 [E] 第九章：判据一变，手册版本随之改变（样本手册 → 分类手册 → 合理分类手册）；
        以及 [M]『曾经存在是最为确定的一种存在』。
        """
        if not tag or not reason:
            raise ValueError("新时代必须同时给出 tag 与 reason（理由不可省略）")
        rec = {
            ERA_MARK: True,
            "era": tag,
            "reason": reason,
            "after_turn": self.turns(),
            "previous_era": self._era,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._boundaries.append(rec)
        self._era = tag
        return rec

    def boundaries(self) -> list[dict]:
        return list(self._boundaries)

    def era_counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for e in self._entries:
            c[e.era] = c.get(e.era, 0) + 1
        return c

    # ------------------------------------------------------------ 查询

    @property
    def entries(self) -> list[LedgerEntry]:
        """**行**（含作废行）。要统计请用 effective_entries。"""
        return list(self._entries)

    @property
    def effective_entries(self) -> list[LedgerEntry]:
        """有效轮次：排除作废行。行为类统计用这个。"""
        return [e for e in self._entries if not e.void]

    @property
    def text_entries(self) -> list[LedgerEntry]:
        """有原话的有效轮次。**任何以"他说了什么"为对象的统计只能用这个。**

        为什么要与上面分开（这是本轮修的实测缺陷）：
          E1–E3 世代共 30 条**没有 raw_input 字段**（该字段 E4 才加）。
          它们是真轮次（有标记、有行为），所以**该进行为统计**；
          但它们没有原话，所以**不该进关联/文本统计**。
          原先只有 association.py 自己在内部过滤，别处拿不到这个口径，
          于是 /character 报出的分母（"配对 59 条"）与台账口径对不上、也没人说得清差在哪。
        """
        return [e for e in self._entries
                if not e.void and (e.raw_input or "").strip()]

    def voided(self) -> list[LedgerEntry]:
        return [e for e in self._entries if e.void]

    def denominators(self) -> dict:
        """把两个口径显式报出来，供上层如实标注分母。"""
        return {
            "rows": len(self._entries),
            "void": len(self.voided()),
            "effective": len(self.effective_entries),
            "with_text": len(self.text_entries),
            "low_content": len([e for e in self.effective_entries if e.low_content]),
            "no_text_but_valid": len(self.effective_entries) - len(self.text_entries),
        }

    def turns(self) -> int:
        """有效轮次（不含作废行）。行数用 len(entries)。"""
        return len(self.effective_entries)

    def marker_frequency(self) -> dict[str, int]:
        freq: dict[str, int] = {}
        for e in self.effective_entries:
            for m in e.markers_fired:
                freq[m] = freq.get(m, 0) + 1
        return freq

    def channel_counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for e in self.effective_entries:
            c[e.channel] = c.get(e.channel, 0) + 1
        return c

    def behavior_counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for e in self.effective_entries:
            c[e.behavior] = c.get(e.behavior, 0) + 1
        return c

    # ------------------------------------------------------------ 作废

    # 零宽字符。做命令判定前必须剥掉 —— 实测用户在 cmd 里粘贴时带了 U+FEFF，
    # `/quit` 因此没被识别成命令，被当成一轮对话记了进来。
    _ZW = "\ufeff\u200b\u200c\u200d\u2060\ufffd \t\r\n"

    def void_where(self, predicate, reason: str) -> int:
        """按条件把若干轮标为作废（**改行，不删行**）。返回改动行数。

        为什么按条件而不是按 turn_id：
          实测台账里 `turn_id` **不唯一**（每个会话从 1 重新计数），
          所以"作废 turn_id=1"会误伤几十条无关的行。
          条件式匹配把判据写在调用处，看得见、可复核。

        为什么必须有这个方法，而不是手工编辑 JSONL：
          手工改容易漏键、也容易手滑删行。这里只加 `void` 一个键，
          其余键**原样回写**（包括本模块不认识的键），并先留一份 .bak。
        """
        return self._rewrite_where(predicate, lambda d: d.update({"void": reason}),
                                   reason_required=reason)

    def _rewrite_where(self, predicate, mutate, reason_required: str = "") -> int:
        if reason_required is not None and not reason_required:
            raise ValueError("必须写明理由 —— 不写理由的改动，后人无法判断能不能翻案")
        import shutil
        bak = self.path + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(self.path, bak)
        out, hits = [], 0
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                d = json.loads(s)
                if (not d.get(ERA_MARK)) and predicate(d):
                    mutate(d)
                    hits += 1
                out.append(json.dumps(d, ensure_ascii=False))
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        self._load()
        return hits

    def void_command_rows(self, reason: str) -> int:
        """/命令残留：raw_input 剥掉零宽字符后以 "/" 开头。"""
        def pred(d):
            s = "".join(ch for ch in (d.get("raw_input") or "") if ch not in self._ZW)
            return s.startswith("/")
        return self.void_where(pred, reason)

    # 只用于"近零内容"判定，与 zero-width 分开命名，避免误用
    _PUNCT = "？?！!。.，,、；;：:~～…—-·「」『』\"'（）()"

    def mark_low_content(self, reason: str = "") -> int:
        """标出近零内容轮（剥掉标点后 ≤1 字，如「?」「嗯。」）。

        **不排除**，只标记 —— 见字段注释：排除等于替使用者决定"哪句话算数"。

        两个坑都踩过了，写在这里免得再犯：
          · `len(s) <= 1` 里的 **0 也要算**。「?」剥掉标点后长度为 0，
            它比「嗯。」内容更少，没有理由反而漏掉（第一版要求 `0 < len` 就漏了 6 条）。
          · **必须先判断字段是否存在**。E1–E3 那 30 条老条目根本没有 `raw_input` 键，
            取值得到空串 —— 那是"没记录"，不是"用户没说话"。
            第一版没判这个，一次标错 30 条（而我在当天的审计脚本里刚犯过同一个错）。
        """
        def pred(d):
            if d.get("void"):
                return False
            if "raw_input" not in d:
                return False          # ← 没有字段 ≠ 空输入
            s = "".join(ch for ch in (d.get("raw_input") or "") if ch not in self._ZW)
            s = "".join(ch for ch in s if ch not in self._PUNCT)
            return len(s) <= 1
        return self._rewrite_where(pred, lambda d: d.update({"low_content": True}),
                                   reason_required="low_content")

    def clear_low_content(self) -> int:
        """撤销 low_content 标记（只清这个键，不碰别的）。"""
        return self._rewrite_where(lambda d: bool(d.get("low_content")),
                                   lambda d: d.pop("low_content", None),
                                   reason_required="clear")

    # ------------------------------------------------------------ 自检

    # 删除类建议的最小样本门槛。
    # 为什么必须有：5 轮之后说"某标记从未触发"毫无意义 —— 那只是样本太小。
    # 依据本仓库 spec/认输清单.md 填写规则第 1 条：「数据不足」是合法且诚实的结论。
    # 取值与 L6 自检周期一致（36 轮 = 一次完整的 36 项目记录）。
    MIN_TURNS_FOR_DELETION = 36

    def self_audit(self, all_marker_ids: list[str]) -> dict:
        """每 36 轮执行一次（[E] 手册修订）。

        返回：从未触发的标记（**仅在样本足够时**建议删）、触发过频的标记（建议改）、
              以及按世代分组的频率 —— 因为 [E] 的手册修订正是
              『新样本是对旧类别的检验』，跨世代与世代内的意义不同。
        """
        freq = self.marker_frequency()
        n = max(1, self.turns())
        never = [m for m in all_marker_ids if freq.get(m, 0) == 0]
        data_sufficient = self.turns() >= self.MIN_TURNS_FOR_DELETION

        # 负相关粗检：某标记命中时，整体行为是否更常落到『禁止提升』的情形
        suppress = 0
        suppress_total = 0
        for e in self._entries:
            if any(m in e.markers_fired for m in ("immutable", "over_intention", "present_missing")):
                suppress_total += 1
                if e.behavior in ("REFLECT", "JUXTAPOSE", "TURN_IMMUTABLE", "REPLENISH", "SILENCE"):
                    suppress += 1

        overused = [m for m, c in freq.items() if c / n > 0.8] if data_sufficient else []

        # 按世代分组
        by_era: dict[str, dict] = {}
        for e in self._entries:
            slot = by_era.setdefault(e.era, {"turns": 0, "markers": {}, "behaviors": {}})
            slot["turns"] += 1
            for m in e.markers_fired:
                slot["markers"][m] = slot["markers"].get(m, 0) + 1
            slot["behaviors"][e.behavior] = slot["behaviors"].get(e.behavior, 0) + 1

        # 跨世代比较：只在两代**都**达到最小样本时才有意义
        cross_era_drift: dict[str, dict] = {}
        eras = list(by_era.keys())
        if len(eras) >= 2:
            first, last = eras[0], eras[-1]
            a, b = by_era[first], by_era[last]
            if a["turns"] >= self.MIN_TURNS_FOR_DELETION and b["turns"] >= self.MIN_TURNS_FOR_DELETION:
                for m in set(list(a["markers"]) + list(b["markers"])):
                    ra = a["markers"].get(m, 0) / max(1, a["turns"])
                    rb = b["markers"].get(m, 0) / max(1, b["turns"])
                    if abs(ra - rb) >= 0.15:
                        cross_era_drift[m] = {str(first): round(ra, 3), str(last): round(rb, 3)}

        suggestions: list[str] = []
        if data_sufficient:
            if never:
                suggestions.append("建议删除从未触发的标记：%s" % ", ".join(never))
            if overused:
                suggestions.append("建议修改触发过频的标记：%s" % ", ".join(overused))
            if cross_era_drift:
                suggestions.append("跨世代漂移显著：%s" % ", ".join(cross_era_drift))
        else:
            suggestions.append(
                "数据不足（%d/%d 轮）：不作删除类建议。"
                "「从未触发」在小样本上无意义 —— 见 spec/认输清单.md 填写规则第 1 条。"
                "当前仅收作基线：%s"
                % (self.turns(), self.MIN_TURNS_FOR_DELETION,
                   ", ".join(sorted(freq)) or "（无标记触发）"))

        return {
            "turns": self.turns(),
            "era": self._era,
            "data_sufficient": data_sufficient,
            "min_turns_for_deletion": self.MIN_TURNS_FOR_DELETION,
            "era_counts": self.era_counts(),
            "boundaries": self._boundaries,
            "marker_frequency": freq,
            "never_fired": never,
            "overused": overused,
            "suppression_rate": round(suppress / suppress_total, 3) if suppress_total else None,
            "channel_counts": self.channel_counts(),
            "behavior_counts": self.behavior_counts(),
            "by_era": {k: {"turns": v["turns"], "markers": v["markers"]} for k, v in by_era.items()},
            "cross_era_drift": cross_era_drift,
            "_actions_suggested": suggestions,
        }

    def counterfactuals(self) -> list[str]:
        """全部反事实条目 —— 按 [M]『曾经存在是最为确定的一种存在』，永不可删。"""
        return [e.counterfactual for e in self._entries]

    def rewrite_without_counterfactual(self, out_path: str) -> tuple[int, int]:
        """自检工具：验证反事实条目的不可删除性。

        返回 (保留条数, 被拦截条数)。被拦截 = 反事实为空、无法写出的条目。
        世代分界记录**不受反事实约束**（它不是判定，是历史标注），原样保留。
        """
        kept = blocked = 0
        with open(out_path, "w", encoding="utf-8") as f:
            for b in self._boundaries:
                f.write(json.dumps(b, ensure_ascii=False) + "\n")
            for e in self._entries:
                if not e.counterfactual:
                    blocked += 1
                    continue
                kept += 1
                f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")
        return kept, blocked


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "ledger.jsonl")
    lg = Ledger(p)
    print("台账条数:", lg.turns())
    print(json.dumps(lg.self_audit([]), ensure_ascii=False, indent=1))

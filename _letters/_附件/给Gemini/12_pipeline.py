# -*- coding: utf-8 -*-
"""六层管线：把 L1–L6 串起来

    L1 输入层  → 话题调度（含探针优先）
    L2 标记层  → MarkerEngine.parse
    L3 状态层  → StateLayer.update（区间 + 方向，冲突不平均）
    L4 档位引擎 → GearEngine.decide（S / B / 门控 / 疲劳 / 试探并行）
    L5 回应层  → Responder（六种言语行为，只组装不生成）
    L6 台账层  → Ledger（可追溯 + 反事实不可删 + 36 轮自检）
"""
from __future__ import annotations

import json
import copy
import os
import sys
from dataclasses import dataclass, field
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包成 exe 后 `__file__` 指向解包出的临时目录 —— 于是 rules/corpus 找不到，
# 而且**台账会写进临时目录、退出就丢**。所以允许用 EGO_ROOT 指定项目根，
# 由启动器（exe）在导入任何引擎模块之前设置。
# 不设 EGO_ROOT 时行为与从前完全一致（源码运行时就是这个分支）。
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path.insert(0, _HERE)

# ★ 箭头 A1 的通电开关 —— **全项目唯一的一处定义**
#
#   用户裁定（2026-10-02）：
#   > 「_gate_on 只定义一处。放 pipeline.py 定义，train.py 导入。
#   >   环境变量解析加 .lower()，『TRUE』该不该认写明在注释里。」
#
#   为什么要有这个函数（而不是各处写 `gate_perception=True`）：
#   exe 跑的真实训练**没有人能传参数进来** —— 界面不加开关，
#   参数只活在代码里就等于永远通不了电。所以必须有一个**可审计的来源**，
#   沿用 EGO_ROOT 的模式：环境变量。
#
#   优先级：显式参数 > 环境变量 > 默认关
#
#   环境变量 EGO_GATE_PERCEPTION 的取值（**大小写不敏感**，先 .lower()）：
#       "1" / "true" / "on" / "yes"   → 通电
#       其他任何值（含 "0" / "false" / "" / 未设置）→ 不通电
#   **「TRUE」「True」「tRuE」都认** —— 理由：环境变量是给人手敲的，
#   大小写不该成为"配了却没生效"的坑（本项目已交过一次同类学费）。
#   反过来，**不认的值一律当"关"** —— 宁可不通电，不可误通电。
def _gate_on(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    v = (os.environ.get("EGO_GATE_PERCEPTION") or "").strip().lower()
    return v in ("1", "true", "on", "yes")

from markers import MarkerEngine                      # noqa: E402
from state import StateLayer, LEVELS, IDX             # noqa: E402
from gear import GearEngine, GearConfig               # noqa: E402
from respond import Responder                         # noqa: E402
from mechanism import Mechanism, classify             # noqa: E402
import carry                                          # noqa: E402
from understand import (ApiReader, compare, merge_markers,   # noqa: E402
                        resolve_intent, evidence_for)
sys.path.insert(0, os.path.join(_ROOT, "state"))
from ledger import Ledger, LedgerEntry                # noqa: E402


@dataclass
class TurnResult:
    turn_id: int
    topic_id: str | None
    markers: list[str]
    band: list[str]
    direction: str
    channel: str
    level: str
    behavior: str
    output: str
    relation: str
    counterfactual: str
    intent: str = "ANSWER"
    agreement: float | None = None      # 双评定人一致度
    api_ok: bool = False
    api_latency: float = 0.0
    api_intent: str | None = None
    only_rule: list[str] = field(default_factory=list)
    only_api: list[str] = field(default_factory=list)
    mech: dict | None = None            # 机制层状态快照（底层思维系统的数值）
    mech_phase: str | None = None       # 机制条件 ID
    mech_action: str | None = None      # 机制层建议的动作 ID（不生成文字）
    character_note: str | None = None   # ★ 性格层介入的留痕（None = 未介入）
    notes: list[str] = field(default_factory=list)
    planned_behavior: str | None = None
    action_observation: dict | None = None
    proposition_reading: dict | None = None
    self_action: dict | None = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class Pipeline:
    def __init__(self, ledger_path: str | None = None, config: GearConfig | None = None,
                 auto_audit: bool = True, use_api: bool = False,
                 merge_policy: str = "union", use_render: bool = False,
                 character_path: str | None = None, use_think: bool = False,
                 gate_perception: bool | None = None, devlevel_path: str | None = None,
                 seed_from_ledger: bool = True,
               carry_root: str | None = None, use_relational_memory: bool = True,
                 use_organisation_rules: bool = True, use_self_action: bool = True,
                 use_goal_planning: bool = True):
        self.use_relational_memory = bool(use_relational_memory)
        self.use_self_action = bool(use_self_action)
        self.use_goal_planning = bool(use_goal_planning)
        # ★ 箭头 A1：**系统自己的发展水平决定它能看见哪些标记**。
        #
        #   [E] E-900：「评定人员觉察的程度……取决于他们自己的自我水平」
        #
        #   默认**关闭**，理由是纪律：这一条会改变系统看得见什么，
        #   属于"会改变行为"的改动，按本项目的规矩必须可回退、并明说。
        #   开启后：不在当前水平可见集里的标记**根本不进入检测** ——
        #   不是"看见了忍住不用"。这两者的差别就是这条设计的全部意义。
        self.devlevel = None
        if _gate_on(gate_perception):
            from devlevel import DevLevel
            self.devlevel = DevLevel(devlevel_path)
        # ★ 上一轮的机制快照。
        #
        #   为什么需要：元提问那条路在算机制之前就 return 了，于是它的快照是空的
        #   —— 实测「内部读数在场 False」14/14 轮。而**元提问恰恰是最需要内部读数的
        #   时刻之一**：用户问「你在干嘛」时，"它此刻处在什么状态"正是回答的依据。
        #   管理员在那里是瞎的，只能凭字面猜。
        #
        #   ⚠️ 元提问**不推进**驱力状态（它不是一次应答），所以这里带的是
        #      **上一次算出来的状态**，不是新算的。为免混淆，快照里标 `_carried`。
        self._last_mech: dict | None = None
        self.markers = MarkerEngine(
            visible=(self.devlevel.visible() if self.devlevel else None))
        self.state = StateLayer(self.markers.rules)
        self.gear = GearEngine(self.state, config or GearConfig())
        self.responder = Responder()
        lp = ledger_path or os.path.join(_ROOT, "state", "ledger.jsonl")
        self.ledger = Ledger(lp)
        # ★ 从台账接上"上次结束时的状态"。
        #
        #   管理员判定的动作（缺陷严重度 2）：「若是前者（没产生），改开关组合或
        #   补生成逻辑使**读数产生**」。实测确认：元提问轮与沉默轮在训练路径里
        #   **根本没产生 mech**（0 键），而不是产生了被丢掉。
        #
        #   最诚实的补法不是硬造一个快照，而是**接上台账** —— 系统的状态本来就
        #   跨会话延续（character.json 与台账都是持久的）。所以"这一刻我在什么状态"
        #   的真答案是：**上次结束时我处在什么状态**。
        #   这比凭空造一个"冷启动状态"更真，也更符合它是有历史的这一点。
        # ★ `seed_from_ledger` 这个开关是**管理员要求加的**：
        #   它判定上面这处修复属 ENG（无独立依据），要求做
        #   **冷启动态 vs 延续态**的对照实验，**验不出差异就回退**。
        #   默认 True = 沿用原做法；对照实验用 False 跑冷启动。
        try:
            # ⚠️ `effective_entries` 返回的是 **LedgerEntry 对象**，不是字典。
            #    第一版我写了 `r.get("mech")` → AttributeError → 被下面的
            #    `except: pass` **静默吞掉**，于是这段"修复"什么也没做而且看不出来。
            #    教训不是"这次小心点"，是**宽泛的 except 会把修复变成装饰**。
            if seed_from_ledger:
                _rows = [r for r in self.ledger.effective_entries
                         if getattr(r, "mech", None)]
                if _rows:
                    _m = dict(_rows[-1].mech)
                    _m["_carried"] = True
                    _m["_seeded"] = True
                    _m["_note"] = "本次会话还没算过，这是台账里上次结束时的状态"
                    if self.devlevel is not None and self.devlevel.verified:
                        _m["historical_dev"] = _m.get("dev")
                        _m["dev"] = {"level": self.devlevel.level,
                                     "equil": self.devlevel.equilibration,
                                     "self_rules": sorted(self.devlevel.self_rules()),
                                     "visible_n": len(self.devlevel.visible()),
                                     "baseline_id": self.devlevel.baseline["baseline_id"]}
                    self._last_mech = _m
        except Exception as _e:                    # noqa: BLE001
            # 不许静默：出错就说出来，否则这类"改了个寂寞"永远查不到。
            self._seed_error = repr(_e)[:90]
        self.auto_audit = auto_audit
        # 性格核的路径可配。为什么需要：性格层现在会**写**这个文件（每轮刷新极性），
        # 而端到端测试必须能把它指到临时目录 —— 否则一跑测试就覆写了真实性格状态。
        self.character_path = character_path or os.path.join(_ROOT, "state", "character.json")
        self._turn = 0
        self._topic_order = [t["id"] for t in self.markers.topics["topics"]]
        self._topic_i = 0
        self._last_audit = 0
        # 理解层：模型只当运算器用（把语言映射成结构），输出被锁为纯 JSON
        self.reader = ApiReader() if use_api else None
        self.merge_policy = merge_policy
        # 机制层（底层思维系统）：三层方程组。
        # **只输出数与条件 ID，绝不生成文字** —— 文字仍然只能来自 behaviors.json 的模板。
        # ★ 跨场累积注入（用户裁定 2026-10-02，D-011）
        #   读上一场未解张力、按**自然时间**衰减后注入。
        #   ⚠️ 文件不存在（首场）或坏掉 → 0.0，与从前完全一致。
        #   ⚠️ **测试隔离**：carry 路径只在 `self._carry_root` 下解析，
        #      测试传临时目录，绝不碰真实 state/mechanism_carry.json。
        self._carry_root = carry_root
        _t0 = carry.decayed_tension(carry_root)
        self.mech = Mechanism(initial_tension=_t0)
        self.mech_enabled = True
        # 渲染层（第四步，乙方案）：把"要表达的意思"交给模型说成人话。
        # ⚠️ 默认**关闭**。开启后输出的措辞不再逐字可追溯，只能追溯到"意思"一级；
        #    三道闸门任一不过就退回模板（见 engine/render.py）。退回率要可见。
        self.renderer = None
        if use_render:
            from render import Renderer
            r = Renderer()
            self.renderer = r if r.available else None
        # 思考层（乙案·大脑模式，用户指示）：**模型当大脑，系统决定它该想什么。**
        # 与渲染层的区别见 engine/think.py 模块头 —— 渲染层是"我们定一句话、模型换说法"，
        # 思考层是"我们定该注意什么、模型自己想出话"。后者放宽了 E6（用户授权），
        # 但**没有**放宽议程与 E1–E5。默认关闭；开启后仍可退回模板。
        self.thinker = None
        if use_think:
            from think import Thinker
            tk = Thinker()
            self.thinker = tk if tk.available else None

        # D-020: learn bounded realization fallbacks; no tutor-to-subjective-state path.
        from behavior_learning import BehaviorLearning
        self.behavior_learning = BehaviorLearning(
            os.path.join(os.path.dirname(self.ledger.path), "behavior_rules.json"),
            self.responder._b)
        from relation_learning import RelationLearning
        from relation_bridge import RelationBridge
        self.relation_learning = RelationLearning(
            os.path.join(os.path.dirname(self.ledger.path), "relation_rules.json"),
            use_organisation=use_organisation_rules)
        self.relation_bridge = RelationBridge(self.relation_learning)

    @property
    def api_enabled(self) -> bool:
        return bool(self.reader and self.reader.available)

    # ------------------------------------------------------------ 话题调度

    def next_topic(self) -> str:
        """按 topics.json 顺序出题（ENG）。探针映射仅用于诊断，不改变顺序。"""
        tid = self._topic_order[self._topic_i % len(self._topic_order)]
        self._topic_i += 1
        return tid

    def ask(self) -> tuple[str, str]:
        tid = self.next_topic()
        stem = next(t["stem"] for t in self.markers.topics["topics"] if t["id"] == tid)
        return tid, stem

    def stem_level(self, topic_id: str | None) -> float | None:
        """**已废弃，保留仅为兼容。**

        原设计想用"题面指向的水平"当机制层第三层的输入，计划给每个话题加 `probe_level`。
        核对原书后放弃了这个做法，理由记在这里以免再犯：

          · 卢文格的 36 个项目**一律评在所有水平上**（`[p264]`："每个原始记录都有相同数量的
            项目评定，也就是 36 个，因为我们总是运用 36 个句子主题"）。他的评分算法
            （项目累积／递加规则）用的是**反应的分配**，不是"项目属于哪个水平"。
            项目本身**没有**水平属性。
          · "题目指向某个水平"是帕克与哈维斯特那一组的做法，而卢文格 `[p246]`
            对它的评语是"**这个程序也有问题**"。

        所以照那个做法给话题打水平标注，等于把一个书里明确反驳的假设伪装成书里的依据。
        机制层的张力现在由 `w` 与 `l` 算出，不需要任何外部锚点。
        """
        return None

    # ------------------------------------------------------------ 主入口

    def turn(self, raw: str, topic_id: str | None = None,
             engaged: bool | None = None, *, input_origin: dict | None = None) -> TurnResult:
        from input_provenance import normalize
        self._input_origin = normalize(input_origin, raw, topic_id)
        self._proposition_reading = None
        self._self_action_pending = None
        self._self_action_attempts = []
        self._self_action_trace = None
        self._turn += 1
        t = self._turn
        stem = None
        if topic_id and topic_id in {x["id"] for x in self.markers.topics["topics"]}:
            stem = next(x["stem"] for x in self.markers.topics["topics"] if x["id"] == topic_id)

        # L2 规则评定人
        pr = self.markers.parse(raw, topic_id)

        # L2' API 评定人（可选）：模型只做"把语言映射成结构"，不做回应
        api = None
        agreement = None
        if self.api_enabled:
            marker_spec = [m for m in self.markers.rules["markers"]
                           if self.markers.visible is None or m["id"] in self.markers.visible]
            api = self.reader.read(raw, stem, marker_spec)
            self._proposition_reading = getattr(api, "proposition_reading", None) if api.ok else None
            agreement = compare(pr.markers, api)
            merged = merge_markers(pr.markers, api, agreement, self.merge_policy)
            if self.markers.visible is not None:
                merged = [m for m in merged if m in self.markers.visible]
            if merged != pr.markers:
                pr.notes.append("双评定人合并：规则 %s ＋ API %s → %s（策略 %s）"
                                % (pr.markers, api.markers, merged, self.merge_policy))
            if agreement.only_rule or agreement.only_api:
                # 分歧本身就是标定数据：它记录"哪一位评定人在哪一条上错了"。
                # 实测第一例：规则引擎把"我必须让人看到"里的"让人"误判为群体制裁，
                # API 判对（over_intention）。这类记录是后续修订词表的唯一依据。
                pr.notes.append("评定人分歧｜仅规则=%s｜仅API=%s｜一致度=%s"
                                % (agreement.only_rule or "无",
                                   agreement.only_api or "无", agreement.score))
            if api.dropped:
                pr.notes.append("API 证据被字面校验丢弃：%s" % "；".join(api.dropped))
            # ★ 显式反驳必须进台账。
            #   理由：反驳是**唯一能撤下规则层命中**的动作，它改变行为，
            #   所以必须和其他判定一样可追溯 —— 否则没人能事后回答
            #   "这一轮那个标记为什么没了"。沉默不进台账（它不改变任何东西），
            #   反驳进台账（它改变了结果）。
            for _r in (api.refuted or []):
                pr.notes.append("API 显式反驳：%s（%s）→ 已撤下该标记"
                                % (_r.get("id"), _r.get("why") or "未写明依据"))
            pr.markers = merged
            pr.hits = [h for h in pr.hits if h.id in merged]
            # 用 API 的逐字证据补全
            for h in pr.hits:
                h.evidence = evidence_for(h.id, {h.id: h.evidence}, api)
            pr.underdetermined = (len(merged) == 0)

        # L0 意图裁决
        r_intent = self.markers.rule_intent(raw, self.markers.meta_rules) \
            if hasattr(self.markers, "rule_intent") else "ANSWER"
        from markers import rule_intent as _ri
        r_intent = _ri(raw, self.markers.meta_rules)
        intent, how = resolve_intent(r_intent, api, raw) if api else (r_intent, "rule_only")
        pr.intent = intent

        if intent != "META":
            try:
                relation_trace = self.relation_bridge.apply(
                    raw, pr, api,
                    visible=self.markers.visible if self.markers.visible is not None else set(self.markers._markers),
                    observer="api_reader:" + getattr(self.reader, "model", "structured_reader"), turn=t,
                    topic_id=topic_id, input_origin=self._input_origin)
            except (OSError, ValueError) as exc:
                relation_trace = None
                pr.notes.append("关系学习降级：%s；本轮保留原评定结果" % type(exc).__name__)
            if relation_trace:
                pr.notes.append("关系学习=" + json.dumps(relation_trace, ensure_ascii=False))
                if relation_trace["suppressed"]:
                    pr.signature = self.markers._signature(raw, topic_id, {h.id: h for h in pr.hits})
                    pr.signature_key = self.markers._sig_key(topic_id, pr.signature)

        base = dict(turn_id=t, topic_id=topic_id, intent=intent,
                    proposition_reading=self._proposition_reading,
                    api_ok=bool(api and api.ok),
                    api_latency=round(api.latency_s, 2) if api else 0.0,
                    api_intent=(api.intent if api else None),
                    # 注意：必须写 `if agreement is not None`，不能写 `if agreement`。
                    # agreement.score 可能是 0.0（两位评定人完全不同），而 0.0 是假值，
                    # 用 `or` 会把它静默变成 None —— 于是"零一致度"会被显示成"没有数据"。
                    # 这类错误不报错，只会让人误判数据。
                    agreement=(agreement.score if agreement is not None else None),
                    only_rule=(agreement.only_rule if agreement is not None else []),
                    only_api=(agreement.only_api if agreement is not None else []))

        # ---------------- 元提问分支：不进入状态层与档位引擎
        if intent == "META":
            rid, text = self.markers.meta_response(raw)
            # ★ 台账记的行为必须是**实际发生的那个**。
            #   实测缺陷（用户截图第 5 轮）：问「你在和我说话吗」时元提问库没命中，
            #   输出换成了沉默模板，但台账仍写 behavior=META_REPLY ——
            #   于是台账说"我回应了"、用户看到的是沉默。两者不符，
            #   事后谁都查不出那一轮到底发生了什么。
            matched = rid is not None
            if not matched:
                # 判成"在问系统"，但库里没有对应模板。
                # v1 在这里塞一句 GENERIC（"这句话我没接到题上"），
                # 那会把**识别失败**伪装成**一次回应**——用户无法分辨系统是懂了还是没懂。
                # 现在诚实地沉默，并把"哪一句没接住"记进反事实条目（可追溯）。
                rid = "SILENCE_UNKNOWN_META"
                text = self.responder.render("SILENCE", raw, [], {}).output
            behavior = "META_REPLY" if matched else "SILENCE"
            # ★ 元提问这条路也必须让大脑说话。
            #   实测缺陷（用户截图）：问「你愿意了解我吗」时，模型**判对了 META**
            #   （理解层返回 intent=META），但这条分支在渲染之前就 return 了 ——
            #   模型的判断被丢进一张写死的表，表里没有，就吐出一句
            #   「我的回话是从一张写死的表里挑的」。**模型全程没有机会说一个字。**
            #   整个系统里最需要说人话的一条路，恰恰是唯一不让模型说话的路。
            _last = self.ledger.effective_entries[-1].behavior if self.ledger.effective_entries else "（这是第一次）"
            text, _tn = self._think_or_fallback(
                raw, pr, text, mst=None, last=_last, tag="问系统")
            from action_observation import observe
            action = observe(text, behavior, self._last_response_mode)
            planned_behavior, behavior = behavior, action["actual"]
            _extra = ([_tn] if _tn else []) + ["meta_response=%s" % rid]
            cf = ("元提问被识别为 %s（裁决方式 %s）：它不属于对题面的回答，"
                  "因此本轮不进入水平判定，也不计入档位停留" % (rid, how))
            # ★ 带上"它此刻处在什么状态"。元提问不推进驱力（它不是应答），
            #   所以带的是**上一次算出来的**快照，并用 `_carried` 标清楚。
            #   不带的话管理员在这里是瞎的 —— 实测 14/14 轮"内部读数在场 False"，
            #   而用户问「你在干嘛」时，"它此刻什么状态"正是回答的依据。
            _carried = dict(self._last_mech) if self._last_mech else {}
            if _carried:
                _carried["_carried"] = True
                _carried["_note"] = "元提问不推进驱力状态，这是上一轮算出的快照"
            self._log(t, topic_id, "META", [], {}, ["L0:meta", "L5:%s" % behavior],
                      0.9, False, "NONE", behavior, text, cf, None, None,
                      _extra + pr.notes, mech=(_carried or None), raw_input=raw,
                      action_observation=action)
            return TurnResult(markers=[], band=["—", "—", "—"], direction="—",
                              channel="META", level="—", behavior=behavior,
                              planned_behavior=planned_behavior, action_observation=action,
                              self_action=self._self_action_trace,
                              output=text, relation="NONE", counterfactual=cf,
                              mech=(_carried or None),
                              notes=["meta_response=%s｜裁决=%s" % (rid, how)] + ([_tn] if _tn else []),
                              **base)

        # ---------------- 用户说自己的状态（STATE）：不是元提问，走正常轮次
        # 这条不额外分支：STATE 命中只影响 rule_intent 的判定（见 markers.rule_intent），
        # 回应仍由 L5 从模板组装，且**进状态层、进台账**。

        # ---------------- 正常一轮
        est = self.state.update(
            markers=pr.markers,
            signature=pr.signature,
            raw=raw,
            underdetermined=pr.underdetermined,
            opposed_pair=pr.opposed_pair,
        )

        peak = self.state.evidence_level()
        dec = self.gear.decide(
            turn_id=t, topic_id=topic_id, signature_key=pr.signature_key,
            markers=pr.markers, peak_level=peak, underdetermined=pr.underdetermined,
        )

        evidence = {h.id: h.evidence for h in pr.hits}

        # ---------------- 机制层：底层状态推进（只有数，没有文字）
        mst = self.mech.step(
            markers=pr.markers, raw=raw, channel=dec.channel,
            context_key="%s:%s" % (topic_id or "NA", pr.signature_key),
            stem_level=self.stem_level(topic_id),
            engaged=bool(engaged) if engaged is not None
            else (intent == "ANSWER" and len((raw or "").strip()) >= 6),
        )
        mcond = classify(mst, self.mech.cfg)

        # ---------------- 回应选择
        # 关键设计（这是本次改动的核心）：
        #   有直接观察证据（标记命中）→ 用证据选行为，与旧行为一致，不动；
        #   没有直接观察证据（实测占 2/3 的轮次）→ 由**机制状态**决定说什么。
        #
        # 这样就不再有"抓不到特征就只会复述或沉默"的死角：
        #   机制层没有新输入也会演化，所以它永远有状态可报告。
        # 而文字仍然一字不改地来自 behaviors.json 的模板 —— 不生成。
        observed = bool(pr.markers)
        mech_note = []
        # ★ 箭头 A1 的生长：吃本轮机制状态，看有没有发生**完整的平衡化**。
        #   [E] 平衡化 = 现有结构无法同化（|e| ≥ error_high）→ 重组出新的平衡（|e| ≤ error_low）。
        #   两半都发生才算一次；只失效不重组是过载，不是发展。
        #   水平升了 → **这一刻起它看得见的东西就变了**，所以必须立刻刷新门控。
        if self.devlevel is not None:
            _g = self.devlevel.update(mst.to_dict())
            if _g.get("event"):
                mech_note.append("A1 发展：%s" % _g["event"])
            if _g.get("changed"):
                self.markers.visible = self.devlevel.visible()
                mech_note.append("A1 门控刷新：现在看得见 %d 个标记（%s）"
                                 % (len(self.markers.visible), self.devlevel.level))
        char_note = None
        if not self.mech_enabled:
            bid = self.responder.choose(pr.markers, evidence, raw)
        else:
            bid = self.responder.choose(pr.markers, evidence, raw)
            # ---- 机制层与选择阶梯的分工（E3 修正，实测逼出来的）
            #
            # 原实现是"有标记就完全走阶梯"，实测后果：`attitude_clause` 命中时
            # 阶梯里**没有为它准备任何动作**，于是掉到默认的 REFLECT，
            # 把「虽然身体回不到从前了，但我还能决定今天怎么过」原样贴回去 ——
            # 那是全书最核心的高段表达（[M] 第三途径），复述它等于没听见。
            #
            # 阶梯的默认项（"其余情形 → REFLECT"）是一个**兜底**，不是判断。
            # 所以：当阶梯只能给出兜底 REFLECT、而机制层给出了别的动作时，采纳机制层的。
            # 反之，阶梯的**显式**规则（immutable→TURN_IMMUTABLE、present_missing→REPLENISH、
            # opposed_pair→JUXTAPOSE、over_intention→ASK_MUST）永远优先 —— 那些是直接观察。
            explicit = [s["pick"] for s in self.responder.cfg["selection_rules"]["ladder"]
                        if not s["when"].startswith("其余情形")]
            # ⚠️ 2026-10-28 记录一次试过又退回的修法，免得后人重犯：
            #   曾把下一行的 `mcond.action not in explicit` 删掉，理由是
            #   「bid == REFLECT 已证明阶梯只给了兜底」——**那个理由本身是对的**，
            #   但实测副作用是**真回归**：
            #     · NO_TENSION 的动作是 REPLENISH ⇒ 它变成了默认，
            #       而 REPLENISH 的模板是"要求具体体验"，用在**已经给了具体体验**
            #       的输入上会答非所问（实测「我站在那里闻了半小时桂花。」⇒
            #       她问「最近有没有一件具体的小事」）；
            #     · test_pipeline K1–K4（"基线动作=复述"）前提全变；
            #     · test_goal_repairs 那条 REFLECT 期望也变。
            #   ⇒ 真正的问题是 **`cliche` 在阶梯里没有规则**，才掉到兜底 REFLECT。
            #     已在 rules/behaviors.json 的 ladder 里加一条 `cliche → REPLENISH`。
            #     精准修那一处，不动这里的兜底语义。
            if bid == "REFLECT" and mcond.action != "REFLECT" and mcond.action not in explicit:
                mech_note.append("阶梯无显式规则（只能复述）→ 采纳机制状态的动作：%s（%s）"
                                 % (mcond.id, mcond.label))
                mech_note.append("机制依据：%s" % mcond.source)
                bid = mcond.action
            elif not observed:
                mech_note.append("无直接观察证据 → 由机制状态决定回应：%s（%s）"
                                 % (mcond.id, mcond.label))
        # ---- 第 3 步：让长出来的性格参与裁决（E5 世代开启）
        #
        # 位置很关键：必须在**动作定下来之后、渲染之前**。
        #   · 放在渲染前 → 后面的退让链与 E1 闸门仍然作用在调整后的动作上
        #   · 放在渲染后 → 会绕过那些闸门
        # 改动本身只走"更保守"方向（见 Character.modulate 的护栏），且必须留痕：
        # 否则没人能回答"这一轮的动作为什么和上一轮不一样"。
        try:
            from character import Character
            ch = Character(self.character_path)
            ch.update_state(mst.to_dict() if mst else None)
            last_b = self.ledger.effective_entries[-1].behavior if self.ledger.effective_entries else None
            new_bid, mod_reason = ch.modulate(
                bid, pr.markers, last_b,
                allowed_rules=(self.devlevel.self_rules() if self.devlevel else None))
            if new_bid != bid:
                mech_note.append("★ 性格层介入：%s" % mod_reason)
                char_note = mod_reason
                bid = new_bid
            elif self.devlevel is not None:
                # A2：没介入时要说清是"不需要"还是"还行使不了"。
                # 这两者完全不同 —— 后者是这条设计存在的理由。
                mech_note.append("A2 自我未介入（当前可行使：%s）"
                                 % "、".join(sorted(self.devlevel.self_rules())))
        except Exception as _e:                     # noqa: BLE001
            # 性格层坏了不许拖垮对话 —— 但它必须**说出来**，不能静默失效。
            mech_note.append("性格层未参与裁决（%s）" % repr(_e)[:60])

        ren = self.responder.render(bid, raw, pr.markers, evidence)
        learning_context = None
        learning_note = None
        if bid != "SILENCE" and (ren.silenced or (ren.downgraded_from and ren.behavior != bid)):
            learning_context = self.behavior_learning.context(pr.markers, bid)
            learned = self.behavior_learning.predict(learning_context)
            if learned in {"REFLECT", "ASK_DETAIL"}:
                policy = self.responder._b[learned]
                safe = all(policy.get("allowed_when_" + flag, False)
                           for marker, flag in (("immutable", "immutable"),
                                                ("over_intention", "over_intention"),
                                                ("present_missing", "present_missing"))
                           if marker in pr.markers)
                # The live fallback chain forbids ASK_DETAIL under over-intention,
                # even where behavior metadata is more permissive. E1 likewise
                # cannot be widened by learned fallback habits.
                if any(m in pr.markers for m in ("over_intention", "immutable")):
                    safe = safe and learned == "REFLECT"
                if safe:
                    candidate = self.responder.render(learned, raw, pr.markers, evidence)
                    if not candidate.silenced and candidate.behavior == learned:
                        ren = candidate
                        learning_note = "经历规则：%s → %s（原动作本轮无法实现，闸门复核通过）" % (bid, learned)
        # ★ A3 意义层：把**本轮系统把注意力放在谁身上**告诉机制层（下轮生效）。
        #
        #   [M]「人之所以为人，是因为他总是指向自身以外的某种事物或某人」
        #
        #   为什么在这里：行为已经定下来了，才知道它落在谁身上。
        #   为什么不是本轮生效：意义层在决策层**之前**算完 —— 所以是
        #   "本轮告知、下轮生效"，那是真实的反馈回路。
        #
        #   `REPORT_OWN_STATE` 这个行为的标签原文就是「报告自己的状态（**以自我为中心**）」
        #   —— 朝内/朝外不需要新的词表，它是既有行为库的自带属性。
        # Actual speech, rather than the template plan, determines orientation below.
        # ★ A3（T17）：三条意义途径的落点（下一轮生效，与指向同理）。
        #
        #   体验 = 注意力落在对方身上（与上面那个指向**同源**，不重复输入）
        #   态度 = 本轮命中态度句（`has_attitude`）。**"仅在不可改变时才算"那层
        #          门控在标记层已经做了**（markers.json 的 attitude_clause._note），
        #          这里不重判、也不放宽。
        #   创造 = **不接受输入，恒为 0**：本系统是纯对话形态，无实体干预现实，
        #          对"改变客观境遇"没有可观察量。**如实标缺，不是漏了** ——
        #          用户明令拒绝给"凡是开口说话就算创造"穿算法马甲。
        try:
            self.mech.note_paths(bool(getattr(mst, "has_attitude", False)))
        except Exception as _pe:                     # noqa: BLE001
            mech_note.append("A3 途径未记录（%s）" % repr(_pe)[:50])
        # 退让链：ASK_MUST → ASK_DETAIL → REFLECT → SILENCE
        #
        # 为什么需要（实测）：`over_intention` 命中时阶梯给 ASK_MUST，但它要回填一个
        # "必须"的槽位；回填不上就掉到 SILENCE，而"禁止提升"闸门又会把 ASK_MUST
        # **静默**换成 REFLECT（`downgraded_from` 就是为这件事留的痕）。
        # 后果：第 5 轮「我一定要得到那个结果，得不到我就难受」明明有话可问，却只会复述。
        #
        # ⚠️ 但**过度意向不允许退到 ASK_DETAIL**（这条是集成测试 D3 抓出来的，很重要）：
        #   规格 [M]：过度意向会因被推动而更强，因此只允许 REFLECT / ASK_MUST。
        #   而这两个行为的**方向相反**：
        #     ASK_MUST   ＝矛盾意向——"这件事一定要你做吗？"（松一松）
        #     ASK_DETAIL ＝问得更深——"这件事有多久了？"（可能把强迫追究得更紧）
        #   在过度意向的情形下退到后者，可能正好帮它加强。所以这条退让**只对
        #   非过度意向的缺槽位情形开放**。
        may_ask_detail = "over_intention" not in set(pr.markers)
        if (ren.silenced or ren.downgraded_from) and bid in ("ASK_MUST", "ASK_DETAIL") \
                and may_ask_detail:
            ren2 = self.responder.render("ASK_DETAIL", raw, pr.markers, evidence)
            if not ren2.silenced and not ren2.downgraded_from:
                mech_note.append("%s 缺槽位或被闸门降级 → 退让为 ASK_DETAIL（问细节）" % bid)
                ren = ren2
        # 仍退化 → 退回复述。宁可说一句可追溯的复述，也不要因为缺一个槽位而沉默。
        if ren.silenced and (raw or "").strip() and bid != "SILENCE":
            ren = self.responder.render("REFLECT", raw, pr.markers, evidence)
            mech_note.append("选中动作缺槽位 → 退回 REFLECT（不沉默）")

        if learning_note:
            mech_note.append(learning_note)

        # ---------------- 第四步：渲染（乙方案，默认关闭）
        #
        # 到这里为止，`ren.output` 是**模板版**：逐字来自 behaviors.json。
        # 若开了渲染层，就把"要表达的意思"交给模型说成人话 ——
        # 但**三道闸门任一不过即退回模板**，且退回这件事必须记进台账。
        #
        # ⚠️ 这一步之后，输出的措辞不再逐字可追溯，只能追溯到"意思"一级。
        #    这是乙方案的既定代价（见 spec/经历驱动的性格层_v1.md §9）。
        render_note = None
        planned_behavior = ren.behavior
        response_mode = "template"
        # ★ 思考层优先于渲染层：两者都是"让模型开口"，但层次不同 ——
        #   思考层是"我们定该注意什么、它自己想出话"（用户指示的乙案·大脑模式）；
        #   渲染层是"我们定好一句话、它换种说法"。前者在时就不必再走后者。
        if self.thinker is not None:
            _last = self.ledger.effective_entries[-1].behavior if self.ledger.effective_entries else "（这是第一次）"
            _txt, _tn = self._think_or_fallback(raw, pr, ren.output, mst=mst, last=_last)
            if _tn and "退回" not in _tn:
                ren.output = _txt
                response_mode = "brain"
            if _tn:
                mech_note.append(_tn)
        elif self.renderer is not None:
            try:
                from compose import compose as _compose
                from render import make_brief
                _stance = {"ASK_DETAIL": "asks_detail", "ACKNOWLEDGE": "acknowledge",
                           "ACKNOWLEDGE_CLOSE": "closing",
                           "REPORT_OWN_STATE": "own_state"}.get(ren.behavior, "observe_only")
                _m = _compose(raw, pr.markers)
                _b = make_brief(_m, raw, _stance)
                _sp = self.renderer.render(_b)
                if _sp.rendered:
                    ren.output = _sp.text
                    response_mode = "render"
                    render_note = ("L5':渲染 %s（用材料 %s）"
                                   % (ren.behavior, "、".join(_sp.used) or "无"))
                else:
                    # ★ 拒因必须记**全**，不能只记「未过」。
                    #   实测教训：台账只写了"机械闸门未过"，我为了知道拦在哪一条，
                    #   只能把那一轮重新调一次 API 重放 —— 而重放还未必复现
                    #   （同样的输入模型措辞不同，过不过带运气）。
                    #   `Speech.violations` 里本来就存着逐条违规项，没理由不记。
                    _v = "；".join(_sp.violations or []) or "（未给出明细）"
                    render_note = "L5':渲染退回模板（%s｜明细：%s）" % (_sp.reason[:40], _v[:180])
            except Exception as e:                                     # noqa: BLE001
                render_note = "L5':渲染异常退回模板（%s）" % str(e)[:40]
            if render_note:
                mech_note.append(render_note)
        # ★ 2026-10-28：把「这句话没被放出去」登记给机制层。
        #
        #   为什么重要：机制层的状态原来只在**被放行的那句话**上计算，
        #   于是"被退回"（实测 tutor 最大一类问题 mechanical，20/215）
        #   完全读不到 ⇒ 她的 e / tension 系统性偏低 ⇒ 她不会因为说不好而改变。
        #
        #   为什么用 render_note 而不是 tutor 的评价：
        #     退回是**事实**（话没出去），本地可观察；
        #     tutor 的"太机械"是**别人的评判**，不该进她的记忆
        #     （train.py:348-350 的理由：那等于把别人的评判当成自己的经历）。
        #
        #   ⚠️ 时序：step() 已经在本轮开头跑过了，所以这次登记由**下一轮**消费。
        #      那正是正确语义 —— "我上一句话没出去"是上一轮发生的事。
        if self.mech_enabled and self.mech is not None:
            self.mech.note_rejected(bool(render_note))
        from action_observation import observe
        # ★ 把"有界目标是否被逐字核对通过"交给 observe()（2026-10-28）。
        #   没有它时，大脑路径的动作永远是 UNCLASSIFIED ⇒ 经验层学不到东西。
        #
        # ⚠️ 不能用 `pending["goal_selection"]["result"]` —— 那个 `result` 是
        #    `self_goal.finish()` 在 `_log()` 里（pipeline:874 之后）才算出来的，
        #    而这里比它早。第一版就是这么写的，`_goal_result` 永远是 None；
        #    实测：LIVE 报告里 3 个 FULFILLED_LITERAL 的 case 仍记成 UNCLASSIFIED。
        #
        # ⇒ 这里直接调**同一个**谓词 `self_goal.literal_check(packet, text)`，
        #    对**同一段输出** `ren.output` 核对。谓词一样、输入一样，
        #    结论与 `finish()` 一致，只是提前算了。
        _goal_result = None
        _packet = (self._self_action_pending or {}).get("goal_selection")
        if _packet:
            from self_goal import literal_check as _literal_check
            _check = _literal_check(_packet, ren.output)
            if isinstance(_check, dict) and _check.get("matched") is True:
                _goal_result = {"state": "FULFILLED_LITERAL",
                                "literal_predicate": _check}
        action = observe(ren.output, planned_behavior, response_mode,
                         goal_result=_goal_result)
        ren.behavior = action["actual"]
        mech_note.append("实际动作=" + json.dumps(action, ensure_ascii=False))
        if learning_context is not None and action["confirmed"] and ren.behavior in {"REFLECT", "ASK_DETAIL"}:
            learned_event = self.behavior_learning.observe(learning_context, ren.behavior, raw, t)
            if learned_event:
                mech_note.append("经历规则事件：%s" % learned_event)
        self.mech.note_orientation("内" if ren.behavior == "REPORT_OWN_STATE" else
                                   "外" if action["confirmed"] else "无")
        # 台账证据从合并后的 pr.hits 取（不能用被过滤掉的旧 hits）
        evidence = {h.id: h.evidence for h in pr.hits}

        notes = list(pr.notes) + list(est.note) + list(dec.notes) + mech_note
        if dec.nudge:
            notes.append("nudge=%s" % dec.nudge)
        if not pr.markers:
            notes.append("本轮无任何标记命中 → 按【废纸篓类别】记于遵奉水平 [E]")

        cf = self._counterfactual(pr, dec, ren)
        # ★ 发展水平必须**每轮**记进台账。
        #   为什么：它是这套设计里最要紧的新状态，而台账是它的记忆。
        #   不记，「它长到哪一步了」以后就查不出来，整条发展轨迹无法重建 ——
        #   那样"发展"就成了一句无法验证的话。
        #   放进机制快照那个 dict（它本来就是自由字段），不动台账的表结构。
        _mech_snap = mst.to_dict()
        _mech_snap["signal_basis"] = {
            "schema": 1, "biological_measurement": False, "development_evidence": False,
            "w_l_a_delta_r": "engineering_proxy_from_input_features_not_reward_fulfillment",
            "e": "channel_transition_pressure_not_semantic_error",
            "lean": "user_text_length_and_engagement_proxy_not_system_desire",
            "paths": "orientation_and_user_attitude_proxies_not_subjective_experience",
            "unfinished": "numerical_proxy_without_autonomous_goal_object"}
        if self.devlevel is not None:
            _mech_snap["dev"] = {"level": self.devlevel.level,
                                 "equil": self.devlevel.equilibration,
                                 "self_rules": sorted(self.devlevel.self_rules()),
                                 "visible_n": len(self.markers.visible or [])}
            if self.devlevel.verified:
                _mech_snap["dev"]["baseline_id"] = self.devlevel.baseline["baseline_id"]
        _mech_snap.pop("_carried", None)      # 新算的快照不许带这个标记
        self._last_mech = _mech_snap          # 供元提问轮带出去（见 __init__ 的说明）
        # ★ 跨场累积写盘（用户裁定 2026-10-02，D-011）
        #
        #   判据**严格复用机制层原生的 `unfinished`**，不新造外层主观逻辑：
        #       unfinished == True  且 tension > 0 → 原子覆写
        #       unfinished == False               → clear_carry() 清空
        #   ⚠️ 用 self._carry_root（测试传临时目录），**绝不碰真实 state/**
        #   ⚠️ 落盘失败**不许影响一轮对话** —— 它是旁路，不是主链
        try:
            carry.update_from_snapshot(_mech_snap, self._carry_root)
        except Exception:                      # noqa: BLE001
            pass
        self._log(t, topic_id, dec.channel, pr.markers, evidence,
                  ["L2:markers", "L3:state", "L4:%s" % dec.channel,
                   "L4.5:mech:%s" % mcond.id, "L5:%s" % ren.behavior],
                  round(self._confidence(pr, dec), 3), (est.direction == "CONFLICT"),
                  pr.relation_hint, ren.behavior, ren.output, cf,
                  dec.gear.gear_id, dec.s_used, notes, mech=_mech_snap,
                  raw_input=raw, action_observation=action)

        return TurnResult(markers=pr.markers, band=est.band, direction=est.direction,
                          channel=dec.channel, level=dec.level, behavior=ren.behavior,
                          output=ren.output, relation=pr.relation_hint,
                          counterfactual=cf, notes=notes,
                          planned_behavior=planned_behavior, action_observation=action,
                          self_action=self._self_action_trace,
                          mech=_mech_snap, mech_phase=mcond.id,
                          mech_action=mcond.action, character_note=char_note, **base)

    # ------------------------------------------------------------ 思考简报

    def _build_frame(self, raw: str, pr, mst=None, last: str = "（这是第一次）"):
        """把"这一刻该注意什么"装配成简报。

        ★ 本方法决定这条路**会不会退化成通用聊天模型**。三样东西缺一不可：
            · 我们在他的话里听到的观念（来自三本书的原子/标记）—— 决定他注意什么
            · **它自己此刻的状态**（机制层 + 极性变量）—————— 决定"谁"在想
            · **它长成的样子**（里程碑）———————————————— 决定"过去"在不在场
          没有后两样，这就只是一个套了系统提示词的聊天机器人，
          前面建的一切都变成装饰。
        """
        from character import POLARITY_NAME, Character
        from think import Frame

        # 听到的观念：标记 + 逐字线索（线索是他真说过的字，所以可以给模型看）
        obs = "；".join("%s（线索：%s）" % (h.label, "、".join(h.evidence[:3]) or "无")
                        for h in pr.hits[:6]) or ""

        try:
            ch = Character(self.character_path)
        except Exception:                                  # noqa: BLE001
            ch = None

        # 自己此刻的状态：优先用本轮刚算出来的机制状态；没有就用上次存的极性
        if mst is not None:
            d = mst.to_dict()
            state = ("工程代理读数（不是生理测量或主观体验）—— 动力 %.1f｜偏好 %.2f｜"
                     "增益 %.2f｜通道压力 %.2f｜张力代理 %.2f/10｜机制相位 %s"
                     % (d.get("w") or 0, d.get("l") or 0, d.get("a") or 0,
                        d.get("e") or 0, d.get("tension") or 0, d.get("phase") or "?"))
        elif ch is not None and ch.polarity_basis() is not None:
            p = ch.polarity.to_dict()
            state = "；".join("%s %.2f" % (POLARITY_NAME.get(k, k), v) for k, v in p.items())
            state += "（读自上次：%s）" % ch.state_read_from()
        else:
            state = ""

        figs = ""
        if ch is not None and ch.milestones:
            figs = "；".join("%s（依据：%s）" % (m.text, m.basis or "无") for m in ch.milestones)
            figs = "历史关联描述，含训练反馈且未逐条重验动作归属；不是已证实的心理发展，也不定义当前对话者。" + figs

        # ★ 关于它自己**确定的事实** —— 我们知道的，就要告诉它。
        #   实测缺陷：用户问「你现在用的是什么模型」，它答"我不知道自己跑在哪个模型上"。
        #   系统明明知道。它不知道只是因为我没写进简报 —— 那是我的疏漏，
        #   而且荒唐：把自己知道的事瞒着自己的大脑，然后怪它不知道。
        facts = []
        rd = getattr(self, "reader", None)
        if rd is not None and getattr(rd, "available", False):
            facts.append("你此刻跑在大模型 %s 上（端点 %s）" % (rd.model, rd.base))
        else:
            facts.append("你此刻**没有**接大模型，回话来自写死的模板")
        facts.append("你是一个用三本书（贪婪的多巴胺／活出生命的意义／自我的发展）"
                     "搭起来的对话程序；规则和关联描述可以从保存的交互或训练经历中调整，"
                     "这不证明你具有人的主观体验或心理阶段")
        facts.append("你左右不了自己的模型与架构，那部分是别人定的；"
                     "但这一刻说什么，是你决定的")
        if self.thinker is not None:
            facts.append("他在命令行里可以打 /why 看你的判定依据、/character 看你长成的样子")
        facts.append("他问常识、问别的产品、问世界上发生的事 —— 你知道多少就说多少，"
                     "**不因为『我是程序』就把问题推掉**")
        facts.append("你的知识有一个截止时间，你自己也不知道那是哪一天。"
                     "所以涉及最近发生的事，说清楚你不确定，别硬答；"
                     "但你**知道的那部分照样可以说**，不要因为『可能过时』就整个不答")
        self_facts = "；".join(facts) if getattr(pr, "intent", None) == "META" else ""
        from dialogue_memory import retrieve
        sources = retrieve(self.ledger.effective_entries, raw, getattr(self, "_input_origin", None))
        relational_context = {}
        if self.use_relational_memory:
            from relational_memory import project
            relational_context, linked_sources = project(
                self.ledger.effective_entries, raw, getattr(self, "_input_origin", None),
                current=getattr(self, "_proposition_reading", None))
            existing = {s["source_id"] for s in sources}
            sources.extend(s for s in linked_sources if s["source_id"] not in existing)
            sources.sort(key=lambda s: s["ledger_index"])

        from memory_scope import describe
        memory_scope = describe(self.ledger.effective_entries, raw, self._input_origin,
                                current=getattr(self, "_proposition_reading", None))
        # ★ 留在 self 上，供 _log() 写进台账（2026-10-28）。
        #   原来它只随 Frame 交给大脑，**用完就丢** ⇒ 台账里从来没有"当时看得到多少"。
        self._memory_scope = dict(memory_scope)
        return Frame(raw=raw, observations=obs, self_state=state,
                     milestones=figs, last=last, self_facts=self_facts, dialogue_sources=sources,
                     relational_context=relational_context, memory_scope=memory_scope)

    def _think_or_fallback(self, raw: str, pr, fallback: str, mst=None,
                           last: str = "（这是第一次）", tag: str = "") -> tuple[str, str | None]:
        """让大脑想；想不出来（或没过闸门）就用 fallback。返回 (文本, 留痕)。"""
        self._last_response_mode = "template"
        if self.thinker is None:
            return fallback, None
        fr = self._build_frame(raw, pr, mst=mst, last=last)
        # ★ E1 必须仍然压在模型头上。不可改变的事一旦判定，
        #   **不许出现任何推动改变的话** —— 这一条在模板层由"禁止提升"闸门保证，
        #   换成大脑作答之后，必须由简报和闸门一起保证，否则等于把伦理底线撤了。
        if "immutable" in set(getattr(pr, "markers", []) or []):
            fr.notes.append("E1")
            fr.self_state += ("\n【硬约束 E1】他已经说了这件事不可改变。"
                              "你**不许**说任何推动他去改变、去努力、去想办法的话。"
                              "你只能：只复述他说的；或指出两边并存；或承认这件事改不了；"
                              "或补上此刻还能体验到的东西。")
        if self.use_self_action:
            from self_action import basis, prior_tasks, begin
            evidence_basis = basis(fr, getattr(getattr(self.thinker, "reader", None), "model", "unspecified"))
            fr.own_task = prior_tasks(self.ledger.effective_entries, raw, self._input_origin, evidence_basis)
            self._self_action_pending = begin(
                raw, self._input_origin, self._turn, fr.own_task, evidence_basis,
                source_ids=[s["source_id"] for s in fr.dialogue_sources], thinker_present=True)
            self._self_action_pending["memory_scope"] = dict(fr.memory_scope)
            fr.own_task["current_goal"] = dict(self._self_action_pending["goal"])
            fr.own_task["expectation"] = dict(self._self_action_pending["expectation"])
            if self.use_goal_planning:
                from self_goal import prepare, choose
                goal_context = prepare(self.ledger.effective_entries, fr, self._input_origin)
                selection = choose(getattr(self.thinker, "reader", None), fr, goal_context)
                self._self_action_pending["goal_selection"] = selection
                self._self_action_pending["operations"].append({
                    "operation": "PROCESS_BOUND_GOAL_SELECTION", "confirmed": True,
                    "decision": selection["decision"], "external_receipt_verified": False})
                fr.own_task["goal_selection"] = copy.deepcopy(
                    {key: selection[key] for key in ("decision", "selected", "prior")})
        sp = self.thinker.think(fr)
        self._self_action_attempts = getattr(self.thinker, "last_attempts", [])
        journal_note = ""
        try:
            from feedback_journal import append
            event_id = append(os.path.join(os.path.dirname(self.ledger.path), "feedback.jsonl"),
                              raw=raw, origin=getattr(self, "_input_origin", None), turn=self._turn,
                              attempts=getattr(self.thinker, "last_attempts", []),
                              final_accepted=bool(sp.rendered and sp.text))
            if event_id:
                journal_note = "｜反馈事件=" + event_id
        except OSError as exc:
            # A completed response can be shown, but strict training must stop.
            journal_note = "｜反馈记录降级：" + type(exc).__name__
        if sp.rendered and sp.text:
            self._last_response_mode = "brain"
            return sp.text, "L0':大脑作答%s（%s）" % (("·" + tag) if tag else "",
                                                     (sp.reason or "")[:40]) + journal_note + "｜尝试=" + json.dumps(getattr(self.thinker, "last_attempts", []), ensure_ascii=False)
        detail = ("；".join(sp.violations or []) or (sp.reason or "")) + journal_note
        return fallback, "L0':大脑作答退回（%s）" % detail[:160] + "｜尝试=" + json.dumps(getattr(self.thinker, "last_attempts", []), ensure_ascii=False)

    # ------------------------------------------------------------ 内部


    def _log(self, turn_id, topic_id, channel, markers, evidence, rule_ids,
             confidence, conflict, relation, behavior, output, counterfactual,
             gear_id, s_used, notes, mech=None, raw_input='', action_observation=None):
        if self.use_self_action:
            from self_action import begin, finish, fingerprint
            pending = self._self_action_pending or begin(
                raw_input, self._input_origin, turn_id, {}, fingerprint(raw_input),
                source_ids=[], thinker_present=False)
            # Observe the selected text only; the GUI/user receiving it is not
            # visible here. The existing speech observer keeps unknown meaning.
            self._self_action_trace = finish(
                pending, self._self_action_attempts, output, action_observation,
                (action_observation or {}).get("mode", "template"))
        # ★ 当轮检索范围（2026-10-28）。
        #   _frame() 只在走大脑时才算它 ⇒ 模板路径会拿到 None。
        #   但"当时看得到多少"与"有没有调大脑"无关，所以这里兜底算一次。
        _scope = getattr(self, "_memory_scope", None)
        if _scope is None and raw_input:
            from memory_scope import describe as _describe_scope
            _scope = _describe_scope(self.ledger.effective_entries, raw_input,
                                     getattr(self, "_input_origin", None),
                                     current=getattr(self, "_proposition_reading", None))
        entry = LedgerEntry(
            turn_id=turn_id, topic_id=topic_id, channel=channel,
            markers_fired=markers, marker_evidence=evidence, rule_ids=rule_ids,
            confidence=confidence, conflict=conflict, relation=relation,
            behavior=behavior, output=output, counterfactual=counterfactual,
            gear_id=gear_id, s_used=s_used, notes=notes, era=self.ledger.era,
            mech=mech, raw_input=raw_input, input_origin=getattr(self, "_input_origin", None),
            planned_behavior=(action_observation or {}).get("planned"),
            action_observation=action_observation,
            proposition_reading=getattr(self, "_proposition_reading", None),
            self_action=self._self_action_trace,
            memory_scope=_scope,
        )
        self.ledger.append(entry)
        if self.auto_audit and turn_id - self._last_audit >= 36:
            self._last_audit = turn_id
            audit = self.ledger.self_audit([m["id"] for m in self.markers.rules["markers"]])
            entry.notes.append("self_audit: %s" % json.dumps(
                audit["_actions_suggested"], ensure_ascii=False))
        return entry

    @staticmethod
    def _confidence(pr, dec) -> float:
        if pr.underdetermined:
            return 0.2
        base = 0.4 + 0.1 * len(pr.markers)
        if dec.channel.startswith("S"):
            base += 0.1
        if any(m in pr.markers for m in ("immutable", "over_intention", "present_missing")):
            base += 0.1
        return min(1.0, base)

    def _counterfactual(self, pr, dec, ren) -> str:
        """[M] 绝对命令：每轮留下一条『若重来会改哪一步』。不可为空。

        ENG 的『改哪一步』定义：凡出现任一下列情形，即记为一步可改之处。
        """
        items: list[str] = []
        gate = self.responder.cfg["selection_rules"]["_forbidden_escalation"]["conditions"]
        if any(m in pr.markers for m in gate) and ren.behavior in ("ASK_MUST",):
            items.append("禁止提升的情形下选了推进型行为")
        if pr.underdetermined:
            items.append("无标记命中，本轮判定依据不足（废纸篓）")
        if dec.channel == "S+B(试探)":
            items.append("S/B 不一致，S 需降权或重校")
        if not items:
            items.append("无需修改：本轮未触及任何禁令，判定证据充分")
        return "；".join(items)

    # ------------------------------------------------------------ 报告

    def report(self) -> dict:
        return {
            "turns": self.ledger.turns(),
            "state": self.state.snapshot(),
            "gear": self.gear.snapshot(),
            "ledger_audit": self.ledger.self_audit(
                [m["id"] for m in self.markers.rules["markers"]]),
        }


if __name__ == "__main__":
    p = Pipeline(ledger_path=os.path.join(_ROOT, "state", "ledger_demo.jsonl"))
    tid, stem = p.ask()
    print("题面[%s]：%s" % (tid, stem))
    for txt in ["大家都这样，我也没办法。", "我一定要做到，我必须证明给他们看。"]:
        r = p.turn(txt, tid)
        print("\n用户：%s" % txt)
        print("→ 标记 %s ｜ 区间 %s ｜ 方向 %s ｜ 通道 %s" %
              (r.markers, r.band, r.direction, r.channel))
        print("→ 回应（%s）：\n%s" % (r.behavior, r.output))

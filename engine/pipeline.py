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
import io
import os
import re
import sys
import time
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
                 use_goal_planning: bool = True, use_cognition: bool = False):
        self.use_relational_memory = bool(use_relational_memory)
        self.use_self_action = bool(use_self_action)
        self.use_goal_planning = bool(use_goal_planning)
        # ★ 2026-10-29（C4/C5 接线）：跨轮思考算子层。
        #
        #   **默认关闭**，理由是成本与纪律：
        #     · 每轮多 2 次 API 调用（抽取两遍）—— 是"每轮"都付，不是偶尔
        #     · 它改变"她该想什么"，属于会改变行为的改动
        #   ⇒ 按本项目规矩：默认关、可显式开、留痕。
        #
        #   ⚠️ 打开后仍受两条硬约束：
        #     ① 每条 claim 都过 `_literal_claim`（`raw[start:end] == text`）
        #     ② 台账记 `cognition`（op / quotes / hint / yielded）
        self.use_cognition = bool(use_cognition)
        #: 进程内的 claim 存档：turn_index -> [claim, ...]
        #: ⚠️ 只在内存里 —— 跨进程不持久。要持久化得先把 claims 也写进台账。
        self._cog_claims: dict[int, list[dict]] = {}
        #: 进程内元数据（供会话切分）
        self._cog_rows: list[dict] = []
        #: 本轮选中的 Thought（`_build_frame` 读它）
        self._pending_thought = None
        #: 本轮的 cognition 记录（写台账用）
        self._cog_record = None
        #: 本轮的空档回想（由 `ruminate()` 产生；没有就是 None）
        self._idle_thought = None
        #: 上次 ruminate 的异常（不静默吞掉 —— 见 ruminate 里的注释）
        self._idle_error = ""
        self._idle_gated = ""
        #: ★ 2026-10-30（Stage 2）：刚刚结算出的遭遇与结算后的 boldness
        self._last_encounter = ""
        self._settled_boldness = None
        #: 已经结算过的轮（幂等挡板 —— 一次 turn 只能结算一次）
        self._last_settled_turn = None
        #: ★ 2026-10-30：settle 的留痕（排查"结算没发生"用）
        self._settle_traces = []
        #: 上一轮是否抛过 idle（冷却用：至少隔 1 轮）
        #: ★ 2026-10-31：最后一次"选了 idle"的轮序号（冷却用，替代死代码 _idle_prev_turn）
        self._idle_last_turn = None
        #: ⚠️ 已废弃：从未被设成 True（死代码），保留仅为兼容旧测试
        self._idle_prev_turn = False
        #: ★ 2026-10-31（用户裁定）：被吞掉的异常计数 —— 每次实测必须报，不为 0 标红
        self._swallow_counts = {}
        self._swallow_total = 0
        # ★ 2026-10-31：已落盘过的那部分（增量落盘用）
        self._swallow_flushed = {}
        #: ★ 2026-10-30（Stage 3）：本轮唯一生效的焦点来源
        #:   "input" | "unfinished" | "idle" | "lexical"
        self._focus_origin = "lexical"
        #: * 2026-10-30（Stage 4）：裁决后的动作与性格层理由（供 stance 同构）
        #: ★ 2026-10-31（主线）：他最后一句是不是问句 / 是不是明确在问她
        self._he_is_asking = False
        self._he_is_asking_explicit = False
        self._final_bid = None
        self._char_note = None
        # 2026-10-30：悬念的「用完即焚」标记 + 单调递增的轮序号
        #   （turn_id 换会话会重置，不能用来判「紧挨着的下一轮」。）
        self._unfinished_consumed = False
        self._turn_seq = 0
        # 2026-10-30：认知层调试日志（独立文件，不进台账）
        self._cog_debug_path = (
            os.path.join(os.path.dirname(os.path.abspath(
                ledger_path or "state/ledger.jsonl")), "cognition_debug.jsonl")
            if ledger_path else None)
        #: ★ 自主悬念对象（架构改造 A）：`{"op", "quotes", "turn"}` 或 None
        self._unfinished_focus = None
        #: 空档回想的落盘（append-only，**独立于台账** ——
        #  因为她想的时候没有"一轮对话"，硬塞进 LedgerEntry 会搅乱轮次编号。
        #  ⚠️ 但这条痕迹必须留下：她想过什么，是可查的，不是一次性的。
        self._idle_log = os.path.join(
            os.path.dirname(os.path.abspath(ledger_path or "state/ledger.jsonl")),
            "ruminations.jsonl") if ledger_path else None
        #: 已经想过的片段（`(turn, start, end)`），供 `idle_recombine` 去重
        self._cog_seen: list[tuple[int, int, int]] = []
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
        # * 2026-10-30：存下来 —— _refresh_milestones 要用它。
        #   （第一版只用了局部变量 lp，于是那里 self.ledger_path 抛 AttributeError，
        #     被 except 吞成一条「里程碑刷新失败」，boldness 也就一直不动。）
        self.ledger_path = lp

        # ---- ★ 重启后从台账恢复 claim 存档与已想过的片段
        #
        #   ★ 依据（Gemini 第 ① 步）：「重启后从台账恢复 `self._cog_claims`，
        #     彻底解决重启失忆」
        #
        #   ⚠️ 这一步是"她记得"的**前提** —— 没有它，每次启动都是新的一天。
        #
        #   ⚠️⚠️ 位置必须是**台账创建之后**。2026-10-29 踩过：
        #      第一版写在 `self.ledger = Ledger(lp)` 之前，
        #      `self.ledger` 还不存在 ⇒ AttributeError 被 `except` 吞掉
        #      ⇒ 恢复 0 条，而且**一句提示都没有**。
        #      这正是项目铁律禁止的"静默失败" —— 所以这里**不吞异常**，
        #      出问题就让它响（`test_substrate_continuity` Y8 抓的是同一件事）。
        #
        #   ★ 依据（Gemini 第 ① 步）：「重启后从台账恢复 `self._cog_claims`，彻底解决重启失忆」
        #
        #   ⚠️ 这一步是"她记得"的**前提** —— 没有它，每次启动都是新的一天，
        #      跨轮算子能匹配的历史窗口只有本次进程内的几轮。
        # ★★ 2026-10-29（Gemini 诊断出的 N3 间歇抖动根因，我确认）：
        #
        #   `train.py` **每场会话开一次 `p = self._pipe()`**（90 轮里重建 15–30 次 Pipeline），
        #   而我上面那个恢复循环是**无条件**遍历整个台账的。
        #   ⇒ 在 `use_cognition=False`（包括 N3 在内的所有基线测试）时，
        #     这是一笔**纯粹的无谓 I/O**：读台账、解析 JSON、还可能撞上文件忙异常，
        #     一旦被 `train.py` 的 `continue` 跳过一轮 ⇒ `89 != 90` ⇒ N3 间歇失败。
        #
        #   ⇒ 守卫：**只有真的要用 cognition 时才恢复。**
        #     这样 `use_cognition=False` 的路径与改动前 100% 零差别。
        #   ⚠️ `test_substrate_continuity` Y8 测"重启恢复"时必须显式传 `use_cognition=True`
        #      —— 否则它测的是一条根本不会执行的路。
        if getattr(self, "use_cognition", False):
            try:
                for _i, _e in enumerate(self.ledger.effective_entries):
                    _cog = getattr(_e, "cognition", None) or {}
                    _cl = _cog.get("claims") or []
                    if _cl:
                        self._cog_claims[_i] = _cl
                        self._cog_rows.append({"ts": getattr(_e, "ts", None),
                                               "input_origin": getattr(_e, "input_origin", None)})
                    # ★★ 2026-10-30 修一个真缺陷（用户指出的）：
                    #   病灶：恢复循环只读 cog["sources"]（= **当轮算子**引用的两段），
                    #   不读 cog["idle"]["sources"]（= **空档回想**引用的两段）。
                    #   ⇒ 空档回想消费过的配对，**下一场会话就忘了**，于是又被选中。
                    #   ⇒ 实测铁证：16 次空档回想只有 7 个不同配对，
                    #     ['上个月发来的…', '下意识说"算了"'] 出现 4 次（轮 13/20/26/32，跨 4 场会话）。
                    #   ⇒ 修：两处 sources 都读。
                    _seen_srcs = list(_cog.get("sources") or [])
                    _seen_srcs += list((_cog.get("idle") or {}).get("sources") or [])
                    for _src in _seen_srcs:
                        try:
                            self._cog_seen.append((int(_src["turn"]), int(_src["start"]), int(_src["end"])))
                        except (KeyError, TypeError, ValueError) as _exc:
                            self._swallow("line269", _exc)
                            pass
            except AttributeError:
                raise
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


    def _refresh_milestones(self, mech_note: list | None = None) -> None:
        """重跑一次 `derive_from_ledger` + `learn()`，刷新里程碑文字。

        ⚠️ 这是**重活**（遍历全量台账），只在两个时机调：
          · 每 6 轮（`turn_id % 6 == 0`）
          · 会话退出时（`shell.py` 的 finally）
        ⚠️ 失败**不许阻断主线** —— 里程碑刷新失败只是"经历没长出来"，
           不该影响这一轮的回应。
        """
        try:
            from association import Association
            from character import Character
            _ap = os.path.join(os.path.dirname(self.character_path), "association.jsonl")
            assoc = Association.derive_from_ledger(self.ledger_path, _ap)
            ch = Character(self.character_path)
            ch.learn(assoc, None)          # mech=None：不假装有当下状态，只更新里程碑
            if mech_note is not None:
                mech_note.append("里程碑刷新：确认 %d / 受挫 %d｜笃定 %.2f"
                                 % (assoc.confirmed_count, assoc.rebuffed_count,
                                    ch.polarity.boldness))
        except Exception as _exc:                                  # noqa: BLE001
            if mech_note is not None:
                mech_note.append("里程碑刷新失败：%s" % type(_exc).__name__)

    def _arbitrate_focus(self, raw: str, mst, mech_note: list) -> None:
        """**单焦点短路仲裁**（五段式管线的 Stage 3）。

        严格按优先级短路求值 —— 前序命中就**绝不调用后续**：

          P1 `input`      ：本轮当轮算子已产出 `Thought`
          P2 `unfinished` ：上一轮想到了但没说透 / 追问了还在等下文（且没碰壁）
          P3 `idle`       ：空档回想（**只有到这里才调 `ruminate()`**）
          P4 `lexical`    ：都没有 ⇒ 才启用词级锚点（`_build_frame` 里照旧）

        ★ 2026-10-30（架构病灶 2+4 的落点）

        ⚠️ P3 的五个条件全部成立才调用 `ruminate()`：
          ① 没有当轮 Thought　② 没有悬念　③ 上一轮不是 REBUFFED
          ④ `boldness >= 0.42`　⑤ 上一轮没有刚抛过 idle（至少隔 1 轮冷却）
          ⇒ 前四条是"该不该想"，第五条是"别连着想"。
        """
        self._focus_origin = "lexical"
        # ---- P1：当轮算子
        if getattr(self, "_pending_thought", None) is not None:
            self._focus_origin = "input"
            self._idle_gated = "P1 胜出（有当轮算子，不耗 seen_pairs）"
            return
        # ---- P2：悬念
        _uf = getattr(self, "_unfinished_focus", None) or {}
        _enc = getattr(self, "_last_encounter", "") or ""
        _bd = getattr(self, "_settled_boldness", None)
        if _bd is None:
            _bd = self._last_encounter_and_boldness()[1]
        # 2026-10-30（Gemini 破案 1：僵尸悬念 Zombie Focus）
        #
        #   病灶：unfinished_focus 原来只在 mst.unfinished 变假时清空，
        #   而 mst.unfinished 在整场 6 轮里几乎永远为真（lean>0 且 l<1.0）
        #   ⇒ 第 1 轮写入的那条悬念，从第 2 轮一直挂到第 6 轮，甚至跨场。
        #
        #   实测铁证：P1 input 只发生 5 次，而 P2 unfinished 触发 21 次
        #   —— 源头只有 5 条，怎么可能消费 21 次？因为它是同一条挂了 4 轮。
        #   而且它 focus_level 落地 0/21（大模型完全无视那两段旧引文），
        #   还白白挡住了十几轮本该触发的 P3 idle。
        #
        #   ⇒ 修：严格限定为"紧挨着的下一轮"。① 同会话 ② 当前轮-uf.turn==1 ③ 否则清空。
        _uf_turn = _uf.get("turn")
        _uf_sess = _uf.get("session_id")
        try:
            _cur_sess = ((self.ledger.effective_entries[-1].input_origin or {})
                         .get("session_id") if self.ledger.effective_entries else None)
        except Exception:                                          # noqa: BLE001
            _cur_sess = None
        _uf_fresh = (isinstance(_uf_turn, int)
                     and getattr(self, "_turn_seq", 0) - _uf_turn == 1
                     and (not _uf_sess or not _cur_sess or _uf_sess == _cur_sess))
        if _uf.get("quotes") and not _uf_fresh:
            self._unfinished_focus = None       # 过期悬念：清掉，绝不允许跨轮驻留
            _uf = {}
        if _uf.get("quotes") and _enc != "REBUFFED":
            self._focus_origin = "unfinished"
            self._idle_gated = "P2 胜出（有悬念，不耗 seen_pairs）"
            self._unfinished_consumed = True    # 用完即焚
            return
        # ---- P3：空档回想（到这里才真的调用 ruminate）
        #
        # ★ 2026-10-31（用户裁定的主线之一）：
        #   **他在问她的时候，idle 不作为本轮焦点。**
        #   理由：那一轮她该做的是**先接住他的问题**，
        #   而 idle 是"翻旧账"——它会把她的注意力从他的问题拽走。
        #   实测支撑：上一批 9 次打回里有 5 次他在问她。
        if getattr(self, "_he_is_asking", False):
            self._idle_gated = "他在问她 ⇒ idle 让位（先接住问题）"
            return
        if _enc == "REBUFFED":
            self._idle_gated = "上一轮碰壁（REBUFFED）⇒ 不翻旧账"
            return
        if _bd < 0.42:
            self._idle_gated = "探照笃定 %.2f < 0.42 ⇒ 先收一收" % _bd
            return
        _last_idle = getattr(self, "_idle_last_turn", None)
        _cooldown = 3
        if isinstance(_last_idle, int) and (getattr(self, "_turn_seq", 0) - _last_idle) < _cooldown:
            self._idle_gated = ("冷却中（上次 idle 在第 %d 轮，还需隔 %d 轮）"
                                % (_last_idle, _cooldown))
            return
        if not getattr(self, "use_cognition", False):
            self._idle_gated = "cognition 关闭"
            return
        _rec = self.ruminate()
        if _rec is not None:
            self._focus_origin = "idle"
            # ★ 2026-10-31（用户裁定）：**选了 idle 之后至少隔 3 轮才允许再选。**
            #
            #   ⚠️ 原来的 `_idle_prev_turn` 是**死代码** ——
            #      148 行声明、481 行读，**没有任何地方把它设成 True**
            #      ⇒ 我文档里写的"冷却一轮"从来没生效过。
            #   ⇒ 改成"记下最后一次选 idle 的轮序号"，用距离判定，写在 `_arbitrate_focus` 里。
            #   ⚠️ 3 这个数是**待标定值（ENG）**：先按用户给的 3，实测后再调。
            self._idle_last_turn = getattr(self, "_turn_seq", 0)
            mech_note.append("空档回想（P3）：%r" % ((_rec.get("quotes") or [])[:2],))
            # ★ 2026-10-30（用户要求：idle 的 sources 与重合度也落盘）
            #   重合度 = 输出里逐字出现了几段 idle 引文 / 一共几段（0 / 0.5 / 1.0）
            self._pending_idle_rec = _rec
        else:
            self._idle_gated = "算法没配出可用的跨轮对"
        # ---- P4：词级（保持原样）

    #: ★ 2026-10-31（用户批准的兜底出口方案）
    #:
    #: ## 为什么换掉原来的兜底
    #:   大脑失败时退到的是模板 ``responder.render`` 的输出，
    #:   而 ``ASK_DETAIL`` 在没有 anchor 时只有一句写死的「发生什么了？」——
    #:   那是一句**没有对象的探问**：它假装接住了，实际在说「我没在听，你再说一遍」。
    #:
    #: ## 硬约束（全部代码保证，不靠提示词）
    #:   ① **不含问号**（`_fallback_line` 里断言）
    #:   ② **不复述他的内容**（这些句子与他说的无关）
    #:   ③ **不对他下指令**（没有「你先」「你别」「你可以」）
    #:   ④ 每种至少 3 个说法；**6 轮内不重复**
    #:   ⑤ 「没法确认」在本场已用过 ⇒ 换别的说法
    #:
    #: ⚠️ 两句通用的短承接故意做得**极短**：她接不住的时候，
    #:    少说比多说好 —— 多说是拿空话填场面。
    FALLBACK_ASK = (
        "这个我没法确认。",
        "我这边看不到。",
        "这我没法替你判断。",
        "我不敢说我清楚。",
        "这个我说不准。",
        "我看不到那一层。",
    )
    FALLBACK_OTHER = (
        "嗯，我听着。",
        "嗯。",
        "我在。",
        "记下了。",
        "好。",
        "嗯，我在听。",
    )

    def _fallback_line(self) -> str:
        """大脑失败时的出口句。按用户批准的五条硬约束挑选。"""
        # ① 他最后一句是问句 ⇒ 用"没法确认"一类；否则极短承接
        _ask = bool(getattr(self, "_he_is_asking", False))
        pool = list(self.FALLBACK_ASK if _ask else self.FALLBACK_OTHER)
        # ⑤ 本场已经说过「没法确认」类 ⇒ 换别的说法
        _used = 0
        try:
            for _e in self.ledger.effective_entries:
                _o = getattr(_e, "output", "") or ""
                if any(_w in _o for _w in ("没法确认", "不确定", "说不准", "答不上")):
                    _used += 1
        except Exception:                                          # noqa: BLE001
            _used = 0
        if _used >= 1:
            pool = [x for x in pool if "没法确认" not in x] or pool
        # ④ 6 轮内不重复
        _recent = set(getattr(self, "_fallback_recent", []) or [])
        cand = [x for x in pool if x not in _recent] or pool
        # 选第一个可用的（确定性，不用随机 —— 可重放）
        line = cand[0]
        # ① 硬断言：不含问号（不靠"我选的句子没问题"，靠代码挡）
        assert "？" not in line and "?" not in line, "兜底句不许含问号：%r" % line
        # 记录最近用过的（保留 6 个）
        _r = list(getattr(self, "_fallback_recent", []) or [])
        _r.append(line)
        self._fallback_recent = _r[-6:]
        return line

    def _flush_swallow(self) -> None:
        """把本轮**新增**的吞异常写进 cognition_debug（用户裁定 2026-10-31）。

        ★ 为什么必须落盘：上一批我加了 _swallow() 却只在进程内累加
          ⇒ 实测结束进程一退，那个数就没了 ⇒ 报不出来。
        """
        c = getattr(self, "_swallow_counts", None) or {}
        if not c:
            return
        prev = getattr(self, "_swallow_flushed", None) or {}
        delta = {k: v - int(prev.get(k, 0)) for k, v in c.items()}
        self._swallow_flushed = dict(c)
        if not any(delta.values()):
            return
        self._cog_debug({"kind": "swallow",
                         "turn": getattr(self, "_turn_seq", 0),
                         "counts": delta, "total": sum(delta.values())})

    def _swallow(self, where: str, exc: BaseException) -> None:
        """记一次**被吞掉的异常**（用户裁定 2026-10-31）。

        ★ 为什么必须有它：
          代码里有一批 `except ...: pass` / `except ...: 只留个备注` 的位置。
          它们让主线在子功能失败时继续走 —— 那是对的 ——
          但**一次都不计数，就永远不知道"这一轮到底有几个东西坏了"**。

        ★ 计数怎么用：每次实测结束报 `_swallow_counts`；
          不为 0 就在汇报里标红并列出位置。
        """
        try:
            c = getattr(self, "_swallow_counts", None)
            if c is None:
                c = {}
                self._swallow_counts = c
            key = "%s:%s" % (where, type(exc).__name__)
            c[key] = c.get(key, 0) + 1
            self._swallow_total = getattr(self, "_swallow_total", 0) + 1
        except Exception:                                          # noqa: BLE001
            pass                                   # 计数自己坏了也不许影响主线

    def _cog_debug(self, rec: dict) -> None:
        """把一条认知层调试记录**追加**到 `state/train/cognition_debug.jsonl`。

        ★ 2026-10-30（用户要求：**只加日志，不改行为**）

        ⚠️ 为什么不写进台账：
           `LedgerEntry` 是"她经历过什么"的正式记录，不是调试缓冲。
           往里面塞每轮的 settle 明细会：
             ① 撑大台账，② 让 `source_hashes` 之外的产物也变成"状态"，
             ③ 更糟的是**污染"她记得什么"**。
           ⇒ 单独一个 append-only 文件，出问题能查，平时不读。

        ⚠️ 失败**不许响**：它只是日志，日志写不进去不该影响这一轮的回应。
           但也不许静默 —— 记在 `self._idle_error` 里，能被测试抓到。
        """
        if not getattr(self, "_cog_debug_path", None):
            return
        try:
            os.makedirs(os.path.dirname(self._cog_debug_path), exist_ok=True)
            with io.open(self._cog_debug_path, "a", encoding="utf-8") as _f:
                # ★ 2026-10-31（用户裁定）：每条都带 run_id / session_id。
                #   理由：append-only 文件跨运行累积，没有 run_id 就没法切出本批 ——
                #   我已经因此误报过一次（把两批累积的 31 当成一批的 idle，实际是 17）。
                _rec = dict(rec)
                # ★ 2026-10-31（用户裁定）：每条都带**台账轮次**（不是进程内 _turn_seq）。
                _rec["turn_id"] = self._turn
                _rec["ledger_index"] = max(0, len(self.ledger.effective_entries) - 1)
                try:
                    # ⚠️ 优先用**本轮**的 input_origin（turn 开头就设好了）；
                    #   台账最后一条是上一轮，用它会把 run_id 记错一轮。
                    _o = dict(getattr(self, "_input_origin", None) or {})
                    if not _o.get("run_id"):
                        _e = (self.ledger.effective_entries[-1]
                              if self.ledger.effective_entries else None)
                        _o = dict((getattr(_e, "input_origin", None) or {}) if _e is not None else {})
                    _rec.setdefault("run_id", _o.get("run_id"))
                    _rec.setdefault("session_id", _o.get("session_id"))
                except Exception:                                      # noqa: BLE001
                    pass
                _f.write(json.dumps(_rec, ensure_ascii=False) + "\n")
        except Exception as _exc:                                  # noqa: BLE001
            self._idle_error = "cog-debug:%s: %s" % (type(_exc).__name__, _exc)

    def _settle_previous_encounter(self, prev_index: int, raw_now: str,
                                   mst, claims_now: list) -> None:
        """**单轮内**结算 `t-1 -> t` 这一次遭遇，并当场更新 `boldness`。

        ★ 2026-10-30（五段式管线的 Stage 2）

        ## 为什么它必须在这里（而不是批处理末尾）
          · `Character.learn()` 的批处理只在训练跑完后调一次
            ⇒ 运行期 `boldness` 冻结在上一场的旧值；
          · `shell.py` 真人交互里**根本没有批处理** ⇒ 性格永远不更新。

        ## 为什么不能只查 `entries[-1]`
          "她 BOLD 了"的是 **`t-1`**；而 `entries[-1]` 在本轮写账前是 **`t-1` 自己**
          （写成 `t-2`）—— 口径一错就永远查不到 REBUFFED。
          ⇒ 显式拿 `t-1` 与 `t` 两条去判。

        ⚠️ 幂等：`_last_settled_turn` 挡住重复结算（一次 turn 只能结算一次）。
        """
        if getattr(self, "_last_settled_turn", None) == prev_index:
            return
        self._last_settled_turn = prev_index
        ents = self.ledger.effective_entries
        if prev_index < 0 or prev_index >= len(ents):
            return
        prev = ents[prev_index]
        prev_d = prev.to_dict() if hasattr(prev, "to_dict") else dict(prev)
        if not (prev_d.get("raw_input") or "").strip():
            return
        try:
            from association import classify_encounter, _is_bold as _bold_fn
        except Exception:                                          # noqa: BLE001
            return
        _is_bold = bool(_bold_fn(prev_d))
        _bold_before = None
        try:
            from character import Character as _Ch0
            _bold_before = float(getattr(_Ch0(self.character_path).polarity, "boldness", 0.5))
        except Exception:                                          # noqa: BLE001
            pass
        try:
            cur_d = {"raw_input": raw_now,
                     "action_observation": {},
                     "cognition": {"claims": list(claims_now or [])},
                     "mech": (mst.to_dict() if mst is not None else {})}
            enc = classify_encounter(prev_d, cur_d)
        except Exception as _exc:                                  # noqa: BLE001
            self._idle_error = "settle:%s: %s" % (type(_exc).__name__, _exc)
            return
        self._last_encounter = enc
        # ★ 2026-10-30（用户要求：**只加日志，不改行为**）：
        #   把判定所用的每一项都落盘 ——
        #   否则"为什么这次没判成"永远只能猜（我上一轮就是这样，最后没定案）。
        _dbg = {
            "kind": "settle",
            "turn": getattr(self, "_turn_seq", 0),
            "prev_index": prev_index,
            "bold": bool(_is_bold),
            "encounter": enc,
            "boldness_before": _bold_before,
            "boldness_after": None,
            # 判定时**实际用的** claims（不是台账里存的那些 —— 这两者可能不同）
            "claims_now": [{"kind": c.get("kind"), "text": c.get("text"),
                            "subject": c.get("subject")} for c in (claims_now or [])],
            "claims_prev": [{"kind": c.get("kind"), "text": c.get("text"),
                             "subject": c.get("subject")}
                            for c in ((prev_d.get("cognition") or {}).get("claims") or [])],
            "len_prev": len((prev_d.get("raw_input") or "").strip()),
            "len_now": len((raw_now or "").strip()),
        }
        if not enc:
            self._cog_debug(_dbg)
            return
        try:
            from character import Character
            ch = Character(self.character_path)
            _before = float(getattr(ch.polarity, "boldness", 0.5) or 0.5)
            self._settled_boldness = ch.settle_encounter(enc)
            _dbg["boldness_before"] = _before
            _dbg["boldness_after"] = self._settled_boldness
            self._settle_traces.append("%d→%d %s ⇒ boldness=%.2f"
                                       % (prev_index + 1, prev_index + 2, enc,
                                          self._settled_boldness))
        except Exception as _exc:                                  # noqa: BLE001
            self._idle_error = "settle-save:%s: %s" % (type(_exc).__name__, _exc)
            self._settle_traces.append("FAIL %s" % type(_exc).__name__)
            _dbg["error"] = "%s: %s" % (type(_exc).__name__, _exc)
        self._cog_debug(_dbg)

    def _last_encounter_and_boldness(self) -> tuple[str, float]:
        """上一轮深度遭遇的结果与当前探照笃定度（读不到就返回保守默认）。

        ⚠️ 读不到时返回 `("", 0.5)` —— **不假装"刚被肯定"**，
           也**不假装"刚被拒绝"**。中位值让门控失效，等于回到旧行为。
        """
        try:
            from character import Character
            ch = Character(self.character_path)
            return (str(getattr(ch, "_last_encounter", "") or ""),
                    float(getattr(ch.polarity, "boldness", 0.5) or 0.5))
        except Exception:                                          # noqa: BLE001
            return ("", 0.5)

    def ruminate(self) -> dict | None:
        """**惰性推演**：在两轮之间，她自己想一次（不自发输出）。

        ★ 依据（Gemini Q7 拍板）：
          「你的『惰性推演（Lazy Evaluation）+ 逻辑时钟脉冲』100% 够用，
            而且是唯一正确的工程实现！**绝不要开后台异步常驻线程！**」

        ★ 为什么不开线程：
          一开就会 测试无法重放 / 台账写入竞态 / API 账单失控，
          而我们好不容易建起来的 62/62 可证伪体系会一夜崩塌。

        ★ 那"她真的经历了"吗？
          经历了。因为她的内部状态**确实**多了一条她自己产生的记忆
          （`ruminations.jsonl` + 下一轮 `Frame` 里会浮现）。
          差别只在"什么时候算" —— 这是离散时间步，不是没有时间。

        返回 {op, quotes, at_turn, hint} 或 None。

        ⚠️ 找不到就不想 —— 宁可这一晚什么都没想，也不硬凑。
        """
        if not getattr(self, "_cog_claims", None):
            return None
        try:
            import cognition_ops as _cops
            # ⚠️ 2026-10-29 踩的坑（12 轮实测里"空档回想 0 次"的真因）：
            #   `_cog_claims` 的 key 是 **turn_id（从 1 开始）**，
            #   而 `_cog_rows` 是**位置索引（从 0 开始）**。
            #   我原来传 `spans=[(0, len(_rows))]` ⇒ `_span_of(2)` 在 spans=(0,2) 上
            #   判 `0 <= 2 < 2` 为假 ⇒ **第 2 轮的 claim 直接被丢掉** ⇒ 凑不出跨轮对。
            #   ⇒ spans 必须按**实际 turn_id 范围**构造。
            _keys = sorted(self._cog_claims.keys())
            _lo = _keys[0] if _keys else 0
            _hi = (_keys[-1] + 1) if _keys else 1
            _rows = list(self._cog_rows) or [{"ts": None, "input_origin": None}]
            while len(_rows) <= _hi:
                _rows.append({"ts": None, "input_origin": None})
            _th = _cops.idle_recombine(self._cog_claims, _rows, self._cog_seen,
                                       [(_lo, _hi)])
            if _th is None:
                return None
            # ⚠️ 2026-10-29：`_t` 在我改这一段时被删掉了，但下面 `rec` 里还在用
            #   ⇒ `NameError` ⇒ 被 `except` 记进 `_idle_error`（幸好这次不吞了）
            #   ⇒ 空档回想永远 0 次。
            #   这是同一类"改了上面忘了下面"的错，这一轮第五次。
            _t = _keys[-1] if _keys else 0
            rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "at_turn": _t, "op": _th.op,
                   "quotes": list(_th.quotes), "hint": _th.hint,
                   "sources": list(_th.sources)}
            # ★ 只有 `rec` 构造成功之后才记 seen ——
            #   否则上面一抛异常，`_cog_seen` 就被污染，那一对永远配不上了
            for _src in (_th.sources or []):
                try:
                    self._cog_seen.append((int(_src["turn"]), int(_src["start"]), int(_src["end"])))
                except (KeyError, TypeError, ValueError) as _exc:
                    self._swallow("line746", _exc)
                    pass
            # ★ 痕迹落盘（append-only，独立于台账）
            if self._idle_log:
                try:
                    os.makedirs(os.path.dirname(self._idle_log), exist_ok=True)
                    with io.open(self._idle_log, "a", encoding="utf-8") as _f:
                        _f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                except Exception:                                  # noqa: BLE001
                    pass
            self._idle_thought = _th
            return rec
        except Exception as _exc:                                  # noqa: BLE001
            # ⚠️ **不静默吞掉。** 2026-10-29 踩过：第一版写 `except: return None`，
            #   于是 ruminate 永远返回 None，而调用方完全不知道有异常
            #   —— 和项目铁律禁止的"静默失败"是同一件事，我自己又犯了一次。
            # ⇒ 记下来，让调用方/测试看得见。
            self._idle_error = "%s: %s" % (type(_exc).__name__, _exc)
            return None

    def turn(self, raw: str, topic_id: str | None = None,
             engaged: bool | None = None, *, input_origin: dict | None = None) -> TurnResult:
        from input_provenance import normalize
        self._input_origin = normalize(input_origin, raw, topic_id)
        # ★ 2026-10-31：这些必须在 **turn() 的最开头**算 ——
        #   `_arbitrate_focus` 与 `_build_frame` 都要读它们。
        #   ⚠️ 上一版把它们错放进了 `_prev_thoughts()`（一个被调用的辅助函数），
        #      于是 `_he_is_asking` 在 `_arbitrate_focus` 之前可能是旧值。
        self._idle_thought = None
        self._idle_consumed = None
        self._turn_seq = getattr(self, "_turn_seq", 0) + 1
        # ★ 2026-10-31：他最后一句是不是问句（宽口径，见 association.asks_her）
        #   ⚠️ 在 turn 最开头算，因为 `_arbitrate_focus` 要用它决定 idle 能不能上位。
        try:
            from association import asks_her as _asks_her, asks_her_explicitly as _asks_exp
            self._he_is_asking = bool(_asks_her(raw))
            self._he_is_asking_explicit = bool(_asks_exp(raw))
        except Exception:                                          # noqa: BLE001
            self._he_is_asking = False
            self._he_is_asking_explicit = False
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

        # ★ 2026-10-28（Gemini 第三封 · 发现 3）：**META 劫持漏斗的收窄**。
        #
        #   实测（有 mech 的 24 行）：
        #     · 20 行（83%）planned_behavior=META_REPLY
        #     · 这 24 行全部 mech._carried=True 或 phase=NO_TENSION
        #     · 而 w **全部等于 9.4** —— 24 行同一个值，说明那是**死快照**
        #   ⇒ 机制层在这条路上**整条被跳过**，台账里的"内在状态"是 10 月初的一张照片。
        #
        #   根因：家教（模拟真人）的话里天然带「你说…」「你想过没有…」这类口头禅，
        #   `rule_intent` 一看到问号或口头禅就判 META，而这条分支在 `mech.step()`
        #   （第 436 行附近）**之前**就 return 了。
        #
        #   收窄判据（只有当**真的在问系统本身**时才走 META）：
        #     · 显式问系统（什么模型／你是谁／什么程序／怎么用／在哪跑）⇒ 照旧走 META
        #     · 其余情况：只要话里有**生活锚点**（人名／时间／物／地点，由 `_pick_anchor`
        #       逐字从原话里抽）或命中了**心理标记**，一律归还主干道
        #   ⇒ 这样「你说我是不是有毛病」会被当成倾诉，而不是"向系统提元问题"。
        if intent == "META":
            _sys_q = bool(re.search(
                r"什么模型|哪个模型|你是谁|你是什么|什么程序|怎么用|在哪跑|哪家的|"
                r"你怎么算|你是不是人|你会什么|/why|/where|/help", raw))
            _life = ""
            try:
                _kind, _life = self.responder._pick_anchor(raw)
            except Exception:                                      # noqa: BLE001
                _life = ""
            # ★ 长度判据（实测逼出来的）：被误判 META 的 11 行，输入长度
            #   min=28 / 中位 42 / max 65 —— **全部是长句倾诉**；
            #   而输入 <15 字的 22 行里，META_REPLY **0 行**。
            #   ⇒ 真正的元提问（"你是谁""你是什么模型""你在干嘛"）都很短，
            #     长句几乎一定是倾诉。这条判据不依赖词表，比锚点更鲁棒
            #     （实测 `_pick_anchor` 在"上礼拜…绿萝"上抽不出东西，
            #      还会从"毛病"里切出一个 '病' —— 不能拿它当唯一依据）。
            _long = len((raw or "").strip()) >= 20
            if not _sys_q and (_long or bool(_life) or bool(pr.markers)):
                pr.notes.append(
                    "META 收窄：原判 META（裁决=%s），但输入 %d 字%s%s"
                    " ⇒ 归还主干道，机制层照常推进"
                    % (how, len((raw or "").strip()),
                       "、有生活锚点「%s」" % _life if _life else "",
                       "、命中标记 %s" % pr.markers if pr.markers else ""))
                intent = "ANSWER"
                pr.intent = intent

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
            _last = self._describe_last()
            text, _tn = self._think_or_fallback(
                raw, pr, text, mst=None, last=_last, tag="问系统")
            from action_observation import observe
            # ★ 2026-10-31：**元提问这条支路原来漏传 `focus_origin`** ——
            #   于是它的台账记录里 `focus_origin` 是空串，
            #   看起来像"第五类焦点"，实际只是没传。
            #   ⚠️ 它**不影响她说什么**（`text` 在第 967 行就生成了），
            #      只影响记录的准确性 ⇒ 允许修。
            action = observe(text, behavior, self._last_response_mode, raw=raw,
                             focus_quotes=(),
                             focus_origin=getattr(self, "_focus_origin", "") or "")
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
            self._flush_swallow()      # ★ 吞异常计数落盘
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

        # ★ 2026-10-29 第四次踩同一个坑：
        #   `mech_note = []` 原来定义在下面（机制层那段），而认知块在它**之前**
        #   用了 `mech_note.append(...)` ⇒ `UnboundLocalError`
        #   ⇒ 被认知块的 `except` 吞掉 ⇒ **`use_cognition=True` 从来就没跑通过**。
        #   直到 12 轮实测第一次真正执行这条路径才暴露。
        #   ⇒ 挪到这里（认知块之前），并删掉下面那处重复定义。
        mech_note = []

        # ---------------- 跨轮思考算子层（C4/C5，2026-10-29，默认关闭）
        #
        #   放在这里是因为它需要三样都得先算出来：
        #     · 本轮原话（要抽取 claim）
        #     · `mst`（算子 2 要看机制相位）
        #     · 历史轮的 claims（跨轮匹配）
        #
        #   ⚠️ 这是**唯一**会让她"想到一个具体结构"的地方 ——
        #      没有它，`_build_frame` 拿到的只有抽象标记和读数。
        #   ⚠️ 清理 `_pending_thought` **必须在 `use_cognition` 分支内部**。
        #      2026-10-29 踩过：写成无条件 `self._pending_thought = None`，
        #      于是外部注入（离线回放 / 测试）的 Thought 在 `turn()` 开头就被抹掉了，
        #      C4 的注入路径直接失效（`test_immutable_yield` Y1 抓到的）。
        # ★ 2026-10-29（Gemini 第 ④ 节第 1 条）：原话去标点 < 8 字（"嗯""是啊""不知道"）
        #   没必要花 2 次 API 去抽 —— 直接跳过抽取，但**空档回想照跑**。
        _bare = re.sub(r"[，。；！？、…—\-\s\"\"''「」『』]", "", (raw or ""))
        _too_short = len(_bare) < 8
        if getattr(self, "use_cognition", False) and self.reader is not None \
                and not _too_short:
            self._pending_thought = None
            self._cog_record = None
            try:
                import cognition as _cog
                import cognition_ops as _cops
                _c = _cog.extract(self.reader, raw, passes=2)
                self._cog_claims[t] = _c["claims"]
                self._cog_rows.append({"ts": None, "input_origin": None})

                # ══════════════ [Stage 2: SETTLE 结算上一轮遭遇]
                #
                # ★★ 2026-10-30（架构病灶 1+2：**状态生命周期断层** + **时序倒置**）
                #
                #   病灶 1：`Character.learn()` 原来只在 `train.py` 的 `_regrow()` 里、
                #     36 轮**全部跑完之后**才调一次
                #     ⇒ 36 轮里每轮读到的 `boldness` 都是**上一场的旧值**；
                #     而 `shell.py`（真人交互）**根本没有 `_regrow()`**
                #     ⇒ 跟真人聊天的整个生命周期里，性格**永远不更新**。
                #
                #   病灶 2：`ruminate()` 原来在 `turn()` **一进门**就跑，
                #     而那时 `raw_t` 的 claims **还没抽** ——
                #     系统根本不知道用户刚说的这句就是一次 REBUFFED。
                #     ⇒ `_idle_gated` 在 36 轮里**实际生效 0 次**（10+26=36 刚好占满）。
                #
                #   ⇒ 修法：**必须在 `extract` 之后**当场结算 t-1→t。
                #     结算完才轮到 Stage 3 的漏斗（它要读 `_last_encounter`）。
                # ⚠️ 2026-10-30 修的**差一位**：
                #   第 t 轮跑到这里时，台账里只有 t-1 条（本轮还没写账），
                #   索引是 0..t-2。传 `t-1` 就正好 `>= len(ents)` ⇒ **立即返回**，
                #   结算一次都没发生（30+ 轮里 boldness 纹丝不动，就是这个）。
                #   ⇒ 用 `len(ents)-1`（= 真实的上一条）。
                _prev_i = len(self.ledger.effective_entries) - 1
                self._settle_previous_encounter(_prev_i, raw, mst, _c["claims"])
                _spans = [(0, len(self._cog_rows))] if len(self._cog_rows) > 1 else [(0, 1)]
                _ph = {max(0, t - 1): getattr(mst, "phase", "")} if mst is not None else {}
                _th = _cops.think(t - 1, self._cog_claims, self._cog_rows, _ph,
                                  [(0, len(self._cog_rows))])
                # ★ 2026-10-29（Gemini 架构改造 B）：句内两难「A 还是 B」。
                #
                #   为什么它比当轮四算子更重要：用户说「接着改还是先睡一觉」时，
                #   如果系统**没把它识别成任何张力**，`Thinker` 面对的就是一个裸的选择问句
                #   ⇒ 触发预训练里的"助手拒单反射" ⇒ 「这两个我替你挑不了」。
                #   而把它当作"他内心两头在打架"递进去，那句话就说不出来了。
                #
                #   优先级：DILEMMA 排在 CHAIN 之后、单跳之前（见 OP_ORDER）。
                try:
                    _dil = _cops.extract_dilemma(raw)
                except Exception:                                  # noqa: BLE001
                    _dil = None
                if _dil is not None:
                    _id = _cops.OP_ORDER.index("DILEMMA")
                    _it = (_cops.OP_ORDER.index(_th.op)
                           if _th is not None and _th.op in _cops.OP_ORDER else 99)
                    if _it > _id:
                        if _th is not None:
                            _dil.yielded = [_th.op]
                        _th = _dil
                # ★ 2026-10-29（Gemini 第 ③ 步）：2 环连锁。
                #   优先级按 `OP_ORDER`：算子 3 > CHAIN > 单跳。
                #   所以只有当**没有算子 3**时，连锁才可能上位。
                try:
                    _chain = _cops.chain_extension(
                        t - 1, self._cog_claims, self._prev_thoughts(),
                        self._thought_levels())
                except Exception:                                  # noqa: BLE001
                    _chain = None
                if _chain is not None:
                    _i3 = _cops.OP_ORDER.index("HABITUATION_LOOP_BREAK")
                    _ic = _cops.OP_ORDER.index("CHAIN_EXTENSION")
                    _it = (_cops.OP_ORDER.index(_th.op)
                           if _th is not None and _th.op in _cops.OP_ORDER else 99)
                    if _it > _i3 > _ic or _it > _ic:
                        if _th is not None and _th.op != "HABITUATION_LOOP_BREAK":
                            _chain.yielded = [_th.op]
                            _th = _chain
                self._pending_thought = _th
                # ★ 2026-10-29（Gemini 第 ① 步）：`claims` 一并写进台账。
                #   他原话是「每一轮存进台账的这 4 类原话片段」——
                #   我第一版只存了 Thought，漏了 claims，所以重启后她的
                #   跨轮匹配历史会清零。
                self._cog_record = ({
                    "op": _th.op, "quotes": list(_th.quotes),
                    "hint": _th.hint, "yielded": list(_th.yielded),
                    "sources": list(_th.sources),
                    "origin": "input",
                    "claims": list(_c["claims"]),
                } if _th is not None else
                    ({"origin": "input", "claims": list(_c["claims"])}
                     if _c and _c.get("claims") else None))
                if _c is not None:
                    mech_note.append("认知抽取=%d 条 claim（字面校验后）｜思考=%s"
                                     % (len(_c["claims"]),
                                        _th.op if _th is not None else "无"))

                # ══════════════ [Stage 3: ARBITRATE 单焦点短路仲裁]
                #
                # ★★ 2026-10-30（架构病灶 4：**多头竞争与观测盲区**）
                #
                #   `Frame` 里原来同时挂着四套注意力指令
                #   （`anchor/concrete`、`thought`、`unfinished_focus`、`idle_thought`），
                #   在没有当轮算子的 26 轮里**轮轮塞 idle**
                #   ⇒ 直接淹没高价值的 `unfinished_focus`
                #   ⇒ 自我连续性从 6/36 跌到 3/36。
                #
                #   ⇒ 改成**短路求值**：前序命中就绝不再调后续（也就不会白耗 seen_pairs）。
                #     P1 input > P2 unfinished > P3 idle > P4 词级
                self._arbitrate_focus(raw, mst, mech_note)
            except Exception as _exc:                              # noqa: BLE001
                # 认知层失败**不许阻断主线** —— 它只是"注意力提示"，
                # 没有它系统照旧能回应（只是回到"只有抽象标记"的状态）。
                self._pending_thought = None
                mech_note.append("认知层降级：%s" % type(_exc).__name__)

        # ---------------- 回应选择
        # 关键设计（这是本次改动的核心）：
        #   有直接观察证据（标记命中）→ 用证据选行为，与旧行为一致，不动；
        #   没有直接观察证据（实测占 2/3 的轮次）→ 由**机制状态**决定说什么。
        #
        # 这样就不再有"抓不到特征就只会复述或沉默"的死角：
        #   机制层没有新输入也会演化，所以它永远有状态可报告。
        # 而文字仍然一字不改地来自 behaviors.json 的模板 —— 不生成。
        observed = bool(pr.markers)
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

        # ---- ★ 2026-10-29（C4 的让位规则，Gemini 两封信都点名要的一条）
        #
        #   当跨轮思考算子层触发 `IMMUTABLE_VS_ACTION_SPLIT` 时，
        #   阶梯的 `TURN_IMMUTABLE` **必须让位** —— 否则两条指令打架：
        #     · `TURN_IMMUTABLE` 的模板只说「这一块改不了。改不了的部分之外，还有别的吗？」
        #     · 而 Thought 已经把「哪半截定了 + 哪半截是他自己做的」两条原话都找齐了
        #   ⇒ 前者只处理处境，后者才是真正的洞察。
        #
        #   **让给 `JUXTAPOSE`**：Thought 本身就是"把两处原话并排摆出来"，
        #   而那正是 `JUXTAPOSE` 的定义 —— 所以这不是换一个新动作，是**同类里更具体的那一个**。
        #
        #   ⚠️ 只在两个条件同时成立时让位：
        #     ① 本轮确实有 `IMMUTABLE_VS_ACTION_SPLIT` 的 Thought
        #     ② 阶梯原本给的就是 `TURN_IMMUTABLE`
        #   ⇒ 不会影响其他任何情形。
        _th_yield = getattr(self, "_pending_thought", None)
        if _th_yield is not None and getattr(_th_yield, "op", "") == "IMMUTABLE_VS_ACTION_SPLIT" \
                and bid == "TURN_IMMUTABLE":
            mech_note.append("跨轮思考层触发「死局与活口切分」→ TURN_IMMUTABLE 让位"
                             "（Thought 已把两处原话找齐，比只说「这一块改不了」更具体）")
            bid = "JUXTAPOSE"
            # ★ 让位后的**真实 bid** 单独留痕。
            #   为什么必须记：模板路径上 `JUXTAPOSE` 可能因缺第二个引文槽位退回 REFLECT
            #   （实测「我爸妈已经离婚了，这件事改不了。」就是），
            #   于是只看 `planned_behavior` 分不清"让位没发生"和"让位了但模板兑现不了"。
            #   ⇒ 记下 bid，两者就分得开。
            mech_note.append("让位后的计划动作=%s" % bid)
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
            # * 2026-10-30（Stage 4）：把裁决后的 bid 与 char_note 挂到实例上，
            #   供 _build_frame 组 stance 时读取 —— 模板轨与大脑轨同构的唯一途径。
            #   ⚠️ 必须放在整个 if/elif 块**之后**（第一版插在了 if 与 elif 之间，
            #      直接把语法打断了）。
            self._final_bid = bid
            self._char_note = char_note
            # ★ 2026-10-30（Gemini 拍板）：**每 6 轮刷新一次里程碑**。
            #
            #   为什么需要它：`boldness` 已经由 `settle_encounter()` 单轮实时更新了，
            #   但**里程碑的文字**要跑 `Association.derive_from_ledger` + `Character.learn()`
            #   —— 那是遍历全量台账的重活，不能每轮跑。
            #   ⇒ 每 6 轮一次（`turn_id % 6 == 0`）。
            #   ⚠️ `shell.py` 真人交互里没有外层批处理 ⇒ 这里补上，
            #      退出时再由 shell 补一次（见 shell.py 的 finally）。
            if getattr(self, "use_cognition", False) and t % 6 == 0:
                self._refresh_milestones(mech_note)
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
            _last = self._describe_last()
            _txt, _tn = self._think_or_fallback(raw, pr, ren.output, mst=mst, last=_last)
            # ★ 2026-10-31（兜底修复的真正根因，两处）：
            #   ① `if _tn and "退回" not in _tn:` —— 只有大脑**没退回**才用 `_txt`，
            #      于是大脑失败时 `ren.output` 保持模板，`_fallback_line()` 被丢弃。
            #      ⇒ 现在改成"只要有文本就用"（兜底句要真的说出口）。
            #   ② 但 `response_mode` **不能**跟着变 —— 它表示"这句话是谁想出来的"。
            #      兜底句不是大脑想的，标 brain 会让 `self_action` 走到
            #      `RETURNED_WITHOUT_CHECK_TRACE`，目标核对因此从 MISMATCH 变 UNKNOWN。
            #      ⇒ mode 只在"大脑真的作答"时标 brain。
            if _txt:
                ren.output = _txt
            if _tn and "退回" not in _tn:
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
        # ★ 2026-10-29 漏接的第四处：`observe()` 原来**没传 `thought_quotes`**！
        #   ⇒ `thought_level` 永远算不出来 ⇒ `THOUGHT_EXECUTED_STRONG` 在生产路径上
        #     一次也不会触发 ⇒ C5 等于没接上。
        #   （C4 实测里能看到 `thought_level`，那是测试自己传的。）
        # ★ 2026-10-30（Stage 5，Gemini 拍板的零混淆扩展）：
        #   `thought_quotes` **只**放当轮算子的那两段（语义不污染），
        #   而「本轮唯一胜出的焦点」另走 `focus_quotes` / `focus_origin`。
        _th_for_observe = getattr(self, "_pending_thought", None)
        _quotes_for_observe = tuple(getattr(_th_for_observe, "quotes", ()) or ())
        _focus_origin = getattr(self, "_focus_origin", "lexical")
        _focus_quotes = _quotes_for_observe
        if _focus_origin == "unfinished":
            _uf = getattr(self, "_unfinished_focus", None) or {}
            _focus_quotes = tuple(_uf.get("quotes") or ())
        elif _focus_origin == "idle":
            _idle_o = getattr(self, "_idle_thought", None)
            _focus_quotes = tuple(getattr(_idle_o, "quotes", ()) or ())
        elif _focus_origin != "input":
            _focus_quotes = ()
        # ★ 2026-10-31（用户裁定）：**兜底轮在动作统计里单列 `fallback`**，
        #   不进 QUESTION / ASK_DETAIL，也不算 BOLD 探照。
        #   ⚠️ 但他在这轮之后说的话，**仍然照常结算**
        #      —— 结算发生在下一轮开头，与这一轮的 mode 无关。
        _was_template = bool(getattr(self, "_brain_failed", False))
        action = observe(ren.output, planned_behavior, response_mode,
                         goal_result=_goal_result, raw=raw,
                         thought_quotes=_quotes_for_observe,
                         focus_quotes=_focus_quotes,
                         focus_origin=_focus_origin)
        if _was_template:
            action["actual"] = "FALLBACK"
            action["fallback"] = True
        ren.behavior = action["actual"]
        mech_note.append("实际动作=" + json.dumps(action, ensure_ascii=False))
        # ★ 2026-10-30：idle 的 sources + 与输出的逐字重合度（只记，不判）
        if getattr(self, "_pending_idle_rec", None):
            _ir = self._pending_idle_rec
            _qs = [q for q in (_ir.get("quotes") or []) if q]
            _hit = [q for q in _qs if q in (ren.output or "")]
            self._cog_debug({
                "kind": "idle",
                "turn": getattr(self, "_turn_seq", 0),
                "quotes": _qs,
                "sources": _ir.get("sources") or [],
                "hit": _hit,
                "overlap": round(len(_hit) / float(max(1, len(_qs))), 2),
                "seen_size": len(getattr(self, "_cog_seen", []) or []),
            })
            self._pending_idle_rec = None
        if learning_context is not None and action["confirmed"] and ren.behavior in {"REFLECT", "ASK_DETAIL"}:
            learned_event = self.behavior_learning.observe(learning_context, ren.behavior, raw, t)
            if learned_event:
                mech_note.append("经历规则事件：%s" % learned_event)
        self.mech.note_orientation("内" if ren.behavior == "REPORT_OWN_STATE" else
                                   "外" if action["confirmed"] else "无")

        # ---- ★ 2026-10-29（Gemini 架构改造 A）：**自主悬念对象（unfinished_focus）**
        #
        #   `unfinished` 原来只是一个布尔值，注释里我自己写着
        #   `numerical_proxy_without_autonomous_goal_object` —— 那是对的，
        #   一个布尔值撑不起"主体感"。人心里挂着的是**一个具体的东西**：
        #     「我刚就这两处拉扯问了你一句，我还在等着听你怎么答。」
        #
        #   两种情形会产生它（都在 `mst.unfinished` 为真时）：
        #     ① **想到了但还没说透**：本轮有 Thought，但她没把它说出来（不是 STRONG）
        #     ② **追问了还在等下文**：本轮有 Thought，且她的回应是个问句
        #   ⇒ 记下来，下一轮进 `Frame`。
        #
        #   ⚠️ 张力消解（`unfinished` 变假）就**清空** ——
        #      否则她会永远挂着一个早就过去了的悬念。
        if getattr(self, "use_cognition", False):
            _th_u = getattr(self, "_pending_thought", None)
            _idle_u = getattr(self, "_idle_thought", None)
            _src_u = _th_u if _th_u is not None else _idle_u
            # 2026-10-30（Gemini 破案 1 第二半）：用完即焚。
            #   本轮若选中过 P2，而本轮没有产生新的未说透 P1，就把旧的清掉。
            if getattr(self, "_unfinished_consumed", False) and not (
                    _src_u is not None
                    and (((action or {}).get("thought_level") or "") != "STRONG"
                         or (action or {}).get("actual") == "QUESTION")):
                self._unfinished_focus = None
            self._unfinished_consumed = False
            if not getattr(mst, "unfinished", False):
                self._unfinished_focus = None
            elif _src_u is not None and getattr(_src_u, "quotes", None):
                _lv = (action or {}).get("thought_level") or ""
                _asked = (action or {}).get("actual") == "QUESTION"
                if (_lv != "STRONG") or _asked:
                    # 2026-10-30：带上 turn_seq 与 session_id ——
                    #   _arbitrate_focus 要靠它们判"是不是紧挨着的下一轮"。
                    try:
                        _sess = ((self.ledger.effective_entries[-1].input_origin or {})
                                 .get("session_id") if self.ledger.effective_entries else None)
                    except Exception:                              # noqa: BLE001
                        _sess = None
                    self._unfinished_focus = {
                        "op": _src_u.op, "quotes": list(_src_u.quotes),
                        "turn": getattr(self, "_turn_seq", 0),
                        "session_id": _sess}
                    mech_note.append("自主悬念：还挂着「%s」×「%s」（%s）"
                                     % (_src_u.quotes[0], _src_u.quotes[-1],
                                        "追问等下文" if _asked else "想到了没说透"))
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
                  raw_input=raw, action_observation=action,
                  cognition=getattr(self, "_cog_record", None))

        self._flush_swallow()      # ★ 吞异常计数落盘
        return TurnResult(markers=pr.markers, band=est.band, direction=est.direction,
                          channel=dec.channel, level=dec.level, behavior=ren.behavior,
                          output=ren.output, relation=pr.relation_hint,
                          counterfactual=cf, notes=notes,
                          planned_behavior=planned_behavior, action_observation=action,
                          self_action=self._self_action_trace,
                          mech=_mech_snap, mech_phase=mcond.id,
                          mech_action=mcond.action, character_note=char_note, **base)

    # ------------------------------------------------------------ 思考简报


    def _prev_thoughts(self) -> dict:
        """从台账读"前几轮已形成的 Thought"（供 2 环连锁的第 1 环）。

        返回 `{turn: {"op", "quotes", "sources"}}`。
        ⚠️ **`CHAIN_EXTENSION` 本身也在里面** —— 深度锁在 `chain_extension()` 里做，
           不在这里过滤：因为"台账里有什么"和"能拿它当第 1 环"是两件事，
           过滤写在算子内部，测试才抓得住（`test_chain_extension` C4）。
        """        # ★★ 2026-10-29 修一个**位置错**（它让"空档回想"在 60 轮里永远是 0 次）：
        #
        #   第一版把这段写进了 `_describe_last()` —— 而那个函数**每轮都会被调用**
        #   （组装"上一轮"时），于是它每次都把自己刚产生的 `_idle_thought` 抹掉。
        #   ⇒ 离线重算证明 `idle_recombine` 在那 36 轮上能配出 **15 条**，
        #     可线上一条也到不了 Frame。**算法没错，是它被放在了一个每轮都会清空它的地方。**
        #
        #   ⇒ 正确位置：`turn()` 的最开头，且**先清上一轮的，再让这一轮产生新的**。
        # ★ 2026-10-30（主线任务 1）：**刚碰了钉子就先收一收** ——
        #   如果上一轮她亮出拉扯后对方收住了（REBUFFED），或探照笃定偏低（< 0.42），
        #   这一轮**不抛空档回想**。有眼色的人不会碰壁之后紧接着翻旧账。
        #
        #   ⚠️ 这是 `boldness` / 遭遇**第一次真正改变她的行为**（之前它只是个读数）。
        #   ⚠️ 它只**减少**回想，从不增加 —— 方向与防讨好结构一致。
        out = {}
        for i, e in enumerate(self.ledger.effective_entries):
            cog = getattr(e, "cognition", None) or {}
            if cog.get("op") and cog.get("quotes"):
                out[i] = {"op": cog["op"], "quotes": list(cog["quotes"]),
                          "sources": list(cog.get("sources") or [])}
        return out

    def _thought_levels(self) -> dict:
        """从台账读"每一轮她有没有真的执行那条思考"（供紧邻轮承接判据）。"""
        out = {}
        for i, e in enumerate(self.ledger.effective_entries):
            a = getattr(e, "action_observation", None) or {}
            lv = a.get("thought_level")
            if lv:
                out[i] = lv
        return out

    def _describe_last(self) -> str:
        """上一轮的"我"是什么样 —— **不只是动作名**。

        ★ 依据（Gemini 第 ① 步）：
          「把她上一轮实际说的句子 + 上一轮脑子里的 `cognition.thought`
            （而不仅是一个干巴巴的动作名 `"REFLECT"`）传进 `Frame.last`，
            让她第一次能『看见自己上一轮想了什么』」

        ⚠️ 实测（2026-10-29）：
          改之前 `last` 就一个动作 ID ⇒ 「我上一轮 / 我一直在想」在 40 条输出里
          出现 **0 次**；而她的自我连续性只能靠输入里有没有同样的词，
          那不是"连续性"，是"巧合"。
        """

        if not self.ledger.effective_entries:
            return "（这是第一次）"
        e = self.ledger.effective_entries[-1]
        parts = ["上一轮你选了「%s」" % getattr(e, "behavior", "?")]
        _out = (getattr(e, "output", "") or "").strip()
        if _out:
            parts.append("你说的是「%s」" % (_out[:120] + ("…" if len(_out) > 120 else "")))
        _cog = getattr(e, "cognition", None) or {}
        _hint = _cog.get("hint") or ""
        if _hint:
            parts.append("你当时注意到的是：%s" % _hint[:160])
        return "｜".join(parts)

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
            # ★ 2026-10-30（主线任务 1）：**`boldness` 必须在她看得见的地方。**
            #
            #   实测缺陷：线上 `mst` **永远不为 None**，
            #   而 `boldness` 只出现在下面那个 `elif`（`ch.polarity_basis()`）里。
            #   ⇒ **连她自己的大脑都看不见这个读数** ——
            #     那它 "从 0.50 长到 0.74" 就只是一个躺在 JSON 里的死数字。
            #
            #   ⚠️ 这一句只是把**已有的数**拼进简报，不改任何行为。
            if ch is not None:
                _bd = getattr(ch.polarity, "boldness", None)
                _basis = getattr(ch, "_boldness_basis", None) or {}
                if _bd is not None:
                    state += "｜探照笃定 %.2f（确认 %d 次 / 受挫 %d 次）" % (
                        _bd, int(_basis.get("confirmed", 0)), int(_basis.get("rebuffed", 0)))
                # ★ 2026-10-30（Gemini 破案 2 根因 A）：
                #   原来门槛写的是 `boldness >= 0.60`，而这 36 轮的**最高值只有 0.59**
                #   （终值 0.56）⇒ 那句鼓励**整整 36 轮一次都没触发（0/36）**。
                #   ⇒ 下调到 0.52（= 净确认 ≥1 次），或者上一轮刚刚 CONFIRMED 也解锁。
                _last_enc = getattr(ch, "_last_encounter", "")
                if (_bd is not None and _bd >= 0.52) or _last_enc == "CONFIRMED":
                    state += ("｜（对方接住了你的话 —— 若有好奇或挂着的事，"
                              "可直接用「我想知道」「我一直在想」开口）")
                _last_enc = getattr(ch, "_last_encounter", "")
                if _last_enc:
                    state += "｜上一轮亮出拉扯后：%s" % (
                        "他接着往深处说了" if _last_enc == "CONFIRMED" else "他收住了/没往深处说")
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
        # ★ 2026-11-01（用户裁定「根源记忆保底」）：
        #
        #   病灶：`retrieve()` 只按**关键词重合**捞历史，捞不到就返回 []。
        #   ⇒ 同一场聊天里，管理员换个词，她就"本场失忆"，
        #     于是顺着「你上次也说过」认下（索引 508/772/868 三次都是这么来的）。
        #
        #   ⇒ 修法：**同一场会话内最近 5 轮保底并入 sources**（按 ledger_index 去重排序）。
        #     这样她永远看得见自己前几句刚说过什么。
        #
        #   ⚠️ 只在**同 session** 内保底，不跨场；且不含当前轮（当前轮还没写账）。
        try:
            _cur_sess = (getattr(self, "_input_origin", None) or {}).get("session_id")
            _cur_rid = (getattr(self, "_input_origin", None) or {}).get("run_id")
            if _cur_sess is not None:
                _ents = list(self.ledger.effective_entries)
                _have = {s.get("ledger_index") for s in sources}
                _floor = []
                for _i in range(len(_ents) - 1, -1, -1):
                    _e = _ents[_i]
                    _o = getattr(_e, "input_origin", None) or {}
                    if _o.get("session_id") != _cur_sess:
                        continue
                    if _cur_rid and _o.get("run_id") not in (None, _cur_rid):
                        continue
                    if _i in _have:
                        continue
                    _d = _src_rec(_i, _e.to_dict())
                    _d["origin"] = "同场保底"
                    _floor.append(_d)
                    if len(_floor) >= 5:
                        break
                if _floor:
                    sources.extend(_floor)
                    sources.sort(key=lambda s: s.get("ledger_index") or 0)
        except Exception as _exc:                                  # noqa: BLE001
            self._swallow("session-floor", _exc)
        relational_context = {}
        if self.use_relational_memory:
            from relational_memory import project
            relational_context, linked_sources = project(
                self.ledger.effective_entries, raw, getattr(self, "_input_origin", None),
                current=getattr(self, "_proposition_reading", None))
            existing = {s["source_id"] for s in sources}
            sources.extend(s for s in linked_sources if s["source_id"] not in existing)
            sources.sort(key=lambda s: s["ledger_index"])

        # ★ 2026-10-29（Gemini 抓的真凶 2 第二半，我采纳）：
        #   跨轮思考层的 `sources` 引用到的历史台账行，也必须并进 `dialogue_sources`。
        #   ⇒ 否则 `content_fidelity` 会把"我刚才还在想你前面说的「…」"
        #     判成 `unsupported_fact` 枪毙掉。
        #   ⚠️ 只并**她真的被允许引用的那几行**（由 `Thought.sources` 精确给出），
        #      不是"把所有历史都塞进去" —— 那会让 `content_fidelity` 形同虚设。
        try:
            from dialogue_memory import source_record as _src_rec
            _need = set()
            for _t in (getattr(self, "_pending_thought", None),
                       getattr(self, "_idle_thought", None)):
                for _s in (getattr(_t, "sources", ()) or ()):
                    try:
                        _need.add(int(_s["turn"]))
                    except (KeyError, TypeError, ValueError) as _exc:
                        self._swallow("line1775", _exc)
                        pass
            _have = {s["ledger_index"] - 1 for s in sources}
            for _i in sorted(_need - _have):
                if 0 <= _i < len(self.ledger.effective_entries):
                    try:
                        sources.append(_src_rec(_i, self.ledger.effective_entries[_i].to_dict()))
                    except Exception:                              # noqa: BLE001
                        pass
            sources.sort(key=lambda s: s["ledger_index"])
        except Exception:                                          # noqa: BLE001
            pass

        from memory_scope import describe
        memory_scope = describe(self.ledger.effective_entries, raw, self._input_origin,
                                current=getattr(self, "_proposition_reading", None))
        # ★ 留在 self 上，供 _log() 写进台账（2026-10-28）。
        #   原来它只随 Frame 交给大脑，**用完就丢** ⇒ 台账里从来没有"当时看得到多少"。
        self._memory_scope = dict(memory_scope)
        # ★ 2026-10-28（Gemini 第三封 · 改动 ①）：给大脑三个**具体支点**。
        #
        #   为什么必须在这里算：`_pick_anchor`（respond.py）和 `_pick_concrete`
        #   （render.py）这两个"从用户原话里逐字抠出具体物"的算子，原来只被
        #   renderer 路径调用 —— 而 renderer 在训练中从不执行
        #   （`train.py:330 use_render=False` + `pipeline.py:632 elif` 双保险）。
        #   ⇒ 她从来没拿到过具体支点，只能说一句"没听出什么"+原话 ⇒ 回声。
        #
        #   ⚠️ 三个值全部**逐字来自用户原话**或**确定性映射**，没有一个字是编的。
        #   ⚠️ 取不到就是空串，绝不补一个假的锚点（补了就变成"引用他没说过的词"）。
        _anchor = ""
        try:
            _k, _anchor = self.responder._pick_anchor(raw)
        except Exception:                                          # noqa: BLE001
            _anchor = ""
        _concrete = ""
        try:
            from render import _pick_concrete
            _concrete = _pick_concrete(raw) or ""
            # ★ 守卫（实测逼出来的）：`_pick_concrete` 在**没有体验词**时会退回
            #   "最长小句"（render.py:237 `return max(cands, key=len)`）。
            #   那对渲染路径是对的（它本来就要复述内容），但对 Frame 是**反效果**：
            #   实测「你说我这是不是有点毛病啊。」抽出的"具体画面"**就是整句**，
            #   塞进【具体画面】等于在教她复述。
            #   ⇒ 超过原文 60% 长度就当没抽到。宁可空着，也不给一个假的支点。
            if _concrete and len(_concrete) > 0.6 * max(1, len((raw or "").strip())):
                _concrete = ""
        except Exception:                                          # noqa: BLE001
            _concrete = ""
        _stance = ""
        try:
            from stance import stance_for
            _phase = getattr(mst, "phase", "") if mst is not None else ""
            _stance = stance_for(_phase,
                                 rejected=bool(getattr(mst, "rejected", False)),
                                 streak=int(getattr(mst, "reject_streak", 0) or 0),
                                 # * 2026-10-30（Stage 4）：必须把性格层裁决后的 bid 传进去
                                 #   否则 modulate 在刹车，而 stance 还在按原始相位踩油门
                                 final_bid=getattr(self, "_final_bid", None),
                                 char_note=getattr(self, "_char_note", None),
                                 last_encounter=getattr(self, "_last_encounter", "") or "",
                                 boldness=getattr(ch.polarity, "boldness", None)
                                 if ch is not None else None)
        except Exception:                                          # noqa: BLE001
            _stance = ""
        # ★ 2026-10-31（主线）：**他问她 ⇒ 第一句必须先接住**。
        #   ⚠️ 第一版写在 `fr` 上 —— 而 `fr` 在函数末尾才创建，
        #      那段代码永远抛 NameError 且被外层吞掉（M4 抓到）。
        #   ⇒ 正确位置：`_stance` 组装完之后。
        if getattr(self, "_he_is_asking", False):
            # 2026-10-31（用户裁定）：不再给固定句式，只给原则。
            #   上一版写死了「就如实说『这个我没法确认』」，结果 11 轮里 7 轮
            #   开头就是那一句 —— 成了口头禅。口头禅的问题不是不礼貌，
            #   是它把「我没看到」变成了万能挡箭牌。
            _used = 0
            try:
                for _e in self.ledger.effective_entries:
                    _o = getattr(_e, "output", "") or ""
                    if any(_w in _o for _w in ("没法确认", "不确定", "说不准", "答不上")):
                        _used += 1
            except Exception:                                      # noqa: BLE001
                _used = 0
            _extra = ("【硬约束·先接住】他最后一句是在问你。"
                      "你这一轮**第一句就必须先回应他问的那件事**。怎么回应，看它属于哪一种：\n"
                      "· 他问的是**他自己心里的事、你看不到的事实**（「我是不是…」「你说我…」）："
                      "如实说你看不到 —— 但**每次换一种说法**，别用同一句；"
                      "并且**接一句你能从他原话里看到的东西**，否则就只是推掉。\n"
                      "· 他问的是**「你怎么看 / 算不算 / 是不是」**："
                      "给出**你自己的看法**，一句话，带理由，理由必须来自他的原话。"
                      "**允许你不同意他**，不要一味附和。\n"
                      "· 引他以前的原话只能放在**回应之后**；引号内必须是他原话的逐字片段。")
            if _used >= 1:
                _extra += ("\n【这一条你已经用过】这场对话里你已经说过 %d 次"
                           "「没法确认」这类话了。**这一轮不许再用**。" % _used)
            _stance = ((_stance + "\n") if _stance else "") + _extra
        # ★ 2026-10-29（C4）：把跨轮思考算子层产出的观察送进简报。
        #
        #   来源是 `self._pending_thought`（由 `turn()` 在认知层跑完后挂上，
        #   或由测试/离线回放直接注入）。没有就是空 —— 绝不为了"显得聪明"补一条。
        _th = getattr(self, "_pending_thought", None)
        _th_hint = getattr(_th, "hint", "") if _th is not None else ""
        _th_quotes = tuple(getattr(_th, "quotes", ()) or ()) if _th is not None else ()
        # ★ Q4：空档里她自己想起来的那一条（没有就是空）
        _idle = getattr(self, "_idle_thought", None)
        _idle_hint = getattr(_idle, "hint", "") if _idle is not None else ""
        # ★ 架构改造 A：把"还没落地的悬念"送进简报
        _uf = getattr(self, "_unfinished_focus", None) or {}
        _uf_hint = ""
        if _uf.get("quotes"):
            _qs = list(_uf["quotes"])
            # ★ 2026-10-30（Gemini 破案 1 第二半）：**对齐 P1/P3 的高落地率写法**。
            #
            #   原来只写了软绵绵的"顺着往下接" —— **没要求用「」引原话**，
            #   而 P1 的 hint 明确写着"把这两处原话用「」并排点出来"。
            #   ⇒ 实测：P1 落地 60%，P3 落地 50%，而 P2 **落地 0/21**。
            #   ⇒ 差的就是"**务必带引号逐字点出至少一段**"这一句。
            _uf_hint = ("【你心里还没落地的悬念】上一轮他说的「%s」和「%s」，"
                        "你心里还挂着没聊透。"
                        "这一轮请直接用「我还在想你刚说的『%s』——」"
                        "或「有件事我想知道：你前面说『%s』……」把话接下去。"
                        "**务必带引号逐字点出其中至少一段原话。**"
                        % (_qs[0], _qs[-1], _qs[-1], _qs[-1]))
        # ★ §一（Gemini 的核对项）：idle 被**真的注入**这一轮时，
        #   把它的 quotes + `origin="idle"` 记进本轮的 `cognition`，
        #   并标记消费 —— 这样：
        #     ① `C5` 能核对她这一轮到底有没有把这条空档回想说出口
        #     ② 下一轮 `ruminate()` 从台账的 `sources` 里看到这对已用过，不会重复想
        if _idle is not None and _idle_hint and not _th_hint:
            self._idle_consumed = _idle
            if self._cog_record is None:
                self._cog_record = {}
            self._cog_record["idle"] = {
                "op": _idle.op, "quotes": list(_idle.quotes),
                "sources": list(_idle.sources), "origin": "idle"}
        return Frame(raw=raw, observations=obs, self_state=state,
                     anchor=_anchor, concrete=_concrete, stance=_stance,
                     thought=_th_hint, thought_quotes=_th_quotes,
                     idle_thought=_idle_hint, unfinished_focus=_uf_hint,
                     milestones=figs, last=last, self_facts=self_facts, dialogue_sources=sources,
                     relational_context=relational_context, memory_scope=memory_scope)

    def _think_or_fallback(self, raw: str, pr, fallback: str, mst=None,
                           last: str = "（这是第一次）", tag: str = "") -> tuple[str, str | None]:
        """让大脑想；想不出来（或没过闸门）就用 fallback。返回 (文本, 留痕)。"""
        self._last_response_mode = "template"
        # ★ 2026-10-31：**区分"兜底"和"本来就是模板"**。
        #   `thinker is None`（离线/测试）时，模板就是预期回应，
        #   不是"大脑失败了" ⇒ 不该被标成 FALLBACK。
        self._brain_failed = False
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
            return sp.text, "L0':大脑作答%s（%s）" % (
                ("·" + tag) if tag else "", (sp.reason or "")[:40]) + journal_note
        detail = ("；".join(sp.violations or []) or (sp.reason or "")) + journal_note
        # ★ 2026-10-31（用户要求「失败分类落盘」）
        try:
            from association import classify_failure, failure_detail
            _att = getattr(self.thinker, "last_attempts", []) or []
            _etypes = [a.get("error_type") for a in _att if a.get("error_type")]
            _viols = [str(x) for a in _att for x in (a.get("violations") or [])]
            _kind = classify_failure(_etypes[0] if _etypes else "", _viols, sp.reason or "")
            _desc = failure_detail(_etypes[0] if _etypes else "", _viols, sp.reason or "")
            self._cog_debug({"kind": "brain", "turn": getattr(self, "_turn_seq", 0),
                             "mode": "template", "fail_class": _kind,
                             "fail_detail": _desc, "error_types": _etypes,
                             "violations": _viols[:3], "attempts": len(_att),
                             "retry_log": []})
        except Exception as _exc:                          # noqa: BLE001
            self._idle_error = "fail-classify:%s: %s" % (type(_exc).__name__, _exc)
        # ★ 2026-10-31：**换掉传进来的模板兜底**，用 `_fallback_line()`。
        self._brain_failed = True
        return self._fallback_line(), "L0':大脑作答退回（%s）" % detail[:160] + "｜尝试=" + json.dumps(getattr(self.thinker, "last_attempts", []), ensure_ascii=False)
    # ------------------------------------------------------------ 内部


    def _log(self, turn_id, topic_id, channel, markers, evidence, rule_ids,
             confidence, conflict, relation, behavior, output, counterfactual,
             gear_id, s_used, notes, mech=None, raw_input='', action_observation=None,
             cognition=None):
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
            # ★ 2026-10-29（C2/C5）：本轮跨轮思考层的产出（默认 None）
            cognition=cognition,
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

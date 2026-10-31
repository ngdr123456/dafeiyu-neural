# -*- coding: utf-8 -*-
"""系统**自己**的发展水平，以及"能看见什么"的门控（箭头 A1）。

为什么需要它 —— 全部 2921 条观点里最硬的一条工程事实
────────────────────────────────────────────────────────────
    [E] **E-900**（p249）：
    「第一个困难是：评定人员**觉察的程度**是不可知的，因为这个程度
      **取决于他们自己的自我水平**，而不是正在接受评定的被试的自我水平。」

    注意它说的是**评定者自己**的水平。所以：**系统能看见什么，取决于系统自己的水平。**

    这一条直接否掉"写规则"那条路：
    你不能靠写规则让它注意到某件事 —— **你得让它长到能注意到。**

在此之前，系统的标记词表是**固定的**：不管它经历过什么，同一句话抓到的标记永远一样。
那是死物。A1 就是把这条接上。

生长律不靠我发明 —— 全部有据
────────────────────────────────────────────────────────────
    [E] 平衡化：**现有结构无法同化新经验时就重组**。
    机制层里已经有一个量正好在量这件事：`e`（结构预测误差），
    且 `|e| ≥ error_high(0.60)` 的注释原文就是「平衡化压力**上涨**」。

    所以一次**完整的平衡化** = 结构先失效、后重组出新的平衡：
        |e| ≥ error_high   → 结构失效（失衡）
        之后 |e| ≤ error_low → 重组完成（新平衡）
    两次都发生，才算一次平衡化。**只失效不重组，是过载，不是发展。**

    2026-10-06 核查：上述是工程代理，不是独立重组证据；现行通道公式
    在真实失效后、无重置的连续运行中无法回落至 ERROR_LOW。
    本次只阻止会话重置伪证，结构学习仍缺实现，见 spec/下一步推进_20261006.md。

    [E] 另外两条，直接当纪律用：
      · **纵向、阶段性、不随情境回退** → 水平只升不降，且不受任何单轮影响
      · 水平是**结构**不是内容 → 它不该被"聊了什么话题"改变

⚠️ 我发明的地方（ENG，无书的依据，必须人批）
────────────────────────────────────────────────────────────
    1. **起始水平**（`start_level`）：书里没有说一个系统该从哪一级开始
    2. **升一级需要几次平衡化**（`per_level`）：书里说的是"重组"，没说几次
    3. **哪个标记需要哪一级才能看见**（`min_level`）：
       · 标记表里已有 `level_hint` 的（blame_external→DELTA、cliche/group_sanction→I-3、
         voice_shift/attitude_clause→I-4）**直接用**，那是有据的
       · `level_hint` 为 None 的（opposed_pair / over_intention / want_like_gap /
         present_missing / immutable）**先一律放行**，并标出来等定
         —— 不替它们编一个级别，那正是"手写词表必然有缺口"的老毛病
"""
from __future__ import annotations

# ★ 阈值从 SSOT 取（用户裁定：三处副本合一，方案乙）
import constants as C          # noqa: E402

import io
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包成 exe 后 `__file__` 指向解包出的临时目录 —— 于是 rules/corpus 找不到，
# 而且**台账会写进临时目录、退出就丢**。所以允许用 EGO_ROOT 指定项目根，
# 由启动器（exe）在导入任何引擎模块之前设置。
# 不设 EGO_ROOT 时行为与从前完全一致（源码运行时就是这个分支）。
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 与 state.py 同一份阶梯。[E] 的九级＋过渡级。
LEVELS = ["I-1", "SYM", "I-2", "DELTA", "I-3", "I-3/4", "I-4", "I-4/5", "I-5", "I-6"]
IDX = {lv: i for i, lv in enumerate(LEVELS)}

DEFAULT_STATE = os.path.join(_ROOT, "state", "devlevel_verified.json")

# ---- ENG 参数（改这里就是改我拍脑袋的部分，别改到别处去）----
START_LEVEL = "I-3"     # ENG：从遵奉阶段起步。理由只是"标记表的多数 level_hint 落在这里"，
                        #      不是书里说的。要你批。
PER_LEVEL = 3           # ENG：几次完整平衡化升一级。书里说"重组"，没说次数。
ERROR_HIGH = C.ERROR_HIGH       # 有据：mechanism.py 的 error_high（「平衡化压力上涨」）
ERROR_LOW = C.ERROR_LOW        # 有据：mechanism.py 的 error_low（「结构停滞」）

# ── 箭头 A5：张力 → 生长（T16）
#
# 书里的依据（三条，逐字核对过）：
#   [M-391]「人对意义的追寻会导致内心的**紧张而非平衡**。」
#   [M-400]「也就是**存在的动力处于一个紧张的极化区**」
#   [M-367]「努力发现生命的意义正是人**最主要的动力**。」
#
# 推论：**张力是"动力"本身。** 没有动力的结构重组，不是意义追寻带来的发展。
#
# 用户裁定（原话）：
#   「弗兰克尔批判的核心是『存在主义真空（无目标、无张力的虚无空转）』。
#     趋零必须坚决排除不计入生长；至于高张力过载，那是前置机制降负载的任务，
#     若在承受高压后仍能完成结构重组，属于**创伤后成长**，不应在此处人为封顶。」
#   → 所以只设**下沿**，**不设上沿**。这是刻意的，不是漏了。
# ── 箭头 A4：态度自由 vs 觉察受限（T18）
#
# 裁决：[spec/冲突裁决表.jsonl] 的 **C3「自由与决定」**（真冲突，已裁决）
#   ruling      分层裁决：**概率层（群体、统计）服从机制；单例层（具体这一次）服从自由**
#   upper_basis [E-154]「在人格问题上，有两个主要的方面**抵抗着结构的论述**，
#                        它们是**自我意识和自由体验**」（主）
#               [E-172]「人格在其构成方面是独特的；它**不可能由逻辑原则的具体事例
#                        或一系列逻辑类别构成**」（辅）
#
# 冲突的确切位置：
#   标记 `attitude_clause`（态度句）带 `level_hint: I-4`，而 `can_see` 是**绝对布尔门控**。
#   起始水平 I-3 → 永远看不见态度句 → **永远走不上态度途径**。
#   但 [M-227] 说：「有一样东西你是不能从人的手中夺去的，那就是最宝贵的自由，
#   人们一直拥有在**任何环境**中选择自己的态度和行为方式的自由。」
#
# 用户裁定（原话）：
#   「态度是面对绝境时的主体姿态（M-227），属于**存在主义维度的基本自由**，
#     不属于受认知复杂性限制的智力技能。因此它应当**跨越发展阶段，在任何水平下
#     均可被觉察**。」
#   「豁免属于**系统治理策略**，不是语言学词表特征。严禁修改纯净的
#     rules\markers.json 数据文件，豁免逻辑完全收敛在 devlevel.py 内部。」
#
# ⚠️ 所以这里**只有一份集合**，且刻意**不放进 markers.json**：
#    那是一个**判断**（态度不受发展门控），不是一条**书本依据**，不该混进有据的词表。
# ⚠️ 也**不做随机化**：用户明令「坚决不采用引入随机概率的方案，
#    保持系统因果逻辑与测试的严格确定性」。
_PATH_EXEMPT = frozenset({"attitude_clause"})
#   只豁免态度途径这一条。`immutable`「不可改变识别」**不在此列** ——
#   它的 `level_hint` 本来就是空的，走 `can_see` 的第一条放行分支，
#   属于「无门控」而不是「豁免」。两者语义不同，不许混（A4-5 锁住这条）。


TENSION_DRIVE = C.TENSION_DRIVE     # 有据：mechanism.py 的 tension_low。
#   注释原文「张力趋零是病态，不是健康」；
#   NO_TENSION 规则原文「张力趋零（**无值得为之努力的东西**）」。
#   低于它 → 无动力，这一次重组不计入生长。

# A2：哪一级解锁哪条"自我对抗"规则。**顺序有据，卡点 ENG。**
#   顺序依据见 self_rules() 的说明（[E] 冲动控制来源的转移）。
_RULE_UNLOCK = {
    "R1": "I-1",        # 最原始：同一个动作做腻了。**任何水平都有**，包括 I-1。
    "R3": "I-3/4",      # 跨会话学到的规律 —— 过渡级之后
    "R2": "I-4",        # 结构失衡时按住不确定 —— 最高
}


def _load_rules() -> list[dict]:
    p = os.path.join(_ROOT, "rules", "markers.json")
    if not os.path.exists(p):
        return []
    with io.open(p, encoding="utf-8") as stream:
        return json.load(stream).get("markers", [])


class DevLevel:
    """系统自己的发展水平 + 感知门控。

    设计上最要紧的一条：**它不是"用户水平估计"的复制品。**
    系统里已经有一套对**用户**水平的估计（`state.py::_band`），
    那是"我在评你"。这一套是"**我自己长到哪了**"。两者不可混用 ——
    混用会让系统的水平被它正在聊的内容拖着走，那就不是发展了。
    """

    def __init__(self, path: str | None = None, rules: list[dict] | None = None):
        self.path = path or DEFAULT_STATE
        self.verified = path is None or os.path.basename(self.path) == "devlevel_verified.json"
        self.baseline = None
        if self.verified and not os.path.exists(self.path):
            from development_baseline import initialize
            self.baseline = initialize(os.path.dirname(os.path.dirname(self.path)), START_LEVEL)
        self.rules = rules if rules is not None else _load_rules()
        self.level = START_LEVEL
        self.equilibration = 0          # 完整平衡化次数
        self.failed = False             # 当前是否处于"结构失效"态
        self.pending = 0                # 累计失效次数（历史字段名保留，非待处理数）
        # ENG 防伪：Pipeline 每场同时新建 DevLevel 和 Mechanism。
        # 失败可跨场保存，但本场清零后的 e 不能证明上一场压力自然回落。
        # 此证据仅属于当前机制生命周期，刻意不落盘、不随 _load 恢复。
        self._failure_observed_here = False
        self.history: list[dict] = []
        # ── 箭头 A5（T16）：张力 → 生长
        self.fail_tension = 0.0         # **失效那一刻**的张力（把它推失衡的动力）
        self.not_grown = 0              # 重组了、但**无动力**所以不计入生长的次数
        self._load()

    # ---------------------------------------------------------- 持久化

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with io.open(self.path, encoding="utf-8") as stream:
                d = json.load(stream)
        except Exception:                          # noqa: BLE001
            if self.verified:
                raise ValueError("Verified baseline unreadable; refusing legacy fallback")
            return
        if d.get("display_projection"):
            self.path = os.path.join(os.path.dirname(self.path), "devlevel_verified.json")
            self.verified = True
            if not os.path.exists(self.path):
                raise ValueError("Canonical baseline missing; display is not development evidence")
            return self._load()
        if self.verified:
            if d.get("baseline_schema") != 1:
                raise ValueError("Invalid verified baseline schema")
            self.baseline = d
        self.level = d.get("level") or START_LEVEL
        self.equilibration = int(d.get("equilibration") or 0)
        self.failed = bool(d.get("failed"))
        self.pending = int(d.get("pending") or 0)
        self.fail_tension = float(d.get("fail_tension") or 0.0)
        self.not_grown = int(d.get("not_grown") or 0)
        self.history = d.get("history") or []

    def save(self) -> None:
        if self.verified:
            from behavior_learning import atomic_json
            data = dict(self.baseline or {})
            data.update(level=self.level, equilibration=self.equilibration,
                        failed=self.failed, pending=self.pending, fail_tension=self.fail_tension,
                        not_grown=self.not_grown, history=self.history,
                        updated=time.strftime("%Y-%m-%d %H:%M:%S"))
            atomic_json(self.path, data)
            atomic_json(os.path.join(os.path.dirname(self.path), "devlevel.json"),
                        dict(data, canonical="state/devlevel_verified.json", display_projection=True))
            self.baseline = data
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        io.open(self.path, "w", encoding="utf-8").write(json.dumps(
            {"_note": "系统自己的发展水平。只升不降（[E]：纵向、阶段性、不随情境回退）。",
             "level": self.level, "equilibration": self.equilibration,
             "failed": self.failed, "pending": self.pending,
             "fail_tension": round(self.fail_tension, 3),
             "not_grown": self.not_grown,
             "history": self.history[-200:],
             "updated": time.strftime("%Y-%m-%d %H:%M:%S")},
            ensure_ascii=False, indent=1) + "\n")

    # ---------------------------------------------------------- 感知门控

    def can_see(self, level_hint: str | None,
                marker_id: str | None = None) -> bool:
        """系统自己到这一级了吗？

        三条放行规则，**顺序有讲究**：

          ① `marker_id` 在 `_PATH_EXEMPT` 里 → **无条件放行**（箭头 A4）。
             态度是存在主义维度的基本自由，不受认知复杂性门控（M-227 + C3）。
          ② `level_hint is None` → 放行。它们是"只作条件判断、不指向水平"的
             可观察事实（如 immutable「不可改变识别」）。**不给它们编一个级别。**
          ③ `level_hint` 不在 IDX 里 → 放行。未知级别不拦，宁可放行不可误封。

        ⚠️ `marker_id` 是**可选**的：不传时行为与从前**完全一致** ——
           改动向后兼容，`pipeline.py` 那种只关心"有没有"的调用点不受影响。
        """
        if marker_id is not None and marker_id in _PATH_EXEMPT:
            return True                            # ① 箭头 A4：态度自由，跨阶段可见
        if not level_hint:
            return True                            # ② 无 level_hint：不编级别
        if level_hint not in IDX:
            return True                            # ③ 未知级别：宁可放行
        return IDX[self.level] >= IDX[level_hint]

    def visible(self) -> set[str]:
        # ⚠️ 必须把 id 一起传进去 —— 豁免是按**标记身份**判的，不是按 level_hint 判的
        return {m["id"] for m in self.rules
                if self.can_see(m.get("level_hint"), m.get("id"))}

    def hidden(self) -> list[dict]:
        """当前**还看不见**的标记 —— 这是"它还没长到那儿"的清单。"""
        return [{"id": m["id"], "label": m.get("label"),
                 "needs": m.get("level_hint")}
                for m in self.rules
                if not self.can_see(m.get("level_hint"), m.get("id"))]

    def ungated(self) -> list[str]:
        """`level_hint` 为空、因而**无法门控**的标记。

        ⚠️ 单独列出来，因为它们是这套设计里的已知缺口：
           它们在书里没有指向某个水平，所以我没拦它们 ——
           但"没拦"不等于"任何水平都该看得见"。这是待你定的清单。
        """
        return [m["id"] for m in self.rules if not m.get("level_hint")]

    def path_exempt(self) -> list[str]:
        """箭头 A4：**豁免发展门控**的标记（当前只有态度途径）。

        ⚠️ 与 `ungated()` **不是一回事**，别混：
             · `ungated()`    —— `level_hint` **为空**，无法门控（数据决定的）
             · `path_exempt()` —— `level_hint` **有值**，但**治理上决定不门控**（判断决定的）
           前者是"拦不了"，后者是"不该拦"。
        """
        return sorted(_PATH_EXEMPT)

    # ---------------------------------------------------------- A2：自我的对抗力量

    def self_rules(self) -> set[str]:
        """自我当前**能行使**哪几条对抗规则（箭头 A2）。

        [E]「自我是内驱力的**对抗者**；然而，自我又是**部分地由内驱力构成**的」

        三条规则本身有发展顺序，不是随便排的：

            R1 耐心     同一个动作连着做、效果递减 —— 最原始（[D] 敏化／习惯化）
            R3 里程碑   跨会话学到的"这个动作多半停在那儿" —— 需要记忆 + 泛化
            R2 结构压力 结构失衡时**不许下断言** —— 需要能按住不确定，最高

        这个顺序对应 [E] 说的**冲动控制来源的转移**：
        从本能的腻（R1）→ 学到的规律（R3）→ 结构性的克制（R2）。
        低水平时只有 R1，自我还拦不下更复杂的东西。

        ⚠️ **ENG**：哪一级解锁哪一条，是我定的（`_RULE_UNLOCK`）。
           "顺序如此"有据（[E] 的阶段描述），"卡在哪一级"没有。
           —— 这不等于"待你批准"：它是**待标定**的占位值，
              该由它自己跑起来的数据定，不该由人或我猜。
        """
        lv = IDX.get(self.level, 0)
        out = set()
        for rule, need in _RULE_UNLOCK.items():
            if lv >= IDX.get(need, len(LEVELS) - 1):
                out.add(rule)
        return out

    # ---------------------------------------------------------- 生长

    def update(self, mech: dict | None) -> dict:
        """吃本轮机制状态，看有没有发生平衡化。**水平只升不降。**

        一次完整平衡化 =
            先  |e| ≥ error_high   （现有结构无法同化）
            后  |e| ≤ error_low    （重组出了新平衡）
        两半必须都发生。只失效不重组 = 过载，**不算发展**。
        本场须重新观测失效；跨场继承 failed 不能为清零后的 e 提供证据。
        此代理判据不能单独证明结构重组。
        """
        if not mech:
            return {"changed": False, "why": "无机制状态"}
        e = abs(float(mech.get("e") or 0.0))
        # ── 箭头 A5：张力是"动力"。失效那一刻的张力，就是把它推失衡的那个力。
        tn_meas = bool(mech.get("tension_measured"))
        tn = float(mech.get("tension") or 0.0)
        before = self.level
        ev = None

        if e >= ERROR_HIGH:
            if not self._failure_observed_here:
                self._failure_observed_here = True
                # 上场失效尚未结案时，重新观测的动力取本场失效点。
                self.fail_tension = tn
            if not self.failed:
                self.failed = True
                self.fail_tension = tn          # ← 记下动力（用户裁定：取失效那一刻）
                self.pending += 1
                ev = ("结构失效（|e|=%.2f ≥ %.2f）｜张力 %s"
                      % (e, ERROR_HIGH,
                         ("%.2f" % tn) if tn_meas else "未测"))
        elif (not self.verified and self.failed and self._failure_observed_here
              and e <= ERROR_LOW):
            # 失效之后重组成功 → 是不是**发展**，还要看有没有动力（A5）
            self.failed = False
            self._failure_observed_here = False
            ft = self.fail_tension
            if not tn_meas:
                # 张力不可测 → **放行**（防冷启动死锁），但**必须显式留痕**
                ok, mark = True, "[张力未测，默认放行]"
            elif ft > TENSION_DRIVE:
                ok, mark = True, "张力 %.2f > %.2f｜有动力" % (ft, TENSION_DRIVE)
            else:
                # 张力趋零 = 「无值得为之努力的东西」→ 这次重组**不算发展**
                ok, mark = False, ("张力 %.2f ≤ %.2f｜**无值得为之努力的东西**"
                                   % (ft, TENSION_DRIVE))
            if ok:
                self.equilibration += 1
                ev = ("平衡化完成（|e| 回落到 %.2f，%s）→ 累计 %d 次"
                      % (e, mark, self.equilibration))
                need = PER_LEVEL
                if self.equilibration % need == 0:
                    i = IDX.get(self.level, 0)
                    if i < len(LEVELS) - 1:
                        self.level = LEVELS[i + 1]
                        ev += "｜**升到 %s**" % self.level
            else:
                # ★ 张力趋零时的重组**不算发展**，但**照记，不静默丢弃**
                self.not_grown += 1
                ev = ("结构重组完成（|e| 回落到 %.2f），但 %s"
                      "｜**不计入生长**（累计 %d 次）" % (e, mark, self.not_grown))

        if ev:
            self.history.append({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                                 "e": round(e, 3), "event": ev, "level": self.level})

        # ★ 落盘移出 `if ev:`（**用户裁定 2026-10-02，方案 (甲)**）
        #
        #   裁定原文：
        #   > 「将 `save()` 从死分支中移出属于典型的『**持久化接线缺陷修复**』，
        #   >   不属于动力学调参。D-013 要求的核心正是『如实记录当前稳态数据』；
        #   >   **稳态未能落盘本身就是未闭环**。准予修复。」
        #
        #   事由（实跑抓到，第 4 次「测试全绿≠真生效」）：
        #   `ev` 只在「结构失效」或「平衡化完成」时非空，而
        #   `e >= ERROR_HIGH(0.60)` 构造上不可达（见 spec/阈值可达性审计.md 第 4 条）
        #   ⇒ `ev` 恒为 None ⇒ **`save()` 从未被调用 ⇒ `devlevel.json` 从不生成**
        #   ⇒ 训练台的只读显示在真机上**永远显示「尚未开始」**。
        #   19/19 测试全绿也没抓到 —— 因为所有测试都**人为喂 e**，没有一条验过
        #   "真实跑一轮之后，文件**在不在**"。
        #
        #   无事件时落盘的是**稳态快照**：level 停在当前级、equilibration/not_grown 为 0、
        #   updated 为真实时间戳。**如实记录，不伪造事件。**
        self.save()

        return {"changed": self.level != before, "level": self.level,
                "event": ev, "equilibration": self.equilibration,
                "pending": self.pending, "failed": self.failed,
                "fail_tension": round(self.fail_tension, 3),
                "not_grown": self.not_grown}

    # ---------------------------------------------------------- 报告

    def report(self) -> dict:
        return {"level": self.level, "index": IDX.get(self.level, 0),
                "equilibration": self.equilibration, "per_level": PER_LEVEL,
                "to_next": PER_LEVEL - (self.equilibration % PER_LEVEL),
                "pending_failures": self.pending, "in_failure": self.failed,
                # 箭头 A5（T16）：生长与张力的关系要**可见**，不藏在内部
                "not_grown": self.not_grown,
                "fail_tension": round(self.fail_tension, 3),
                "tension_drive": TENSION_DRIVE,
                "visible": sorted(self.visible()),
                "hidden": self.hidden(),
                "ungated": self.ungated(),
                "path_exempt": self.path_exempt(),   # A4：豁免门控的标记
                "self_rules": sorted(self.self_rules()),
                "eng": {"start_level": START_LEVEL, "per_level": PER_LEVEL,
                        "rule_unlock": dict(_RULE_UNLOCK)}}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="系统自己的发展水平与感知门控（A1）")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--simulate", type=int, default=0,
                    help="喂 N 轮模拟的结构误差，看它会不会长")
    ap.add_argument("--state", default=None)
    a = ap.parse_args()
    d = DevLevel(a.state)
    if a.simulate:
        import random
        rnd = random.Random(7)
        print("模拟 %d 轮（每次平衡化 = 先 |e|≥0.60 后 |e|≤0.15）" % a.simulate)
        for i in range(a.simulate):
            d.update({"e": rnd.uniform(0.65, 0.95)})      # 失衡
            r = d.update({"e": rnd.uniform(0.02, 0.12)})  # 重组
            if r.get("event"):
                print("  轮%-4d %s" % (i + 1, r["event"]))
        print()
    r = d.report()
    print("=" * 74)
    print("系统自己的发展水平（A1）")
    print("=" * 74)
    print("当前水平：%s（第 %d 级 / 共 %d 级）" % (r["level"], r["index"] + 1, len(LEVELS)))
    print("完整平衡化：%d 次｜再 %d 次升一级（ENG: per_level=%d）"
          % (r["equilibration"], r["to_next"], r["per_level"]))
    print()
    print("现在**看得见**的标记 %d 个：%s" % (len(r["visible"]), "、".join(r["visible"])))
    print()
    print("现在**还看不见**的 %d 个（它还没长到那儿）：" % len(r["hidden"]))
    for h in r["hidden"]:
        print("   · %-18s 需要 %s　%s" % (h["id"], h["needs"], (h["label"] or "")[:22]))
    print()
    print("⚠️ 无法门控的 %d 个（书里没指向任何水平，所以没拦）：%s"
          % (len(r["ungated"]), "、".join(r["ungated"])))
    print("   ↑ 依据：标记表 legend 原文「level_hint：null 表示只作条件判断，不指向水平」")
    print()
    print("★ A2 自我当前**能行使**的对抗规则：%s（共 3 条）" % "、".join(r["self_rules"]))
    for rule, need in sorted(r["eng"]["rule_unlock"].items()):
        mark = "✓" if rule in r["self_rules"] else "✗"
        print("   %s %s  需 %s" % (mark, rule, need))
    print("   ↑ 顺序有据（[E] 冲动控制来源的转移：本能的腻 → 学到的规律 → 结构性克制）")
    print("     卡在哪一级是 ENG 占位值，**该由数据定，不是请你选**。")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

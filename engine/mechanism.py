# -*- coding: utf-8 -*-
"""机制层（底层思维系统）

这一层的职责，用一句话说：
    **把三本书讲的"大脑底层怎么运转"，写成一个会自己演化的方程组；
      交互层的输出由这个方程组的当前状态决定，而不是由"用户这句话里抓到了几个特征"决定。**

为什么需要它（这是本模块存在的全部理由）
  实测事实（见 README「三·补五」）：
    · 真人输入约 2/3 轮次**命中 0 个标记**（tests/probe_topic_answers.py）
    · 而旧架构是"命中标记 → 改状态"，没命中就什么都不发生 → 只能复述或沉默
  于是系统退化成了一个复述机。根因不是词表不够长，而是**入口放错了位置**：
    旧：用户说了什么  → 触发什么行为
    新：底层机制在算什么 → 交互自然长得像对话
  机制层没有新输入时也会演化（衰减、累积、耦合），所以它**永远有状态可说**。

三条纪律（违反即失败）
  1. **本层只做数学运算与结构映射，不生成任何文字。**
     它输出的是数、条件 ID、动作 ID。文字只能来自 rules/behaviors.json 的模板。
  2. **每个常数必须标注来源。** `有据` = 原书给了数值或区间；`待标定` = 我挑的工程占位。
     不许把"我挑的"伪装成"书里说的"。这是本项目最重要的一条诚实要求。
  3. **不制造痛苦（E2）。** 张力趋零时允许上调目标，但**不得**为了推进发展而
     人为制造困难。上调目标的依据是 `[M]` 的"精神动力"，不是"让人吃点苦有好处"。

------------------------------------------------------------------ 三层与位阶

`[规格 §1 冲突 6]` 的裁决是 **动力（多巴胺）→ 结构（控制）→ 方向（意义）**，
下位服从上位。放进方程组后它成为一条**运算纪律**：

    第 1 层  动力层   算 w, l, Δr, a     → 产出"驱力"
    第 2 层  结构层   算 e，用 e 门控驱力 → 产出"可用的力"      ← 不许绕过
    第 3 层  意义层   算 tension，定向     → 产出"往哪去"

**禁止第 1 层直接驱动输出（绕过第 2 层）。**
而"绕过第 2 层"恰恰就是过度意向（over_intention）—— 它不需要靠词表去抓，
它就是本系统自己的一个数值状态。这是本模块相对旧架构最实质的改变。

------------------------------------------------------------------ 变量与量纲

全部量纲取自原书，不是我编的归一化数：

| 变量 | 含义 | 量纲 | 来自原书的上下界 |
|---|---|---|---|
| `w` | 想要回路活跃度 | Hz（放电率） | 静止 3–5；兴奋 20–30；预期落空 → 0 |
| `l` | 当下分子/体验水平 | 无量纲 [0,1] | 长期可卡因使用者释放量比健康人低 **80%** |
| `Δr` | 奖赏预测误差 | Hz | **＝实际奖赏 − 预期奖赏** |
| `a` | 敏化增益 | 无量纲 ≥ 0 | 耐受/敏化（重复同图 → 反应降；换新图 → 复燃） |
| `e` | 结构预测误差 | 无量纲 | 平衡化压力（全证实 / 全违反 都推动重组） |
| `tension` | 意义张力 | [0,10] | **"紧张的极化区"**，两端都不健康 |
"""
from __future__ import annotations

# ★ 阈值与常数一律从 SSOT 取（用户裁定：三处副本合一，方案乙）
import constants as C          # noqa: E402

import os
import sys
from dataclasses import dataclass, field, asdict

_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包成 exe 后 `__file__` 指向解包出的临时目录 —— 于是 rules/corpus 找不到，
# 而且**台账会写进临时目录、退出就丢**。所以允许用 EGO_ROOT 指定项目根，
# 由启动器（exe）在导入任何引擎模块之前设置。
# 不设 EGO_ROOT 时行为与从前完全一致（源码运行时就是这个分支）。
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)

# ------------------------------------------------------------------ 常数

# 全部来自 [D]《贪婪的多巴胺》的实测数字（原书第 194–196 行附近）：
#   "多巴胺放电率：静止状态每秒 3 到 5 次激发；兴奋时激增到每秒 20 到 30 次；
#    预期奖赏没有实现时下降到零"
DA_REST_LO = 3.0        # 有据：静止下界
DA_REST_HI = 5.0        # 有据：静止上界
DA_BURST_LO = 20.0      # 有据：兴奋下界
DA_BURST_HI = 30.0      # 有据：兴奋上界
DA_ZERO = 0.0           # 有据：预期落空 → 零

# 神经调质半衰期决定时间折扣。dopamine ~200ms、serotonin ~数百ms、oxytocin ~分钟级。
# 对话的时间尺度是"轮"而不是"毫秒"，所以必须换算；换算率是 ENG。
# ⚠️ 这一处是本模块最大的一个未标定量：正确做法是用真实轮次间隔（分钟级）
#    乘上身半衰期去算，而我们现在没有真实使用的时序数据。
DOPAMINE_TAU = 0.25     # 以"轮"为单位的衰减时间常数（ENG，待标定）
PRESENT_TAU = 0.70      # 同上，当下分子（ENG，待标定）
# 取 0.70 而不是 0.35：0.35 时 l 在两三轮内就掉到地板，
# 于是 DEPLETED 变成一个常亮状态、盖住了其他所有机制条件（实测发现）。
# 当下一轮的时长以"谈话"计，体验的积累与流失都该是慢变量。


@dataclass
class MechanismConfig:
    """机制层参数。

    `dopamine_gain` 与各层增益在无外部参照时**不需要标定**：
      Δr = 实际 − 自身预期，两边同量纲，增益会自动抵消（见 Dynamics._predict）。
    这正是"用自身当参照"的好处 —— 它消掉了一个否则只能靠猜的常数。
    """

    # ---- 第 1 层 动力
    da_rest: float = (DA_REST_LO + DA_REST_HI) / 2.0   # 有据（取静止带中点）：4.0 Hz
    da_ceiling: float = DA_BURST_HI                    # 有据：30 Hz
    habituation_k: float = 0.10    # 新颖度衰减/轮。有据的**定性**事实："几周后变平淡"；
                                   # 换算成"轮"的速率是 ENG（0.10 → 约 8 轮降到一半）。
    # 新颖度地板：只作为数值下限，避免长期麻木后爆发分量永远残留。
    # 取 0.02 时，完全麻木的 w ≈ 4.0 + 15×0.02 = 4.3Hz，落在原书的静止带 3–5 内。
    # 第一版取 0.12，结果麻木后 w 停在 5.8Hz，**回不到静止带** —— 被测试 A2 抓到。
    habituation_floor: float = 0.02
    # l 的两个时间常数（以"轮"计，ENG，待标定）。
    # 关键关系是**回升快、流失慢** —— 对应 [D] 的"几周后，这座城市最好的咖啡
    # 和牛角面包变成了平淡的早餐"：一次具体的体验马上能补回来，麻木却要走很久。
    # τ=14 → 每轮保留 0.929，约 28 轮连续无具体体验才降到 0.12（DEPLETED 阈值）。
    # ⚠️ 原值 8.0 太快：实测 12 轮的对照语料里没有任何具体体验，
    #    l 一路掉到 0.26，于是张力顶到上界 10.0、7 轮全判 OVERLOADED。
    #    真实的反思型对话里，具体的此时此地细节本来就不常出现；
    #    "麻木"必须比"这十几轮没聊到具体事"更慢才算合理。
    experience_rise_tau: float = 2.0   # 有体验时回升的时间常数（ENG）
    experience_decay_tau: float = 14.0 # 无体验时流失的时间常数（ENG）
    experience_floor: float = 0.05     # l 的地板。有据的类比：长期使用者释放量比健康人少 80%（ENG 换算）
    sensitization_gain: float = 0.18   # 失望 → 想要的增益上升（ENG，待标定）。
                                       # 0.18 配 /10 的量纲换算：一次 −6Hz 的失望 ≈ a += 0.108

    # ---- 第 2 层 结构
    error_memory: float = C.ERROR_MEMORY     # 预测误差的记忆系数 γ（ENG，待标定）
    error_high: float = C.ERROR_HIGH       # |e| 超过 → 平衡化压力"上涨"（ENG，待标定）
    error_low: float = C.ERROR_LOW        # |e| 低于 → 结构停滞（ENG，待标定）

    # ---- 第 3 层 意义
    # 张力的两个减项系数：完成感与应对能力各能抵掉多少张力（ENG，待标定）
    completion_relief: float = 1.0
    capacity_relief: float = 1.0
    # 行为性投入的两个长度门槛（ENG，待标定）。
    # min_answer_len：短于此长度不算一次实质应声（"嗯""哦"不构成投入）
    # substantive_len：超过它才算一次实质接话
    min_answer_len: int = 3
    substantive_len: int = 10
    # 这句话长到足以追问的最低字数（ENG）。只看长度，不做语义理解。
    askable_len: int = 6
    # 张力标度：把"Hz × 缺口感"换算到 0–10 的张力量表（ENG，量纲换算不是主观权重）
    tension_scale: float = 1.1
    tension_up: float = 7.0        # 有据的类比：弗蘭克尔"张力爆表 → 降负载"
    tension_low: float = C.TENSION_LOW       # 有据（定性）：张力趋零是病态，不是健康
    tension_health_lo: float = C.TENSION_HEALTH_LO # 健康极化区下沿（ENG）
    # 健康极化区上沿。**不是独立常数** —— 它由 __post_init__ 强制等于 tension_up。
    # ⚠️ 它原本写死成 6.5，于是张力落在 (6.5, 7.0) 的轮次没人管，
    #    实测掉进 UNCLASSIFIED 死角（测试 F10 抓到）。
    #    改成强制派生后，这类"区间不闭合"的缝在结构上就不可能出现。
    tension_health_hi: float = field(init=False, default=7.0)

    def __post_init__(self) -> None:
        # 不变量：健康带上沿必须与爆表阈值重合，否则两者之间是一条缝。
        # 用强制赋值而不是断言，是为了让"想让它们不等"这件事根本做不到。
        self.tension_health_hi = self.tension_up
    tension_health_hi: float = C.TENSION_HEALTH_HI # 健康极化区上沿（ENG）

    # ---- 水平之间的代价（用于算 unfinished gap）


# ------------------------------------------------------------------ 结果

@dataclass
class MechanismState:
    """一"轮"结束时机制层的状态。全部是数，没有任何文字。"""

    turn: int
    # 第 1 层 动力
    w: float                 # 想要（Hz）
    l: float                 # 喜欢（[0,1]）
    novelty: float           # 该情境的剩余新颖度（[floor,1]）
    lean: float              # 行为性投入（相对自身基线）—— 想要的来源，不看措辞
    lean_raw: int            # 本轮原始投入级数 0–3（可观察行为，用于追溯）
    askable: bool            # 这句话长到足以追问吗（可观察：字数）
    has_attitude: bool       # 命中 attitude_clause（第三途径）—— 供 ACKNOWLEDGE 使用
    is_closing: bool         # 这是不是一句收尾语（就这样吧／算了…）—— 供 ACKNOWLEDGE_CLOSE 使用
    delta_r: float           # 奖赏预测误差（Hz）
    a: float                 # 敏化增益
    # 第 2 层 结构
    e: float                 # engineering channel-transition pressure; not measured semantic error
    e_trend: str             # RISING / FLAT / FALLING
    # 第 3 层 意义
    tension: float
    tension_measured: bool
    completed: float
    unfinished: float
    capacity: float
    # ★ 2026-10-28：上一轮的输出有没有被闸门退回（她**自己的**可观察量）。
    #   与 tutor 的评价无关 —— 那是别人的评判；这个是事实：话没出去。
    #
    #   ⚠️ 必须放在**有默认值的字段区**（dataclass 不允许"无默认值"跟在"有默认值"后面）。
    #      第一版插在 `turn` 后面，直接 TypeError。
    rejected: bool = False
    reject_streak: int = 0
    # ★ A3 意义层：**指向**（朝外／朝内）。
    #
    #   [M]「人之所以为人，是因为他总是指向**自身以外**的某种事物或某人」
    #   [M]「自我实现可能是**自我超越唯一的副产品**」
    #
    #   意义层缺的从来不是"缺口有多大"（那是 unfinished 在量的），
    #   而是"**缺口朝哪**"。指向就是那个方向。
    #
    #   三条途径的**真实**状态（T17 逐条查证后改写；旧版此处不实，已纠）：
    #     · 体验 —— **系统遇到另一个人**。供给方是用户与管理员（家教）。
    #               [M] 的"某人"不是要去对方话里检测的词，是**真的有人在场**。
    #               落点见 MechanismState.path_experiential（由 orientation 推出）。
    #     · 态度 —— 面对不可改变之事取姿态。
    #               由 attitude_clause 推出，**且只在 immutable 成立时才算**
    #               （那层门控在标记层，见 markers.json 的 attitude_clause._note）。
    #               落点见 MechanismState.path_attitudinal。
    #     · 创造 —— ⚠️ **无可观察量，诚实缺位，恒为 0**。
    #               旧版这里写的是「系统产出回应（每轮都在发生）」——
    #               那是**把缺口说成了实现**：恒真的量不携带信息，等于没做。
    #               本系统是纯对话形态，无实体干预现实；[M] 的创造途径要求
    #               主体在**现实世界**里改变客观境遇（M-578）。如实标缺。
    #               详见 MechanismState.path_creative 的说明与用户裁定原文。
    #
    #   `orientation` 由**上一轮系统把注意力放在谁身上**推出：
    #     "外" = 落在对方身上     "内" = 落在自己的状态上
    #     （REPORT_OWN_STATE 这个行为的标签原文就是"以自我为中心"）
    #
    #   ⚠️ 为什么用上一轮：本轮行为要到决策层才定，而意义层在它之前算。
    #      用上一轮是**真实的反馈回路**，不是将就。
    #   ⚠️ **必须是数，不能是字符串。** 机制层的纪律是"只有数，没有文字"，
    #      而测试 G1 真的把这条抓住了 —— 我第一版写成 `orientation: str = "无"`，
    #      G1 立刻判失败。改成数值也更好用：可以求和、可以平均、可以直接进方程。
    #        +1.0 = 朝外（注意力落在对方身上）   -1.0 = 朝内   0.0 = 判不出
    orientation: float = 0.0
    orientation_out: int = 0         # 累计朝外 —— "遇到人"的次数
    orientation_in: int = 0          # 累计朝内
    # ── A3（T17）：三条意义途径的落点（[M]「找到生命之意义有三个主要途径」M-570）
    #
    #   全部是**数**（0.0 / 1.0），遵守机制层"只有数、没有文字"的纪律。
    #   三条途径**不互斥** —— Frankl 没说是互斥的，同一轮可以同时走上两条。
    #
    #   · 体验（path_exp）：系统**遇到了另一个人**。
    #       [M]「人之所以为人，是因为他总是指向自身以外的某种事物或某人」
    #       由 orientation 推出 —— 注意力落在对方身上即成立。
    #
    #   · 态度（path_att）：面对**不可改变**之事取姿态。
    #       [M] 第三途径「在忍受不可避免的苦难时采取某种态度」
    #       由 `attitude_clause` 标记推出，且**只在 immutable 成立时才算**
    #       （markers.json 里 attitude_clause 的 `_note` 原文：
    #        「仅在 mutability=IMMUTABLE 时计入方向；对可改变处境使用态度句
    #          不构成高段证据」）。
    #
    #   · 创造（path_creative）：**暂无可观察量，诚实缺位，恒为 0.0。**
    #
    #       ⚠️ 这条是**刻意空着**的，不是漏了。
    #       [M] 的创造途径指主体在**现实世界**里完成具体作为、改变客观境遇
    #       （M-578「首要的是创造性地去改变让我们遭受磨难的境遇」）。
    #       本系统是**纯对话形态**：既无实体干预物理世界的能力，
    #       也无权在对话里替用户创造。它只能通过"体验"（遇到这个人）与
    #       "态度"（陪他面对不可改变的事）参与 —— 这与意义疗法的定位一致：
    #       **它不替人活，只帮人看见。**
    #
    #       曾经这里只写了一句「创造 —— 系统产出回应（每轮都在发生）」，
    #       那是**把缺口说成了实现**：恒真的量不携带任何信息，等于没做。
    #       用户裁定（原话）：「（甲）方案本质上依然是给『凡是开口说话就算创造』
    #       穿上了一层算法马甲，会让绝大多数轮次沦为假阳性，彻底稀释了这一指标的
    #       严肃性」。所以这里**如实标缺**，并保留计数器 `path_cre`（恒为 0），
    #       让"它一直是 0"这件事本身可见。
    path_creative: float = 0.0       # 创造途径：**恒 0.0，无可观察量（见上）**
    path_experiential: float = 0.0   # 体验途径：遇到另一个人
    path_attitudinal: float = 0.0    # 态度途径：对不可改变之事取姿态
    path_cre: int = 0                # 创造途径累计 —— **永远为 0，这是诚实留痕**
    path_exp: int = 0                # 体验途径累计
    path_att: int = 0                # 态度途径累计
    # 派生
    phase: str = ""          # 机制条件 ID（见 CONDITIONS）
    last_phase: str | None = None   # 上一轮的机制条件 ID（供不连问这类回合间规则使用）
    forbidden_layer1: bool = False   # 是否禁止第 1 层直接驱动（= 过度意向）
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ 情境轨迹（新颖度）

    #: ★ **公式版本**（用户裁定 2026-10-02：架构层数据分界）。
    #:  1 = 旧公式 `e = γ·e + (1-γ)·(change+rigidity)/2`，值域 [0, 0.5]
    #:  2 = 方案 B noisy-OR，值域 [0, 1]
    #:  **两者不可直接比较。** 分析历史台账前必须先看这个字段。
    #:  ⚠️ 放在**字段列表末尾** —— dataclass 不许「带默认值的字段排在不带默认的之前」。
    e_version: int = 0
class HabituationTrack:
    """记录每个情境被重复了多少次 → 剩余新颖度。

    依据 [D]（面包店案例，全书最著名的比喻）：
      "这是你喝过的最好喝的咖啡" → 几周后变成平淡的早餐
      **"咖啡和牛角面包都没有变，变的是你的预期。"**
    依据 [D]（耐受）：
      重复看同一张图片 → 多巴胺回路活性降低、兴趣减弱；看到**新**图片 → 系统再次活跃。

    注意这里的关键设计：**新颖度不看用户说了什么词，只看情境被见过几次。**
    这就是"用自身当参照"——它不需要任何词表，也不需要标定外部的"新鲜"标准。
    """

    def __init__(self, k: float, floor: float):
        self.k = k
        self.floor = floor
        self.count: dict[str, int] = {}

    def novelty(self, key: str) -> float:
        """剩余新颖度 ∈ [floor, 1]。"""
        n = self.count.get(key, 0)
        return max(self.floor, (1.0 - self.k) ** n)

    def see(self, key: str) -> float:
        """登记一次曝光，返回**曝光后**的剩余新颖度。"""
        self.count[key] = self.count.get(key, 0) + 1
        return self.novelty(key)

    def snapshot(self) -> dict:
        return {"distinct_keys": len(self.count),
                "max_repeat": max(self.count.values()) if self.count else 0}


# ------------------------------------------------------------------ 机制层

class Mechanism:
    """三层方程组。**只做运算，不生成文字。**

    每一轮调用 `step()`，它按 动力 → 结构 → 意义 的位阶顺序计算，
    并用第 2 层门控第 1 层（不许绕过）。
    """

    def __init__(self, config: MechanismConfig | None = None,
                 initial_tension: float = 0.0):
        """★ `initial_tension`（用户裁定 2026-10-02，D-011）：
        上一场未解张力**衰减后**的注入值。默认 0.0 = 与从前完全一致。
        显式传参而不是让 Mechanism 自己去读文件 —— 读盘是 Pipeline 的职责，
        机制层只管动力学（它现在连 os 都不需要）。
        """
        self.cfg = config or MechanismConfig()
        self.track = HabituationTrack(self.cfg.habituation_k, self.cfg.habituation_floor)
        self._turn = 0
        # 状态初值
        self.w = self.cfg.da_rest          # 有据：静止状态
        # l 的起点不是 0.5 也不是任何我挑的数，而是**自身参照系的中性值 1.0**
        #   l 的定义是"体验充足度"（见 _layer1），比值 1.0 恰好表示"与期望持平"。
        #   第一版取 0.5，结果前几轮一律被判 DEPLETED —— 起点自己造成了偏差。
        self.l = 1.0
        self._l_raw = 1.0
        self.a = 0.0                       # 未敏化
        self.e = 0.0                       # 无历史 → 无结构压迫
        self._e_prev = 0.0
        self._channel_prev: str | None = None
        self._stable_streak = 0            # 通道连续未变的轮数
        # ★ 2026-10-28：输出被闸门退回（她自己的失败）。机制层的状态原来
        #   只在**被放行的那句话**上计算，于是"这句话没出去"完全读不到。
        self._rejected_pending = False     # 上一轮渲染阶段登记进来的
        self._reject_streak = 0            # 连续被退回的轮数
        # 可体验事件的自身统计（l 的参照系，见 _layer1 错误 3）
        self._seen_experience = 0
        self._miss = 0
        self._l_raw = 1.0
        self._base_rate = 1.0              # 自身长期体验频率（拉普拉斯平滑，起点为无信息先验）
        # 行为性投入（"想要"的来源，见 _observe）
        self._lean = 0.0
        self._lean_base = 1.0              # 自身投入基线（自参照的分母）
        self._expect = 0.0                 # 对奖赏的自身预期（EMA），见 _layer1
        self._novelty_bursts = 0
        self._obs_history: dict[str, list[int]] = {}
        # 第 3 层
        self._completed = 0.0
        self._capacity = 0.0
        # ★ 跨场累积注入点（D-011）：默认 0.0，与从前完全一致
        self._tension = max(0.0, min(C.TENSION_SCALE_MAX, float(initial_tension)))
        self._unfinished_last = 0.0
        # A3 意义层：指向。由上层每轮告知**本轮**的实际落点，下一轮生效。
        #   数值：+1 朝外 / -1 朝内 / 0 判不出（机制层不许有文字）
        self._orientation = 0.0
        self._orient_out = 0
        self._orient_in = 0
        # ── A3（T17）：三条途径的落点与累计。全部是**数**，机制层不许有文字。
        #   体验 = 走上一条（遇到另一个人）；态度 = 走上另一条（对不可改变之事取姿态）；
        #   创造 = **无可观察量，恒为 0**（理由见 State 里 path_creative 的说明）。
        self._path_att = 0.0        # 本轮态度途径是否成立（0.0 / 1.0）
        self._cnt_cre = 0           # 创造途径累计 —— **永远为 0，诚实缺位**
        self._cnt_exp = 0           # 体验途径累计
        self._cnt_att = 0           # 态度途径累计
        self._skill = 0.0                  # 被"答到题上"训练出来的能力（0 起，靠 engaged 上升）
        # 张力**始终可测**：它由第 1 层已算出的 w 与 l 推出（想要 vs 能够得到），
        # 不依赖任何外部水平锚点。
        # 曾经的"待测／未测"状态已随第一版设计一起废弃 —— 那一版需要
        # corpus/topics.json 提供"题面水平"，而核对原书后确认那是帕克与哈维斯特的做法，
        # 卢文格 [p246] 明确反驳它。详见 _layer3 的注释。
        self._tension_measured = True
        self._last_phase: str | None = None   # 上一轮的机制条件（回合间规则用）
        self._history: list[float] = []
        self._last_inputs: dict = {}
        self._last_key: str = ""

    # -------------------------------------------------------------- 输入映射

    # 观测动作 → 对底层变量的注入。**全部是可观察的字面事实，不是解释。**
    # 只映射到第 1 层（驱力），第 2 层与第 3 层由系统自身状态算出，不由输入直接给。
    _WANT_BOOST = 20.0     # want_like_gap 命中时，渴望在**全新情境**下能加多少 Hz。
                           # 定 20 是为了让"渴望 + 全新"落在原书的兴奋带 20–30 内
                           # （静止基线 4 ＋ 20×novelty ≈ 22–24 Hz）。这是量纲换算，不是主观标度。
    # 行为性"想要"每级折合多少 Hz。三级行为强度 → 最多 +18Hz，
    # 使得"投入很强 + 情境全新"能自然落进兴奋带，而不必依赖任何措辞。
    _LEAN_TO_HZ = 6.0
    _EXPERIENCE_INJ = 1.0  # present_missing 的反面：有体验词 → 注入当下（倍数）

    # 收尾语名单（穷举，字面）。只认这几种结束交谈的形式，不做语义理解。
    # 依据：用户第三次判定指出第 12 轮「就这样吧。」是死的 —— 而它是收尾语，
    # 不是对题目的回答，所以既不该被追问"发生什么了"，也不该算作投入。
    _CLOSING_LEXICON = (
        "就这样吧", "算了", "不说了", "没什么好说的", "没什么", "没事",
        "不知道", "嗯", "哦", "好吧", "随便", "都行", "无所谓",
    )

    def _observe(self, markers: list[str], raw: str, stem_level: float | None,
                 engaged: bool = False) -> dict:
        """把可观察事实整理成这一轮的注入量。只有字面事实，没有推断。"""
        ms = set(markers)
        t = (raw or "").strip()
        # ---- 行为性投入（0–3）。**三项都是可观察行为，不看措辞。**
        # 这一组存在的理由（承「三·补五」的老毛病，是用户反馈逼出来的）：
        #   机制层第一版把"想要"挂在 want_like_gap 这个**词表标记**上。
        #   实测 12 轮里只有 1 轮 w 上升（"我一定要得到那个结果"），其余 11 轮 w 贴着
        #   静止基线 4.0Hz 不动 → 未完成恒为 0 → 张力恒为 0 → 整场只识别出一种状态，
        #   8 个零命中轮次全回同一句话。用户的原话："其他的全是牛头不对马嘴。"
        #   根因：机制层的卖点就是"不靠词表"，而"想要"偏偏还用词表推 —— 自相矛盾。
        # 修法：改用行为。**"想要"在行为上无法伪装的那个证据是"你还在说"。**
        #   一个人不想继续，他的行为是**停止**，不是换个说法。
        # ⚠️ 第一项原本是 1 if t else 0（只要开口就算一级），
        #   实测后果："嗯"（1 字）与一句 17 字的实质回答**算同一级投入**，
        #   于是 lean 在整场里恒定，行为性想要完全失去分辨力（被测试 F1 抓到）。
        #   修法：开口要够长才算一级。"嗯""哦"这类应声不算投入。
        lean = (1 if len(t) >= self.cfg.min_answer_len else 0) \
            + (1 if len(t) >= self.cfg.substantive_len else 0) \
            + (1 if engaged else 0)
        # ---- 收尾语 vs 有内容的叙述（用户第三次判定逼出来的）
        # 用户实测给了他活人感的四轮是 3、4、6、9，其中 **4 和 6 都没有锚点**，
        # 却和 3、9 打平 —— 说明"发生什么了？"这句本身够轻，不依赖锚点（锚点是加分项）。
        # 而第 12 轮「就这样吧。」系统只回复述，那轮是死的。
        # 差别在于：「反正也就那样」「有时候觉得挺累的」是**对题目的回答**（有内容，哪怕空泛）；
        # 「就这样吧」「算了」是**收尾语**，它不是叙述，是结束交谈。
        # 对收尾语追问会显得没听懂；对叙述只复述则是浪费。
        # 名单是穷举的字面词 —— 只认这几种结束形式，不做语义理解（[E] 最低限度推理）。
        closing = any(t == w or t.startswith(w) for w in self._CLOSING_LEXICON)
        if closing:
            # 收尾语不算投入：它表示"不想说了"，不是"在说"。
            # 不扣的话，系统会把"算了""就这样吧"当成积极参与，继续往下推。
            lean = max(0, lean - 2)
        return {
            # 措辞性渴望（词表）。现在只是行为性投入之外的一个**加项**，不再是唯一来源。
            "want": "want_like_gap" in ms,          # [D] 想要／喜欢分离
            "lean_raw": lean,
            "closing": closing,
            # 可观察：这句话有没有东西可问。**看长度，并排除收尾语**，不做语义理解。
            "askable": len(t) >= self.cfg.askable_len and not closing,
            # 这一轮**没有得到**想要的（没有态度句、也没有被满足的迹象）
            # 失望只在"刚渴望过、但这次索然"时才算 —— 由 _layer1 用 self._expect 判定
            "unsatisfied": "want_like_gap" not in ms,
            # 有可体验事件＝这句话里出现了具体物（味/触/身体/具体的人/此刻），
            # 且没有被判为"当下缺失"。两个条件都只看字面。
            "has_experience": ("present_missing" not in ms) and self._experience_hint(raw),
            "immutable": "immutable" in ms,          # [M] E1 闸门
            "attitude": "attitude_clause" in ms,     # [M] 第三途径
            "over": "over_intention" in ms,          # [M] 过度意向
            # 是否真的答到了题上（由 L0 意图与题面匹配判定后传入）→ 训练能力
            "engaged": bool(engaged),
            "stem_level": stem_level,
        }

    @staticmethod
    def _experience_hint(raw: str) -> bool:
        """字面检查：这句话里有没有可体验的具体物（味/触/身体/具体的人/此刻）。

        这不是语义理解 —— 只是词表命中，与 markers.json 的体验词汇域同源。
        用途仅一个：决定要不要给 `l` 注入。不生成任何标记。
        """
        lex = ("味道", "香", "甜", "苦", "摸", "触", "凉", "暖", "烫", "疼",
               "身体", "睡", "呼吸", "心跳", "饿", "脸", "声音", "看着",
               "一起吃饭", "抱着", "坐在", "那天", "当时", "此刻", "眼前")
        return any(x in (raw or "") for x in lex)

    # -------------------------------------------------------------- 第 1 层 动力

    def _layer1(self, key: str, obs: dict) -> dict:
        """动力层：算 w, l, Δr, a。

        这几个式子是**改过一版的**，改的理由写在下面各段 —— 第一版有三个错误，
        都是被 `python engine/mechanism.py` 的自检打印出来的，不是我想出来的：
          错误 1：把新颖度乘在 w 的整体上 → 重复同一句话时 w 单调下降。
                  [D] 的意思是"刺激的反应下降"，不是"驱力下降"。修法：新颖度只作用于**爆发分量**。
          错误 2：Δr 用"w 与自身预期之差" → 说了让人兴奋的话反而 Δr 变小、招来敏化，方向反了。
                  修法：Δr 是**奖赏预测误差**，用 |w − 静止基线| 当"实际奖赏"的量。
          错误 3：l 用 |0,1| 绝对刻度、起点 0.5 又没事件可注入 → 永远是 0.05 地板、"枯竭"常亮。
                  修法：改成**相对于自身历史**的比值（同 Δr 的自参照思路），少一个瞎猜的常数。
        """
        self._last_key = key

        # ---- 曝光 → 新颖度下降（不看用户说什么也会变）
        obs_list = self._obs_history.setdefault(key, [])
        n_seen = len(obs_list)
        self.track.count[key] = n_seen + 1
        nov = self.track.novelty(key)

        if not obs["has_experience"]:
            self._miss += 1
        if obs["has_experience"]:
            self._seen_experience += 1
        obs_list.append(1 if obs["has_experience"] else 0)
        became_novel = obs["has_experience"] and not any(obs_list[:-1])
        if became_novel:
            self._novelty_bursts += 1

        # ---- 想要 w（Hz）
        #   w = 静止基线（受敏化抬高） ＋ 相位性爆发（**渴望在新颖情境下的那一下**）
        # [D] "静止状态每秒 3 到 5 次激发；兴奋时激增到每秒 20 到 30 次"
        # [D] 兴奋来自"对意外的反应，即对可能性和预期的反应" → 爆发由**新颖 × 渴望**共同决定：
        #     新颖但不渴望 → 只是注意到，不兴奋（停在静止带）
        #     渴望且新颖   → 兴奋带 20–30
        #     渴望但不新颖 → 回落到静止带（这就是面包店案例：咖啡没变，预期变了）
        #
        # ⚠️ "渴望"的来源改过一次，这是本次最重要的修正：
        #   第一版：`if obs["want"]`（＝ want_like_gap 这个**词表标记**）
        #     → 实测 12 轮里只有 1 轮 w 上升，其余 11 轮贴着静止基线不动，
        #       整场只识别出一种状态。用户的评语："其他的全是牛头不对马嘴。"
        #   现在：**行为性投入 lean**（是否还在说 / 说得够不够多 / 是否真在答），
        #     lean 本身是**相对于自身基线**的比值，所以它也是自参照的。
        #   加了词表项作为额外加项，但它不再是必要条件。
        # [D] 依据：想要是行为，不是说法。一个人不想继续，行为是**停止**，不是换个措辞。
        w = self.cfg.da_rest * (1.0 + self.a)      # 静止基线（受敏化抬高）
        self._lean_base = 0.92 * self._lean_base + 0.08 * obs["lean_raw"]
        lean = min(1.0, obs["lean_raw"] / max(0.5, self._lean_base)) if self._lean_base else 0.0
        self._lean = lean
        want_hz = self._LEAN_TO_HZ * lean
        if obs.get("want"):
            want_hz += self._WANT_BOOST            # 措辞性渴望：加项，不是唯一来源
        if want_hz > 0:
            w += want_hz * nov
        w = max(DA_ZERO, min(self.cfg.da_ceiling, w))

        # ---- 奖赏预测误差 Δr ＝ 实际奖赏 − 预期奖赏
        # [D] 章末总结原句："多巴胺的反应不是针对奖赏，而是针对
        #     **奖赏预测误差＝实际奖赏减预期奖赏**"
        #
        # 这一段改过三版，把两版错误记下来，因为它们很容易再犯：
        #   错版 1：actual 用 |w − 静止基线| → 说了让人兴奋的话 Δr 反而变小，方向反了。
        #   错版 2：expected 用"对奖赏的 EMA 平滑"（含相位性分量）→
        #           任何衰减信号都会因平滑器的**滞后**产生恒负的 Δr，
        #           于是 a 被数值伪影一路推高（实测 40 轮涨到 0.29，而实际并无失望）。
        #
        # 现在的定义：
        #   Historical interpretation said reward fulfilment. The implementation
        #   below only observes a lexical want feature, not a fulfilled outcome.
        #   r is an engineering proxy; do not use it as a measured reward signal.
        #       相位性爆发不进 r —— 因为按 [D]，爆发本身就是奖赏预测误差的表现，
        #       把它放进 actual 等于把 Δr 算两遍。
        #   expected（预期）＝ 系统对"这件事能否给出奖赏"的估计，从 0 起。
        #       [D] 对陌生的事不抱预期；越熟悉、预期越准。
        # 于是三种情形都对上了：
        #   陌生且无渴望 → 0 − 0 = 0（无所谓）
        #   第一次渴望   → 6 − 0 > 0（惊喜）
        #   反复渴望     → 6 − 6 = 0（不再惊喜，但也没失望）
        #   在会失望的地方渴望（"想要"指向的对象一直没兑现）→ 转负 → 敏化
        r = self._WANT_BOOST if obs.get("want") else 0.0
        delta_r = r - self._expect
        # 预期按真值更新；用精确赋值而不是平滑，避免再引入一个滞后型伪影
        self._expect = r
        # ---- 敏化 a：反复的失望抬高想要回路的增益
        # [D] 耐受与敏化：长期可卡因使用者多巴胺释放比健康人少 80%；
        #     诺亚"随着耐受度提高，平淡素材无法满足，追求更刺激享受"
        if delta_r < 0:
            self.a += self.cfg.sensitization_gain * (-delta_r) / 10.0
        else:
            self.a *= 0.98                              # 正误差缓慢消退（ENG）
        self.a = max(0.0, min(4.0, self.a))

        # ---- 当下 l：**被"此时此地的真实体验"喂养，靠缺失缓慢流失**
        # [D] 当下分子负责此时此地的真实体验；[D] 长期缺失 → 麻木
        # [D] 麻木不是一轮就发生的："几周后，这座城市最好的咖啡和牛角面包变成了平淡的早餐"
        #
        # ⚠️ 这一段改过**四版**，前三版都错，全过程记下来，因为它是本模块最容易写错的地方：
        #   错版 1：l 用"累计体验比例"走一阶 EMA → 第一轮没体验就从 1.0 掉到 0.3，
        #           两三镇压到地板，DEPLETED 常亮，盖住其他所有机制条件。
        #   错版 2：l 用"最近窗口频率 ÷ 固定期望值 0.25" →
        #           正常对话里大多数轮次本来就不含具体体验（A/B 实测 12 轮里 0 轮），
        #           于是 l 永久压在地板上，系统认为所有人都在枯竭。
        #           这是把"跟一个我拍的常数比"当成了"跟自身比"。
        #   错版 3：比值 + 快平滑两个机制叠在一起 → 互相打架，l 仍然单轮压到地板
        #           （被测试 D4 抓到）。错因：**一层里放了两个动力学**。
        #
        #   现在：**只有一个机制。** 有具体体验就**回升**，没有就**缓慢流失**。
        #         回升快、流失慢 —— 这是 [D] 的"几周后变平淡"在时间常数上的落点。
        #         l 从 1.0 起（＝"还没观察到枯竭"），不需要任何外部标准。
        if obs.get("has_experience"):
            self.l += (1.0 - self.l) / self.cfg.experience_rise_tau
        else:
            self.l -= self.l / self.cfg.experience_decay_tau
        self._l_raw = self.l
        self.l = max(self.cfg.experience_floor, min(1.0, self.l))

        self.w = w
        return {"w": w, "l": self.l, "novelty": nov, "delta_r": delta_r, "a": self.a}

    # -------------------------------------------------------------- 第 2 层 结构

    def _layer2(self, channel: str) -> dict:
        """结构层：算通道稳定性 e，并以此**门控**第 1 层。

        [E] 平衡化：不是进步，是**失衡驱动的重组**。
            全被证实与全被违反都推动，方向不同；两者都是"结构受压迫"。
        [规格 §1.1 维度 B]："现有结构与环境预期匹配 → 发展停止"

        系统的预期是什么？这里取一个**纯自指**的预期：下一轮仍是同一通道。
        它不需要任何外部标准，且能被台账直接验证。
        e 的含义：**结构被压迫的程度** —— 通道越是长期不变（或越是频繁翻转），
        平衡化压力越大。这样 e 不需要跟任何外部标准比较，也就不用标定常数。
        """
        if self._channel_prev is None:
            change = 0.0
        else:
            change = 0.0 if channel == self._channel_prev else 1.0
        # 通道翻转是"结构被违反"的直接观测；长期不翻转则结构僵化
        self._stable_streak = self._stable_streak + 1 if change == 0.0 else 0
        rigidity = min(1.0, self._stable_streak / C.STREAK_FULL)     # 12 轮不动 = 完全僵化（ENG）
        # ★ 方案 B（D-012）：noisy-OR 取代 (change+rigidity)/2
        #
        #   旧式：e = 0.75*e + 0.25*(change + rigidity)/2        → 值域 [0, 0.5]
        #        根因不是"两个信号各压一半"，而是**两者互斥**：
        #        change=1（翻转）时 streak 被清零 ⇒ rigidity=0
        #        ⇒ 0.5 ~ 1.0 那一段**永远是空的**。
        #   新式：x = 1 - (1-change)(1-rigidity)                 → 值域 [0, 1]
        #        注释原文说「通道越是长期不变（**或**越是频繁翻转），压力越大」——
        #        **那个"或"字，均值与 max 都表达不了，noisy-OR 才是它的正确形式。**
        #   上界证明见 engine/constants.py 的 E_UPPER_BOUND。
        _x = 1.0 - (1.0 - change) * (1.0 - rigidity)
        # ★ 2026-10-28：把「上一轮输出被退回」并入结构压力。
        #   语义：这句话没能通过结构要求 ⇒ 结构被压迫。
        #   合并方式与 change/rigidity 一致（noisy-OR）：可累积、上界 1.0、
        #   且不会因为一次退回就冲到失效门槛。
        _rejected = bool(getattr(self, "_rejected_pending", False))
        self._rejected_pending = False
        self._reject_streak = self._reject_streak + 1 if _rejected else 0
        self._last_rejected = _rejected          # 留给 step() 填进 MechanismState
        if _rejected:
            _x = 1.0 - (1.0 - _x) * (1.0 - C.REJECT_WEIGHT)
        e = C.ERROR_MEMORY * self.e + (1.0 - C.ERROR_MEMORY) * _x

        trend = "FLAT"
        if e - self._e_prev > 0.03:
            trend = "RISING"
        elif self._e_prev - e > 0.03:
            trend = "FALLING"
        self._e_prev, self.e = self.e, e
        self._channel_prev = channel

        gate_open = abs(e) < self.cfg.error_high
        return {"e": e, "e_trend": trend, "gate_open": gate_open}

    # -------------------------------------------------------------- 第 3 层 意义

    def note_orientation(self, kind: str) -> None:
        """A3：告知**本轮**系统的注意力落在谁身上（下一轮生效）。

        [M]「人之所以为人，是因为他总是指向自身以外的某种事物或某人」

        kind：
          "外" —— 注意力落在对方身上。这就是 [M] 的**体验途径**：
                  系统**遇到了另一个人**。用户在场、管理员（家教）在场，都算。
          "内" —— 注意力落在自己的状态上（`REPORT_OWN_STATE` 的标签原文即
                  "以自我为中心"）。[M]：「自我实现越追求越容易失去」。
          "无" —— 判定不了。**不许猜。**

        ⚠️ 这个方法由上层在**行为定下来之后**调用，因为它要的是本轮的落点；
           而意义层在行为定下来**之前**就算完了。所以是"本轮告知、下轮生效"。
           这是真实的反馈回路，不是将就。
        """
        if kind not in ("外", "内", "无"):
            return
        self._orientation = {"外": 1.0, "内": -1.0, "无": 0.0}[kind]
        if kind == "外":
            self._orient_out += 1
        elif kind == "内":
            self._orient_in += 1

    def note_paths(self, has_attitude: bool) -> None:
        """A3（T17）：告知**本轮**意义是从哪条途径来的（下一轮生效，与指向同理）。

        ★ 体验途径**不由这里传入** —— 它等价于 `orientation > 0`，
          在构造落点时从 `self._orientation` 推出。同一个事实只允许有一个来源。

        ★ 创造途径**不接受任何输入**：本系统对它没有可观察量（纯对话形态，
          无实体干预现实）。所以 `path_creative` 恒为 0.0、`path_cre` 恒为 0 ——
          **这不是没实现，是如实标缺**，理由见 MechanismState.path_creative。

        参数
          has_attitude  本轮是否命中态度句。**"仅在不可改变时才算"那层门控
                        在标记层已经做了**（markers.json 的 attitude_clause._note），
                        此处不重复判断，也不放宽。
        """
        self._path_att = 1.0 if has_attitude else 0.0
        if has_attitude:
            self._cnt_att += 1
        if self._orientation > 0:       # 体验途径与指向同源
            self._cnt_exp += 1
        # 创造途径：**恒不累加** —— 无可观察量。计数器留着是为了让"它一直是 0"可见。

    def _layer3(self, d1: dict, d2: dict, obs: dict) -> dict:
        """意义层：算张力，定向。**只用前两层已经算出的量与自身历史，不用任何外部标准。**

        [M] 原句（这是本层存在的最强依据）：
          "人对意义的追寻会导致内心的紧张而非平衡。不过，**这种紧张恰恰是精神健康的必要前提。**"
          "精神健康有赖于一定程度的紧张——即**已完成的和有待完成的任务之间的紧张，
            或者是当下状态与理想状态之间的差距**。这种紧张是人固有的，也是精神健康所必不可少的。"
          "我认为，某些精神卫生学说主张人最需要的是平衡……**这种说法是错误和危险的**。"
          "人所需要的不是'内稳态'，而是我所谓的'精神动力'，
            也就是存在的动力处于一个**紧张的极化区**。"

        ⚠️ 用户已明确同意把"张力是动力源、张力趋零是病态"作为内生驱动源。
           并且**张力由系统自己的记录算出，不由用户输入直接给** ——
           这就避开了 E2（不制造痛苦）的红线：系统没有给用户添加任何困难。

        ⚠️⚠️ 这一层重写过一次，原因必须记下来（这是本项目最容易犯的一类错误）：

          第一版让张力 = |题面指向的水平 − 系统当前水平|，
          并计划给 corpus/topics.json 的每个话题加一个 `probe_level` 字段。

          **这个计划是错的。** 核对原书后发现两件事：
            1. 卢文格的 36 个项目**一律评在所有水平上**。
               `[p264]`："每个原始记录都有相同数量的项目评定，也就是 36 个，
                        因为我们总是运用 36 个句子主题。"
               他的评分算法（项目累积／递加规则）用的是**反应的分配**，
               不是"这个项目属于哪个水平"。项目本身**没有**水平属性。
            2. "题目指向某个水平"是帕克与哈维斯特那一组的做法，而卢文格
               `[p246]` 对它的评语是"**这个程序也有问题**"。
               所以照那个做法给话题打水平标注，等于把一个书里明确反驳的假设
               伪装成书里的依据 —— 这正是本项目一路在避免的事。

          修法：张力**只用前两层已算出的量**。
          弗蘭克尔的原话本来就是"已完成的和有待完成的任务之间的紧张，
          或者是**当下状态与理想状态之间的差距**" —— 那个"理想状态"由系统自己的
          设定点（静止基线）给出，不需要任何外部量表。

        张力是**瞬时状态**，不是累计总量（也改过一版）：
          把"未完成量"逐轮累加会让张力顶到上界 10.0 并饱和，饱和之后它就不再区分任何情景。
        """
        # 已完成：这一轮命中了态度句（第三途径）→ 记为完成的量
        # [M] 第三途径：在忍受不可避免的苦难时采取某种态度
        if obs.get("attitude"):
            self._completed += 1.0
        self._completed *= 0.90                 # 完成感会衰减（ENG）

        # ---- 未完成：由第 1 层算出的"想要 vs 能够得到"的差距
        # "有待完成的任务" = 想要回路指向的东西（它永远说"我想要更多"）
        # "当下状态"       = 当下分子能兑现的体验（l）
        #
        # 这正是 [D] 的核心机制：想要与喜欢由两套系统产生，
        # 差得越远，"想要更多"的驱力越无处安放 —— 那就是张力的来源。
        #
        # ⚠️ "想要"这里也改过一次（与第 1 层同步）：
        #   第一版用 `max(0, w - da_rest)`，而 w 那时只由词表标记驱动，
        #   于是 11/12 轮未完成恒为 0、张力恒为 0，机制整场只有一种状态。
        #   现在：`want_above` 直接由**行为性投入**给出（lean 已含"是否还在说"
        #   与"说得够不够多"），所以"一个人持续在讲、却没有一句落在具体体验上"
        #   这个状态终于能被算出来 —— 那正是最该说"先不往后看"的时候。
        # ⚠️ 张力必须是**状态变量**，不能是累加量。这里也犯过一次：
        #   曾经写成 `unfinished = want_above * (1 - l)`，而 want_above 由投入决定。
        #   投入恒定、l 持续下降 → 未完成逐轮单调上升 → 张力顶到上界 10.0 并**顶死**，
        #   之后它不再区分任何情景（实测 12 轮里 6 轮全是 OVERLOADED）。
        #   这与更早那次"未完成量逐轮累加导致饱和"是**同一个错误**，
        #   说明这个坑很容易再踩 —— 所以下面写的是一阶动力学，没有累加项。
        #
        #   → deficit 最大 ≈ 17，乘 tension_scale 落到 0–10。
        # 它是自限的：投入停下，张力就回落；体验补上，张力也回落。
        #
        # 现在的定义：张力衡量的是**当前这一刻，"想要"与"能够得到"差多少**。
        #   want_above 满投入 ≈ 18（兴奋带量级）；(1-l) 最大 ≈ 0.95
        # "想要"的高度来自行为性投入（`self._lean`，第 1 层刚算出，自参照）。
        want_above = self._LEAN_TO_HZ * 3.0 * self._lean
        deficit = want_above * (1.0 - d1["l"])
        self._unfinished_last = deficit

        # 技能：被"答到题上"训练出来的能力（[E] 平衡化：能力随被处理过的负载上升）
        if obs.get("engaged"):
            self._skill += 0.25
        # 应对能力：体验充足度 × 技能 × 结构可用度
        # [D] 当下分子枯竭时，任何事都变得更难 → 能力下降
        self._capacity = (d1["l"] * 0.4 + 0.6 * min(1.0, self._skill)) * \
            (1.0 - min(0.6, abs(d2["e"]) * 0.5))

        # 张力一阶动力学 —— 量纲标定说明（这一处必须写清楚，否则后人无从判断）：
        #   want_above 满投入 ≈ 18（兴奋带量级），(1-l) 最大 ≈ 0.95
        #   → deficit 最大 ≈ 17。减掉完成感与应对能力后，再乘 tension_scale 落到 [0,10]。
        #   tension_scale 是**量纲换算**（把"Hz×缺口感"映射成 0–10 的张力量表），
        #   不是主观权重。取 1.1 而不是 2.0：2.0 时张力在第 6 轮就顶死 10.0，
        #   之后 6 轮全判 OVERLOADED，**饱和之后它不再区分任何情景**（实测）。
        #   取 1.1 后同样的输入落在 0.7–7 之间，全程保留分辨力。
        target = max(0.0, deficit - self._completed * self.cfg.completion_relief
                     - self._capacity * self.cfg.capacity_relief)
        raw = target * self.cfg.tension_scale
        self._tension = max(0.0, min(C.TENSION_SCALE_MAX,
                                     0.55 * self._tension + 0.45 * raw))
        # 张力由自身量算出，**始终可测** —— 不再依赖任何外部锚点
        self._tension_measured = True
        return {"tension": self._tension, "completed": self._completed,
                "unfinished": deficit, "capacity": self._capacity}

    # -------------------------------------------------------------- 主入口

    def note_rejected(self, rejected: bool) -> None:
        """登记**上一轮**的输出有没有被闸门退回（2026-10-28）。

        为什么这是她自己的可观察量，而不是外部意见：
          退回是**事实**（她的话没被放出去），不是评价（"太机械了"）。
          tutor 的意见不该进她的记忆（train.py:348-350 的理由对），
          但"我说出去的话没能通过"是她自己的经历，所以该成为她的状态。

        ⚠️ 时序：`step()` 在渲染**之前**跑，所以这里登记的值由**下一轮**消费 ——
           那正是正确语义："我上一句话没出去"是上一轮发生的事。
        """
        self._rejected_pending = bool(rejected)

    def step(self, markers: list[str], raw: str, channel: str,
             context_key: str, stem_level: float | None = None,
             engaged: bool = False) -> MechanismState:
        """推进一轮。返回的**全是数**，没有任何文字。"""
        self._turn += 1
        obs = self._observe(markers, raw, stem_level, engaged)
        d1 = self._layer1(context_key, obs)          # 动力
        d2 = self._layer2(channel)                   # 结构（门控）
        d3 = self._layer3(d1, d2, obs)               # 意义（定向，只用前两层已算出的量）

        # ---- 位阶纪律：第 1 层不许绕过第 2 层
        # "绕过第 2 层"就是过度意向 —— 它是数值状态，不是词表命中的东西。
        forbidden = (not d2["gate_open"]) or obs.get("over", False)

        st = MechanismState(
            turn=self._turn,
            # ★ 2026-10-28：她自己的失败读数（上一轮输出有没有被退回）
            #   `_layer2` 已把结果留在 self 上（它才是算 e 的那一层）。
            rejected=bool(getattr(self, "_last_rejected", False)),
            reject_streak=self._reject_streak,
            w=round(d1["w"], 3), l=round(d1["l"], 3), novelty=round(d1["novelty"], 3),
            lean=round(self._lean, 3), lean_raw=obs["lean_raw"],
            askable=obs["askable"], has_attitude=bool(obs.get("attitude")),
            is_closing=bool(obs.get("closing")),
            delta_r=round(d1["delta_r"], 3), a=round(d1["a"], 3),
            # ★ 公式版本标记（用户裁定 2026-10-02：架构层数据分界）
            #
            #   1 = 旧公式 `e = γ·e + (1-γ)·(change+rigidity)/2`，值域 [0, 0.5]
            #   2 = 方案 B noisy-OR，值域 [0, 1]
            #   **两者不可直接比较** —— 分析历史台账前必须先看这个字段。
            #   为什么会漏：第 1~4 步换了公式却**没打标**，
            #   于是台账里新值旧值混在一起、事后分不开。用户点名插队补上。
            e_version=C.E_VERSION,
            e=round(d2["e"], 3), e_trend=d2["e_trend"],
            tension=round(d3["tension"], 3), tension_measured=self._tension_measured,
            completed=round(d3["completed"], 3),
            unfinished=round(d3["unfinished"], 3), capacity=round(d3["capacity"], 3),
            # A3 意义层：指向。由上一轮的实际落点决定（见 note_orientation）。
            orientation=self._orientation,
            orientation_out=self._orient_out, orientation_in=self._orient_in,
            # A3（T17）三条途径
            path_creative=0.0,             # ★ 恒 0：无可观察量，诚实缺位
            path_experiential=1.0 if self._orientation > 0 else 0.0,
            path_attitudinal=self._path_att,
            path_cre=self._cnt_cre,        # 恒 0
            path_exp=self._cnt_exp, path_att=self._cnt_att,
            forbidden_layer1=bool(forbidden),
            last_phase=self._last_phase,
        )
        st.phase = classify(st, self.cfg).id
        self._last_phase = st.phase
        st.notes = self._trace(st, d2)
        self._history.append(st.tension)
        return st

    def _trace(self, st: MechanismState, d2: dict) -> list[str]:
        """可追溯的说明。**只陈述数值与事实，不做解释**（[E] 最低限度推理）。"""
        n = ["w=%.2fHz（静止带 3–5，兴奋带 20–30 [D]）  l=%.2f" % (st.w, st.l),
             "Δr=%.2fHz（＝实际−预期 [D]）  新颖度=%.2f（该情境第 %d 次）"
             % (st.delta_r, st.novelty, self.track.count.get(self._last_key, 0)),
             "a=%.2f（敏化增益）  e=%.2f（%s）  门控=%s"
             % (st.a, st.e, st.e_trend, "开" if d2["gate_open"] else "关"),
             "张力=%.2f（极化区 %.1f–%.1f [M]）"
             % (st.tension, self.cfg.tension_health_lo, self.cfg.tension_health_hi)]
        if st.forbidden_layer1:
            n.append("**第 1 层被禁止直接驱动输出**（结构未承认 / 过度意向）"
                     " —— 这是数值状态，不是词表命中")
        return n

    def snapshot(self) -> dict:
        return {
            "turn": self._turn,
            "w": round(self.w, 3), "l": round(self.l, 3),
            "a": round(self.a, 3), "e": round(self.e, 3),
            "tension": round(self._history[-1], 3) if self._history else None,
            "unfinished": round(self._unfinished_last, 3),
            "completed": round(self._completed, 3),
            "capacity": round(self._capacity, 3),
            "skill": round(self._skill, 3),
            "track": self.track.snapshot(),
            "config": asdict(self.cfg),
        }


# ------------------------------------------------------------------ 机制条件

@dataclass
class Condition:
    id: str
    label: str
    action: str
    source: str
    predicate: str        # 人类可读的判据（供文档与台账）
    test: object = None   # 可调用：st, cfg -> bool


def _mk(cid, label, action, source, predicate, fn) -> Condition:
    return Condition(cid, label, action, source, predicate, fn)


def conditions(cfg: MechanismConfig) -> list[Condition]:
    """机制条件 → 动作。**按顺序求值，先命中者胜。**

    这是"输出由机制状态决定"的落点。注意每个动作 ID 都是
    rules/behaviors.json 里**已经存在**的行为 —— 本层不新造言语行为。
    """
    return [
        # ---- 【排在第一位】收尾语：承认这次交流到此为止
        # 为什么排第一：用户给出的关键区分是——「就这样吧」有前情时是**收尾**，
        # 没有前情时是**怪话**。系统永远处在第一种情况（题面是它自己问的，
        # 前面还有它自己的回应），所以对它来说这永远是收尾，该承认，不该追问也不该复述。
        #
        # ⚠️ 用户举的回答「行，那就这样」**不能照说** —— 那个"行"是在表示同意，
        #    即接过对方结论的评判责任，违反 E3（『他绝对不允许患者将评判的责任转移给医生』）。
        #    正确的分界：
        #      「行，那就这样」          → 对**用户的决定**表态  ❌ 禁止
        #      「我记下了。这一轮就到这儿。」 → 只说**系统自己**要停  ✅ 合法
        #    这与 REPORT_OWN_STATE 是同一条纪律：只能说系统自己的状态。
        _mk("CLOSING", "收尾语（承认这次交流到此为止）", "ACKNOWLEDGE_CLOSE",
            "[E] 『一个人只能尝试去开门，他是否愿意穿过这扇门乃系他自己的选择。』"
            "[M] 不允许患者将评判的责任转移给医生 —— 故不能表示同意，只能陈述系统自己停在哪里。",
            "识别到收尾语（就这样吧／算了／不说了／嗯…，穷举字面名单）",
            lambda st, c: st.is_closing),

        # ---- 过度意向：干，但结构不承认
        _mk("DRIVE_UNACKNOWLEDGED", "驱力未被结构承认（＝过度意向）", "ASK_MUST",
            "[M] 过度渴望使所愿之事变得不可能；[E] 布莱西：关键因素是『一定』",
            "forbidden_layer1 为真 → 只允许 REFLECT / ASK_MUST，禁止任何提升",
            lambda st, c: st.forbidden_layer1),

        # ---- 想要高而喜欢低：欲望回路与当下回路分离
        _mk("WANT_NO_LIKE", "想要高、喜欢低、且低于预期", "REFLECT",
            "[D] 『欲望回路只是一个销售员』；『我们想要的东西往往是我们不喜欢的』",
            "w ≥ 兴奋带下沿 且 l ≤ 0.25 且 Δr < 0",
            lambda st, c: st.w >= DA_BURST_LO * 0.6 and st.l <= 0.25 and st.delta_r < 0),

        # ---- 当下枯竭：任何事都变得更难
        _mk("DEPLETED", "当下分子枯竭", "REPLENISH",
            "[D] 当下分子负责此时此地的真实体验；[M] 价值空缺时先补当下",
            "l ≤ 0.12（约为期望水平的 12%，接近文献中 +80% 剥夺的量级）",
            lambda st, c: st.l <= 0.12 + 1e-9),

        # ---- 张力爆表：减负载，不推进
        # ⚠️ 这条的动作原本是 TURN_IMMUTABLE（"这一块改不了"），**已改掉**。
        #   实测：张力顶到上界时，用户说的只是"有时候觉得挺累的"，
        #   而 TURN_IMMUTABLE 的模板会对他说"这一块改不了" —— 那是凭空断言
        #   他的处境不可改变。这是牛头不对马嘴的又一个版本，而且比原来那个更糟：
        #   原来只是答非所问，这个是在**替他下结论**。
        #   TURN_IMMUTABLE 只能在真的观测到 immutable 时用（那由 L2 处理，不归机制层）。
        #
        # ★ E3 世代再改一次：REFLECT → ACKNOWLEDGE。
        #   实测张力最高那一轮（7.52，用户说"我也不知道"）落回 REFLECT，
        #   输出又变成"我听到的是：「我也不知道」" —— 在最需要一句人话的时候复述。
        #   改判 ACKNOWLEDGE：张到最高时，能做的只有承认这件事有分量，别的不该做。
        _mk("OVERLOADED", "张力爆表", "ACKNOWLEDGE",
            "[M] 张力爆表 → 降负载，而不是加大难度；且不得替他判断处境可否改变",
            "tension ≥ 阈值上沿（＝健康带上沿）",
            lambda st, c: st.tension >= c.tension_up),

        # ---- 张力趋零：病态，不是健康
        # 只在张力**可测**时才判 —— 没有能力锚点时报"未测"，不报"趋零"。
        _mk("NO_TENSION", "张力趋零（无值得为之努力的东西）", "REPLENISH",
            "[M] 『人所需要的不是没有紧张的状态』『这种说法是错误和危险的』",
            "张力可测 且 ≤ 阈值下沿",
            lambda st, c: st.tension_measured and st.tension <= c.tension_low),

        # ---- 健康极化区：允许一次试探性推进
        _mk("HEALTHY_DRIVE", "处于健康的紧张极化区", "JUXTAPOSE",
            "[M] 『存在的动力处于一个紧张的极化区』",
            "张力可测 且 在健康区内 且 结构趋势 FLAT 且 门控开",
            lambda st, c: (st.tension_measured
                           and c.tension_health_lo <= st.tension <= c.tension_health_hi
                           and st.e_trend == "FLAT" and not st.forbidden_layer1)),

        # ---- 【E3】第三途径出现（attitude_clause）：承认，不复述
        # 实测补的：第 11 轮用户说「虽然身体回不到从前了，但我还能决定今天怎么过」，
        # 系统回的是「你用了这样一句话：……」。那句话正是全书最核心的高段表达
        # （[M] 第三途径：在忍受不可避免的苦难时采取某种态度），原样贴回去太浪费。
        #
        # ⚠️ 这里**不做任何褒奖**：不说"这很好""你进步了"——那是 E3 价值评判，
        #    而且会把发展的责任从用户那里接过来。只承认这句话有分量，然后停下。
        #    放在 ASKABLE 之前：态度句已经说完整了，追问反而显得没听懂。
        _mk("ATTITUDE_PRESENT", "出现第三途径（态度句）→ 承认", "ACKNOWLEDGE",
            "[M] 第三途径：『在忍受不可避免的苦难时采取某种态度』；"
            "『他绝对不允许患者将评判的责任转移给医生』——承认，但不褒奖。",
            "命中 attitude_clause",
            lambda st, c: st.has_attitude),

        # ---- 【E3 修正·主路径】张力已起、人还在讲，且这句话里有东西可问 → 问细节
        # 这一条是本次最重要的修正，理由是一次实测判定：
        #   用户对 A/B 输出两次给出的判定都是「只有第三组合理，其他完全是牛头不对马嘴」。
        #   查明原因：`TENSION_PRESENT` 的定义（"张力在健康区 且 结构趋势非 FLAT"）太宽，
        #   吃掉了 12 轮里的 6 轮，而它的动作是 REFLECT —— 于是绝大多数轮次都在复述。
        #   第 3 轮之所以是唯一合理的那一轮，恰恰因为它是**唯一没被 TENSION_PRESENT 拦住**的。
        #
        # 根因是**把复述当成了默认**。现改为反过来：
        #   **有话可问就问（ASK_DETAIL），问不出才复述（REFLECT）。**
        # [M] 依据：『生命对每个人都提出了问题』——想听懂那个问题，就该问它具体是什么样。
        #   而"复述"在 [E] 里只是**最低限度的兜底**（『我们试图在最低限度的推理水平上陈述观察』），
        #   它从来不是目标，只是无话可说时的诚实动作。
        _mk("ASKABLE", "张力已起、人还在讲、有话可问（问细节）", "ASK_DETAIL",
            "[M] 『生命对每个人都提出了问题，他必须通过对自己生命的理解来回答生命的提问。』"
            "——想听懂那个问题，就该问它具体是什么样。",
            "张力可测 且 > tension_low 且 有实质投入 且 这句话长到足以追问",
            lambda st, c: (st.tension_measured and st.tension > c.tension_low
                           and st.lean >= 0.5
                           and st.askable)),

        # ---- 张力在健康区，但结构趋势不稳：不推进，只照原样
        # ⚠️ 已被 ASKABLE 抢在前面（它更具体、更有依据）。保留作**兜底**：
        #    张力在健康区而这句话不足以追问时，只陈述观察。
        _mk("TENSION_PRESENT", "有张力但结构趋势未定", "REFLECT",
            "[E] 最低限度推理：『我们试图在最低限度的推理水平上陈述观察』",
            "张力可测 且 在健康区内 但 结构趋势非 FLAT",
            lambda st, c: (st.tension_measured
                           and c.tension_health_lo <= st.tension <= c.tension_health_hi
                           and st.e_trend != "FLAT")),

        # ---- 张力偏低但未到"趋零"：中间地带
        # 这一条是实测补的：张力落在 (tension_low, tension_health_lo) 之间的轮次
        # 会掉进 UNCLASSIFIED。条件表**必须覆盖整个区间**，
        # 否则机制层会在一段很常见的状态上无话可说 —— 那等于把死角换了个位置。
        #
        # ★ E3 世代起改为 ASK_DETAIL —— 这是"牛头不对马嘴"的正面修正：
        #   张力低而人还在讲，最像真人的反应是**想知道**（「发生什么了？」），
        #   而不是把对方的原话复述回去。
        #   [M] 依据：问题是被人带来的 —— 想听懂那个问题，就该问它具体是什么样。
        _mk("TENSION_LOW", "张力偏低而人还在讲（可问细节）", "ASK_DETAIL",
            "[M] 『生命对每个人都提出了问题，他必须通过对自己生命的理解来回答生命的提问。』"
            "『在意义疗法中，患者需要笔直地坐着，倾听那些有时很不中听的事情。』",
            "张力可测 且 低于健康区下沿 且 有实质投入（lean ≥ 0.5）",
            lambda st, c: (st.tension_measured
                           and c.tension_low < st.tension < c.tension_health_lo
                           and st.lean >= 0.5)),

        # ---- 上一轮刚问过细节，而状态没变：改为承认（既不查户口，也不复述）
        # 这一条是"不连问"规则的**必要配套**：加了"不能连续问细节"之后，
        # 第二次落进同一区间的轮次就没规则可命中，实测掉进 UNCLASSIFIED 并退回复述 ——
        # 等于把刚修好的问题换个地方又长出来。
        # 教训：**任何"排除"规则都必须配一条兜底**，否则它只是把死角挪了位置。
        _mk("ASKED_ALREADY", "刚问过细节、状态未变（改为承认）", "ACKNOWLEDGE",
            "[M] E3：不追问、不评价，只承认这件事有分量",
            "张力偏低 且 有实质投入 且 上一轮刚问过细节",
            lambda st, c: (st.tension_measured
                           and c.tension_low < st.tension < c.tension_health_lo
                           and st.lean >= 0.5
                           and st.last_phase == "TENSION_LOW")),

        # ---- 有实质投入但当下不足：承认他在讲的事有分量（温暖，不评判）
        # ★ E3 世代新增。用户明确要求"温度"但拒绝"评判"。
        #   判据（用户确认过）：温暖＝承认你说的事有分量；评判＝告诉对方什么才算重要。
        _mk("ACKNOWLEDGE_PRESENT", "在讲，但当下不足（承认，不评判）", "ACKNOWLEDGE",
            "[M] E3：只承认这件事有分量，绝不规定什么才算重要。"
            "『他绝对不允许患者将评判的责任转移给医生』",
            "张力可测 且 ≥ 健康区下沿 且 有实质投入 且 当下不足",
            lambda st, c: (st.tension_measured and st.tension >= c.tension_health_lo
                           and st.lean >= 0.5 and st.l < 0.75)),

        # ---- 投入已停而张力仍在：如实说出系统自己的状态（以自我为中心）
        # ★ E3 世代新增。来源是用户对"抱歉，我对你的经历不感兴趣"的**本意澄清**：
        #   「我的心情和我的利弊观告诉自己，跟你讨论这个问题是浪费时间。」
        #   这不是"我讨厌你"，是"我有自己的立场" —— 那正是"以自我为中心"的落点。
        #   纪律：只能说**系统自己的**状态，不得评价对方的经历（后者是 E3 ＋ 伤害）。
        _mk("NOTHING_MORE", "投入已停而张力仍在", "REPORT_OWN_STATE",
            "[M] 维也纳办公室：『那你属于哪个学派？』『我自成一派。』"
            "——他清楚自己是什么，就说什么，没有讨好提问者。",
            "张力可测 且 高于下沿 且 行为性投入已消失（lean < 0.5）",
            lambda st, c: (st.tension_measured and st.tension > c.tension_low
                           and st.lean < 0.5)),

        # ---- 结构被持续违反：方向不明，不假装知道
        _mk("STRUCTURE_INVALID", "结构持续被违反", "SILENCE",
            "[E] 平衡化：失衡推动重组，但重组期间不得假装已知道方向",
            "|e| ≥ 阈值上沿",
            lambda st, c: abs(st.e) >= c.error_high),
    ]


def classify(st: MechanismState, cfg: MechanismConfig) -> Condition:
    """把状态映射到一个机制条件。返回的 action 是**动作 ID**，不是文字。"""
    for c in conditions(cfg):
        try:
            if c.test(st, cfg):
                return c
        except Exception:                                       # noqa: BLE001
            continue
    return Condition("UNCLASSIFIED", "未被任何机制条件覆盖",
                     "REFLECT", "[E] 最低限度推理：判不出就不假装判出",
                     "兜底：仅复述", None)


# ------------------------------------------------------------------ 自检

if __name__ == "__main__":
    print("=== 机制层自检：同一句话重复 7 轮，看底层变量怎么动 ===")
    print("（没有 want_like_gap，所以 Δr 恒为 0 —— 不渴望就不会失望。这是对的。）")
    m = Mechanism()
    for i in range(7):
        st = m.step(["group_sanction"], "大家都这样，我也没办法。", "B", "T01:B")
        print("  轮%d  w=%6.2fHz  l=%.2f  新颖=%.2f  Δr=%6.2f  a=%.2f  张力=%.2f  → %s"
              % (st.turn, st.w, st.l, st.novelty, st.delta_r, st.a, st.tension, st.phase))

    print("\n=== 失望 → 敏化：建立预期之后落空 ===")
    m2 = Mechanism()
    for i in range(8):
        mk = ["want_like_gap"] if i < 3 else []
        raw = "我一定要得到那个结果" if i < 3 else "也就那样吧"
        st = m2.step(mk, raw, "B", "T10:B")
        print("  轮%d  %-4s w=%6.2fHz  Δr=%6.2f  a=%.4f  → %s"
              % (st.turn, "渴望" if mk else "落空", st.w, st.delta_r, st.a, st.phase))

    print("\n=== 当下分子：有具体体验 vs 没有 ===")
    m3 = Mechanism()
    for _ in range(8):
        st_a = m3.step([], "那天她把我送到楼下，风挺凉的。", "B", "T09:B")
    m4 = Mechanism()
    for _ in range(8):
        st_b = m4.step([], "反正就这样，没什么好说的。", "B", "T09:B")
    print("  有具体体验的句子：l=%.3f → %s" % (st_a.l, st_a.phase))
    print("  无可体验内容的句子：l=%.3f → %s" % (st_b.l, st_b.phase))

    print("\n=== 第三层张力：想要 vs 能够得到（越想要、越得不到，张力越高）===")
    for mk, tag in (([], "不渴望"), (["want_like_gap"], "渴望")):
        mm = Mechanism()
        for _ in range(6):
            st = mm.step(mk, "我一定要得到那个结果", "B", "T10:B")
        print("  %-4s w=%.1fHz l=%.2f → 未完成=%.2f 张力=%.2f → %s"
              % (tag, st.w, st.l, st.unfinished, st.tension, st.phase))
    print("  再加一件具体的可体验事件（补当下）→ 张力应当下降：")
    mm = Mechanism()
    for _ in range(6):
        st = mm.step(["want_like_gap"], "我一定要得到那个结果", "B", "T10:B")
    t_before = st.tension
    for _ in range(6):
        st = mm.step([], "那天她把我送到楼下，风挺凉的。", "B", "T10:B")
    print("    补当下前 张力=%.2f → 补当下后 张力=%.2f" % (t_before, st.tension))

    print("\n=== 位阶纪律：第 1 层不许绕过第 2 层 ===")
    m5 = Mechanism()
    st = m5.step(["over_intention"], "我一定要做到，我必须证明给他们看", "B", "T15:B")
    print("  forbidden_layer1=%s（过度意向是数值状态，不是词表命中）" % st.forbidden_layer1)
    for n in st.notes:
        print("    ·", n)

# -*- coding: utf-8 -*-
"""性格核：从经历里长出来的「我是什么样」

设计见 spec/经历驱动的性格层_v1.md §2、§3③。

理论落点（[E] 卢文格最关键的区分）
    「人格特质必须被假设为具有**极性和里程碑**的表现形式。」

| 类型 | 在本模块是什么 | 变化规律 |
|---|---|---|
| **极性变量** | 当下的倾向（愿不愿接话／耐不耐重复／对这个人有多少兴趣…） | 每轮都在动，可涨可落 |
| **里程碑** | **性格特征** —— 它变成了什么样的东西 | 越过阈值后固化，**不退回** |

而"固化"的机制 [E] 里有原句：
    **「遵守大小便规则不再被体验为一种意向或要求，而成了一种习惯。」**

⚠️ 极点说明：[Baldwin] 警告「年幼儿童……模仿强者并欺侮弱者」。
   一个只靠趋避学习的系统**一定会学成迎合**。
   所以本模块的极性变量里**没有"让对话继续"这一项** —— 那是奖赏，会导向迎合。
   有的是：愿不愿接（openness）、耐不耐重复（patience）、对这个人有多少兴趣（interest）、
   说话直不直（directness）、愿不愿承认对方的事（warmth）。

⚠️ 里程碑必须可查看、可解释、可用 era 回退（设计 §7 第 3 条：性格可能长歪）。
"""
from __future__ import annotations

# ★ 阈值从 SSOT 取（用户裁定：三处副本合一，方案乙）
import constants as C          # noqa: E402

import io
import json
import os
from dataclasses import dataclass, field, asdict
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包成 exe 后 `__file__` 指向解包出的临时目录 —— 于是 rules/corpus 找不到，
# 而且**台账会写进临时目录、退出就丢**。所以允许用 EGO_ROOT 指定项目根，
# 由启动器（exe）在导入任何引擎模块之前设置。
# 不设 EGO_ROOT 时行为与从前完全一致（源码运行时就是这个分支）。
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)

# 固化阈值。**待标定**（ENG）—— 需要跨会话数据才能定。
# 这个数现在只能靠猜，所以它进认输清单。
A_SOLIDIFY = 3          # 固化阈值（**待标定值**：没有数据支撑，见诚实声明）

# character.json 的 schema 版本。极性变量的**定义**变过就必须升版本 ——
# 否则旧文件里的同名字段会被当成新定义载入，把两个不相干的量接在一起。
SCHEMA = 2

# ---------------------------------------------------------------- 里程碑的判据
#
# 反应分两个方向。「接得住」= 他继续说了；「停在那儿」= 话没往下走。
# ⚠️ 这两类**不是好与坏**，只是方向 —— 本模块不打分、不排序、不做优化。
#    （硬约束①：不把"让对方继续说"当奖赏。见 association.py 模块头。）
CONTINUE_REACTIONS = ("ANSWERED_MORE", "ANSWERED_SAME")
STOP_REACTIONS = ("ANSWERED_LESS", "CLOSED", "CHANGED_SUBJECT", "SILENT")
# NO_REPLY（会话结束）**两边都不进** —— 它不是"他对我这个动作的反应"，
# 把它算进任一侧都是往判据里掺与判据无关的东西。
#
# TOPIC_MOVED（话题被调度挪走）同样两边都不进 —— 那是**机制**动的，不是他的反应。
# 这一条是本轮补的实测教训：第一版新判据把 TOPIC_MOVED 算进"停在那儿"，
# 于是「问」这个动作的 6 次里 5 次是调度换题，却推出"我问他细节时话就停在那儿"。
# ⚠️ 所以这里用的是**显式白名单**，任何新增的反应类型默认不参与，
#    必须有人明确决定它算哪一边 —— 默认不参与比默认参与安全。

# 每个动作的一句话说法。用于把"行为×反应"的条件关联说成人话，
# 且**主语必须是我**（E5：关于他的观察不许进输出）。
# ★ 名字与实算不符的变量必须自己说清（E5 世代补）。
#
# 为什么要有这张表：旧版 `patience` 的名字是"耐不耐重复"，实算的却是
# "话题平均多久被调度挪一次" —— 它测的是**调度器**，不是耐心。
# 一个显示成 0.84 的数字配上"耐不耐重复偏高"的标签，比没有这个数字更坏：
# 它会让人相信一件没有测量过的事。**没有测量就说没有测量**，不要用一个像样的数糊过去。
#
# 重定之后五个名字已经各自对上了一个机制量，剩下这两条**不是"名字不符"，
# 而是"这个量本身有它自己的来历"**，也必须一并说：
POLARITY_CAVEAT = {
    "wanting": "它的来源里含『他还在说』这项可观察行为（机制层的 lean 由字数推出），"
               "所以**不是纯自主的量**。想要≠喜欢这件事本身是对的（[D]），"
               "但别把这个数读成『我想不想』。",
    "structure": "这是我说的话与实际结构差多远。差得远**不等于**我说得不直 ——"
                 "旧版把这条叫『说话直不直』，那是我编的，没有任何测量支撑，已撤下。",
}

ACTION_PHRASE = {
    "问": "问他细节",
    "复述": "只是把他的话还回去",
    "承认": "承认他说的事有分量",
    "接住收尾": "接住他的收尾",
    "并排呈现": "把两边并排放给他看",
    "我换的话题": "把话题带走",
    "区分能改与不能改": "指出哪一部分改不了",
    "没出声": "不出声",
    "要求具体的体验": "要求具体的体验",
    "说自己": "说出自己的状态",
}


@dataclass
class Polarity:
    """极性变量：**当下的状态**。每轮都在动，可涨可落。

    ★★ 本轮重定（这是本模块最要紧的一次修正）

    旧版把五个"倾向"（愿不愿意接话／耐不耐重复／对这个人有多少兴趣／
    说话直不直／愿不愿意承认对方的事）用**累积到今天的占比**算出来。
    两个问题叠在一起：
      ① 分母只长大 → 值随聊天变长单向漂移。实测同一个系统，
         openness 只聊 5 轮是 0.60、聊满 55 轮是 0.16 —— 测的是你聊了多久。
      ② 更根本的：openness／warmth／directness 这三个名字**是我编的倾向，
        背后没有任何测量**。正因为没有量可读，才只能拿计数去凑，
        所以它们必然撒谎。（interest 也一样：分子分母都是**他的**行为。）

    裁定：**极性变量的名字必须能被一个机制量直接兑现；兑现不了的撤下，不许硬凑。**

    于是五个名字全部换成三本书各自给的量，名字即公式，无从撒谎：

    | 名字 | 读哪个量 | 公式 | 出处 |
    |---|---|---|---|
    | wanting  想要   | `w`（Hz）         | (w−4.0)/(30.0−4.0) | [D] 静止带 3–5／爆发带 20–30 |
    | liking   喜欢   | `l`（[0,1]）      | l                  | [D] 想要≠喜欢 |
    | patience 耐重复 | `a`（敏化增益）   | 1 − a/4.0          | [D] 失望累积成敏化 |
    | structure 结构压力 | `e`（结构预测误差） | min(1, abs(e)/0.60) | [E] 平衡化 |
    | tension  张力   | `tension`（0–10） | tension/10         | [M] 张力趋零是病态 |

    ⚠️ 两条必须写在名字旁边的实话：
      · `wanting` 的来源里含"他还在说"这项可观察行为（机制层的 lean 由字数推出），
        所以它**不是纯自主的量**。
      · 旧的累积占比没有删，搬到「行为分布（累积，非状态）」那一栏 ——
        它是"我做过什么"的历史占比，不是状态，且会随轮次漂移。
    """

    wanting: float = 0.0       # [D] 想要（相对静止带／爆发带归一化）
    liking: float = 0.0        # [D] 喜欢（就是机制层的 l）
    patience: float = 1.0      # [D] 敏化的反面：越不敏化越耐得住重复
    structure: float = 0.0     # [E] 结构压力：我说的与实际结构差多远
    tension: float = 0.0       # [M] 张力（0–10 归一化到 0–1）
    # ★ 2026-10-29（Gemini 拍板）：**愿不愿意朝外探** —— 唯一一个
    #   **只由经历累积**、与当下机制快照严格解耦的极性变量。
    #
    #   为什么需要它：`modulate` 只能向保守方向走（结构性防讨好），
    #   所以"经历"只能让她越来越小。但 `[E]` 说自我是**双向**长出来的。
    #   ⇒ 不动 `modulate`（讨好防线保持"结构上不可能"），
    #     另开这一个**读数**：经历里"亮出矛盾→对方接着深聊"（CONFIRMED）
    #     让她更敢，"亮出→对方收尾"（REBUFFED）让她更收。
    #
    #   ⚠️ 它**不进入 `modulate` 的任何决策** —— 所以不削弱防讨好结构。
    #   ⚠️ 公式写在这里，名字即公式：clamp(0.5 + 0.08*(confirmed - rebuffed), 0, 1)
    boldness: float = 0.5

    def to_dict(self) -> dict:
        return {k: round(v, 3) for k, v in asdict(self).items()}

    def clamp(self) -> None:
        for k, v in asdict(self).items():
            setattr(self, k, max(0.0, min(1.0, v)))


# 张力量的量纲常量必须与 mechanism.py 保持一致 —— 不一致就会算出一个"看起来像"的数。
# 这些值取自 MechanismConfig 的默认：da_rest=4.0（静止带中点）、da_ceiling=30.0（爆发带上沿）、
# sensitization 上限 4.0、error_high=0.60、张力量表 0–10。
_POLARITY_BANDS = {
    "da_rest": 4.0,
    "da_ceiling": 30.0,
    "a_max": 4.0,
    "error_high": C.ERROR_HIGH,
    "tension_scale_max": 10.0,
}

POLARITY_SOURCE = {
    "wanting": "[D] 想要（Hz，静止带 3–5／爆发带 20–30）",
    "liking": "[D] 喜欢（当下分子，与想要不是一回事）",
    "patience": "[D] 敏化增益的反面（失望累积得越多，越耐不住重复）",
    "structure": "[E] 结构预测误差（平衡化压力）",
    "tension": "[M] 张力（趋零是病态，不是健康）",
}

POLARITY_NAME = {
    "wanting": "想要",
    "liking": "喜欢",
    "patience": "耐重复",
    "structure": "结构压力",
    "tension": "张力",
}

# ---------------------------------------------------------------- 第 3 步：介入强度序
#
# 从左到右 = 从最主动到最保守。**性格只能向右推。**
# 这个序不是审美排序，是"这个动作替对方定了多少东西"：
#   ASK_MUST        逼出一个「必须」（替对方定问题的形状）
#   TURN_IMMUTABLE  判定不可改变（替对方定事实的边界）
#   JUXTAPOSE       指出两边并存（替对方把结构定下来）
#   ASK_DETAIL      追问（把话往深处带，但不下结论）
#   REPLENISH       补上当下可体验的东西
#   REFLECT         只复述，什么都不定
#   ACKNOWLEDGE     承认，不推进
#   ACKNOWLEDGE_CLOSE 承认收尾
#   SILENCE         什么都不说 —— 最保守
#
# ⚠️ 第一版把 TURN_IMMUTABLE 排在 JUXTAPOSE **之后**，于是 R2（"不许下断言"）
#    会把并排呈现降成"判定不可改变" —— **降到了一个更硬的断言上**，
#    规则自己打自己。是 tests/audit_character_influence.py 的合成用例抓到的。
#    排序的判据必须是"替对方定了多少东西"，不是"听起来强不强"。
CONSERVATISM = ["ASK_MUST", "TURN_IMMUTABLE", "JUXTAPOSE", "ASK_DETAIL", "REPLENISH",
                "REFLECT", "ACKNOWLEDGE", "ACKNOWLEDGE_CLOSE", "SILENCE"]

# 「断言型」动作：它们替对方把某件事定下来（问题的形状／事实的边界／结构）。
# ★ 必须是 CONSERVATISM 的**前缀** —— 这样"降到第一个非断言动作"才总有解。
#   若断言集在序里是散的，降级就可能落在另一个断言上（第一版正是如此）。
ASSERTIVE = ("ASK_MUST", "TURN_IMMUTABLE", "JUXTAPOSE")

# E1 允许集（硬底线，不得被性格绕过去）：
# 「一旦判定不可改变，禁止任何水平提升型回应；只允许 仅复述／指出并存／切不可改变／补当下」
E1_ALLOWED = ("REFLECT", "JUXTAPOSE", "TURN_IMMUTABLE", "REPLENISH")

# 动作 ID → 里程碑的类别键（里程碑是按"我做了什么"分类的）
KIND_OF_ACTION = {
    "ASK_DETAIL": "问", "ASK_MUST": "问",
    "REFLECT": "复述", "ACKNOWLEDGE": "承认", "ACKNOWLEDGE_CLOSE": "接住收尾",
    "JUXTAPOSE": "并排呈现", "TURN_IMMUTABLE": "区分能改与不能改",
    "SILENCE": "没出声", "REPLENISH": "要求具体的体验",
    "REPORT_OWN_STATE": "说自己",
}


def polarity_from_mech(mech: dict, keep_boldness: float | None = None) -> Polarity:
    """从一轮机制快照读出极性变量。**归一化的唯一来源**（learn 与审计共用）。

    为什么要抽成函数：归一化公式一旦有两份拷贝，它们迟早会不一致，
    然后审计工具会用一份公式去"验证"另一份公式算出的数 —— 那是自证，不是验证。
    """
    b = _POLARITY_BANDS
    w = float(mech.get("w") or 0.0)
    l = float(mech.get("l") or 0.0)
    a = float(mech.get("a") or 0.0)
    e = abs(float(mech.get("e") or 0.0))
    tn = float(mech.get("tension") or 0.0)
    p = Polarity(
        wanting=(w - b["da_rest"]) / (b["da_ceiling"] - b["da_rest"]),
        liking=l,
        patience=1.0 - a / b["a_max"],
        structure=min(1.0, e / b["error_high"]),
        tension=tn / b["tension_scale_max"],
    )
    # ★★ 2026-10-30（**最后一处脑裂**，实测抓到的）：
    #
    #   `polarity_from_mech()` 每次都 new 一个 `Polarity()`，
    #   而 `boldness` 的**默认值是 0.50** ⇒
    #   每轮 `ch.update_state(mst.to_dict())` 都会把 `settle_encounter()`
    #   刚写进去的 `boldness` **冲回 0.50**。
    #
    #   ⇒ 于是 36 轮里 `settle` 明明跑了（离线重算应有 7 次 CONFIRMED），
    #     而落盘的 `boldness` 永远是 0.50。
    #   ⚠️ 这不是"读不到"，是"读到了但下一步就覆盖" ——
    #      和 Gemini 说的「生命周期断层」是同一个病，只是发生在**内存里**。
    #
    #   ⇒ `boldness` 是**只由经历累积**的量，和机制快照无关
    #     ⇒ 必须由调用方把它传进来保留，公式侧不许给它赋值。
    if keep_boldness is not None:
        p.boldness = max(0.0, min(1.0, float(keep_boldness)))
    p.clamp()
    return p


@dataclass
class Milestone:
    """里程碑：固化后不退回（但会被后续经历加厚）。"""

    key: str
    text: str                  # 关于自己的陈述（**主语必须是"我"**）
    evidence: int              # 历史最高水位（固化后不退回 —— 见 learn() 的 max()）
    era: str = "?"
    first_turn: int = 0
    # ★ 当前证据数（E5 世代新增）。
    #
    # 为什么必须与 evidence 分开（实测缺陷）：
    #   `evidence` 是**历史最高水位**，设计意图是"固化后只变厚、不退回"。
    #   但修掉关联矩阵的跨会话 bug 之后，「我换的话题」的真实次数从 20 掉到 9，
    #   而界面仍显示「证据 20 次」—— 读的人会把它当成**当前**计数，于是被一个
    #   已经作废的数字说服。水位本身不该删（它记录了曾经到过哪里），
    #   但必须与当前值一起显示，否则"不退回"就变成了"不许更正"。
    current: int = 0
    # ★ 依据（E5 世代新增）：这个陈述是从什么数里长出来的。
    #   必须存，因为新判据是**条件关联**（我做 X 之后多半怎样），不是一个计数。
    #   不存依据，读的人就只能看到一句断言，无法核对它是否站得住 ——
    #   那正是旧判据最大的毛病（"证据 20 次"看起来像证据，其实是动作次数）。
    basis: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class Character:
    """性格核。它回答一个问题：**它变成了什么样的东西。**"""

    STORE = "character.json"

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(_ROOT, "state", self.STORE)
        self.polarity = Polarity()
        self.milestones: list[Milestone] = []
        self._events: list[tuple[str, str]] = []      # (原句, 我的归类)
        self._basis: dict = {}                        # 各极性变量的 (分子, 分母, 公式)
        self._polarity_caveat: dict = {}              # 名字与实算不符的说明
        self._state_read_from: str = "（还没读过）"    # 极性变量读自哪个当下
        self._milestone_details: list = []            # 全部候选的固化/未固化与理由
        self._load()

    def polarity_basis(self) -> dict:
        """返回 {变量: (分子, 分母, 公式)}。learn() 之后才有内容。"""
        return dict(self._basis)

    def polarity_caveats(self) -> dict:
        """每个量的来历与它**不是**什么。宁可说没有测量，也不要给一个像样的数糊过去。"""
        return dict(self._polarity_caveat)

    def state_read_from(self) -> str:
        """极性变量是从哪个"当下"读出来的。读不到时必须说出来。"""
        return getattr(self, "_state_read_from", "（还没读过）")

    # ------------------------------------------------ 第 3 步：性格影响行为

    def update_state(self, mech: dict | None) -> None:
        """每轮调用的轻量更新：只刷新极性变量（读机制快照），不碰里程碑。

        为什么不每轮都跑 learn()：learn 需要整个关联矩阵（要重新派生、重写
        association.jsonl）。极性变量只需要"当下"，而当下就在机制快照里。
        分工：每轮 update_state（便宜）／打 /character 时 learn（完整）。
        """
        if not mech:
            return
            # * 2026-10-30：**必须把现有 boldness 传进去保留** ——
            #   否则每轮 update_state 都会把它冲回默认 0.50（实测抓到的最后一处脑裂）。
            self.polarity = polarity_from_mech(
                mech, keep_boldness=getattr(self.polarity, "boldness", None))
            self._state_read_from = "第 %s 轮机制快照" % mech.get("turn", "?")
        self.save()

    #: 每一次遭遇对 `boldness` 的增量（ENG 待标定）
    #  ⚠️ 不对称是**故意的**：受挫的权重是确认的两倍（见 learn() 里的注释）
    BOLD_GAIN_CONFIRMED = 0.03
    BOLD_GAIN_REBUFFED = -0.06

    def settle_encounter(self, encounter: str) -> float:
        """**单轮内**结算一次遭遇，就地增量更新并 clamp `boldness`，立即落盘。

        ★ 2026-10-30（架构病灶 1+2+5 的落点）：这是把 `boldness`
          从"批处理末尾算一次的死数字"变成"每轮当场结算的有界状态机"。

        ★ 为什么必须在**单轮内**做：
          · `train.py` 的 `_regrow()` 只在 36 轮**全部跑完**之后才调一次
            ⇒ 36 轮里每一轮读到的 `boldness` 都是**上一场的旧值**；
          · 而 `shell.py`（真人交互）**根本没有 `_regrow()`**
            ⇒ 跟真人聊天的整个生命周期里，性格**永远不更新**。
          ⇒ 所以结算点必须搬到 `turn()` 里，每轮一次。

        ⚠️ 幂等性：调用方负责**不要让同一对遭遇被结算两次**
           （`pipeline.turn()` 里用 `_last_settled_turn` 挡住）。
        """
        if encounter not in ("CONFIRMED", "REBUFFED"):
            return self.polarity.boldness
        delta = (self.BOLD_GAIN_CONFIRMED if encounter == "CONFIRMED"
                 else self.BOLD_GAIN_REBUFFED)
        # ★ 每一步都 clip —— 这才是有界状态机，而不是"先累加后截断"
        self.polarity.boldness = max(0.0, min(1.0, self.polarity.boldness + delta))
        self._last_encounter = encounter
        self.save()
        return self.polarity.boldness

    def _note_encounter_milestone(self, confirmed: int, rebuffed: int) -> None:
        """把「深度遭遇」的累积固化成一条里程碑。

        ★ 为什么用"固化"而不是"每轮追加一条"：
          `Milestone` 的语义就是**固化后不退回**（见它的 docstring）。
          同一个 key 只留一条，证据用 `current` 更新 —— 与既有机制一致。
        """
        key = "deep_encounter_confirmed"
        if any(m.key == key for m in self.milestones):
            for m in self.milestones:
                if m.key == key:
                    m.current = confirmed
                    m.evidence = max(m.evidence, confirmed)
                    m.basis = ("确认 %d 次 / 受挫 %d 次｜boldness=%.2f"
                                 % (confirmed, rebuffed, self.polarity.boldness))
            return
        self.milestones.append(Milestone(
            key=key,
            text=("我曾 %d 次把注意到的两处拉扯或没落地的悬念亮出来，"
                  "对方接着往深处多说了一层" % confirmed),
            evidence=confirmed, current=confirmed,
            era=getattr(self, "era", "?"),
            basis=("确认 %d 次 / 受挫 %d 次｜boldness=%.2f"
                     % (confirmed, rebuffed, self.polarity.boldness))))

    def _allowed(self, rule: str) -> bool:
        """A2 门控：自我当前**能行使**这一条吗。

        [E]「自我是内驱力的**对抗者**；然而，自我又是**部分地由内驱力构成**的」

        ⚠️ 这两半必须分开实现，否则会把设计做反：
          · 「部分由内驱力构成」—— **已经在跑**：极性变量由 polarity_from_mech 算出。
            所以自我**照常形成、照常更新**，这一半不受任何门控。
          · 「对抗者」—— 这一半**是长出来的**：低水平时自我还拦不下冲动，
            机制层建议什么就执行什么（[E] 的 I-2 冲动阶段）。
          所以变的不是自我，是它**能不能行使**。

        `self._allowed_rules is None` = 不门控（旧行为，向后兼容）。
        """
        return self._allowed_rules is None or rule in self._allowed_rules

    def modulate(self, action: str, markers: list[str] | None = None,
                 last_behavior: str | None = None,
                 allowed_rules: set[str] | None = None) -> tuple[str, str | None]:
        """第 3 步：让长出来的性格参与裁决。返回 (动作, 理由或 None)。

        ★★ 三条结构性护栏（缺一条这一步就不该做）

        ① **只能往保守方向推，绝不更主动。**
           这一条不是自觉，是**结构**：本函数只沿 CONSERVATISM 列表**向右**走，
           永远不向左。讨好的失败模式必然是"做更能留住对方的事"（问更多、
           接更多、更主动），而那需要向左走 —— 结构上做不到，所以这条路上
           产生不了讨好。这也是用户对整层的原话：「输出要比现在更受约束，
           而不是更自由。」

        ② **E1 在场时，结果必须仍落在 E1 允许集内。**
           immutable 命中时 E1 只允许 仅复述／指出并存／切不可改变／补当下。
           降级若落到集合外（比如 ACKNOWLEDGE），就是把伦理闸门绕过去了。
           所以这里显式限制候选集，不靠下游再拦。

        ③ **刻意不用 `wanting`。**
           实测（tests/audit_behavior_sensitivity.py）行为选择对 `w` 不敏感，
           所以它是新信息、本可以用。但 `w` 的来源含"他还在说"这项可观察行为
           （机制层的 lean 由字数推出）。拿它决定行为，等于让系统按**用户说得
           多不多**来调整自己 —— 那正是 Baldwin 警告的讨好路径。
           **宁可少一条规则，也不留这条路。**
           `liking`／`tension` 也不用：实测它们本来就是冗余的（机制层已敏感），
           再读一遍只是同一个数换刻度。

        三条规则各自的依据与阈值都写在下面，阈值全部是**待标定值**。
        """
        # A2 门控（见 `_allowed`）：不传 = 三条全开（旧行为，向后兼容）
        self._allowed_rules = allowed_rules
        if action not in CONSERVATISM:
            return action, None
        ms = set(markers or [])
        i = CONSERVATISM.index(action)
        reasons = []

        # ---- R4 ★ 2026-10-30（主线任务 1）：**刚碰了钉子就收一收**
        #
        #   [E] 平衡化不是"碰壁就停"，而是**碰壁后调整**。
        #   但这里只走一个方向：**向右（更保守）** —— 与 B9 的结构护栏完全一致。
        #
        #   触发：① 最近一次深度遭遇是 `REBUFFED`（她亮出拉扯后，对方收住了）
        #         ② 或 `boldness` 偏低（< 0.42，确认少、受挫多）
        #   动作：若当前选中的是**较激进的探照动作**，沿 CONSERVATISM 向右退一格。
        #
        #   ⚠️ 它**不读 `boldness` 去决定向左** —— 那样的代码一行都没有（B9 会抓）。
        _enc = getattr(self, "_last_encounter", "")
        _bd = getattr(self.polarity, "boldness", 0.5)
        if self._allowed("R4") and ((_enc == "REBUFFED") or (_bd < 0.42)):
            _i = CONSERVATISM.index(action)
            _probe = ("JUXTAPOSE", "ASK_DETAIL")
            if action in _probe and _i + 1 < len(CONSERVATISM):
                _nxt = CONSERVATISM[_i + 1]
                if (not ms & {"immutable"}) or _nxt in E1_ALLOWED:
                    i = _i + 1
                    reasons.append("R4 刚碰了钉子（%s / 笃定 %.2f）⇒ 往回收一格：%s → %s"
                                   % (_enc or "低笃定", _bd, action, _nxt))
                    action = _nxt

        # ---- R1 耐心：同一个动作连着做，效果递减
        # [D] 敏化：反复落空的期待会抬高想要，同时让同类刺激越来越难满足。
        # 落到行为上就是：连着做同一个动作，越做越没用。
        # 阈值 patience < 0.35 ⇔ a > 2.6（敏化上限 4.0 的 65%）—— **待标定**。
        if (self._allowed("R1") and self.polarity.patience < 0.35
                and last_behavior and action == last_behavior):
            reasons.append("耐心 %.2f 偏低，且上一轮做的就是 %s（同一动作连着做效果递减 [D] 敏化）"
                           % (self.polarity.patience, action))

        # ---- R2 结构压力：结构被违反时不许下断言
        # [E] 平衡化原句：失衡推动重组，**而重组期间不得假装已知道方向**。
        # 机制层的 STRUCTURE_INVALID 条件写的就是这条，但它是条件表第 15 条，
        # 先到先得 —— 实测 58 轮里一次也没轮到（和 NOTHING_MORE 同一种死法）。
        # 所以这条判断在这里给它一条真正的通路。
        #
        # ⚠️ 阈值用**机制层自己声明的线**（|e| ≥ error_high），不用我拍脑袋的数。
        #    第一版我写了 `structure > 0.80` —— 既是我编的，又会让这条与
        #    STRUCTURE_INVALID 各说各话（同一条理论、两条不同的线）。
        #
        # ⚠️⚠️ **但这条规则目前是死的，必须说出来**：本批数据 68 轮里
        #    structure 最大只到 0.682（|e|≈0.409），而 error_high = 0.60。
        #    它与 STRUCTURE_INVALID 共享同一个问题：阈值落在可达范围之外。
        #    是端到端用例（test_pipeline K2）抓出来的 —— 我原本用 character.json
        #    注入 structure=0.95，结果管线每轮都会用机制快照把它刷回真实值，
        #    于是才发现"这个阈值根本达不到"。
        #    **我没有为了让它亮起来而下调阈值** —— 那正是本模块一直在修的那种错。
        r2 = self.polarity.structure >= 1.0 and action in ASSERTIVE
        if r2 and not self._allowed("R2"):
            r2 = False                            # A2：这一级还行使不了这条
        if r2:
            reasons.append("结构压力 %.2f 已达机制层上沿（|e| ≥ error_high），"
                           "此时不得下断言 [E] 平衡化" % self.polarity.structure)

        # ---- R3 里程碑：跨会话学到的"这个动作多半停在那儿"
        # 这是本层唯一真正跨会话的信息 —— 机制层只看当下，里程碑是累积出来的。
        # 判据沿用固化时的口径：stop 占 ≥ 2/3 才算"多半停在那儿"。
        if self._allowed("R3"):
            for m in self.milestones:
                if ACTION_PHRASE.get(m.key) is None:
                    continue
                if not m.text.startswith("我%s的时候，多半就停在那儿" % ACTION_PHRASE[m.key]):
                    continue
                if m.key == KIND_OF_ACTION.get(action):
                    reasons.append("里程碑：%s（依据 %s）" % (m.text, m.basis or "缺"))
                    break

        if not reasons:
            return action, None

        # ---- 选目标：**只往右走**，且落点必须同时满足两条硬约束
        #   ① R2 触发时不得落在断言集里（否则规则自相矛盾）
        #   ② immutable 在场时必须落在 E1 允许集里（否则绕过伦理闸门）
        blocked = set(ASSERTIVE) if r2 else set()
        cands = [a for a in CONSERVATISM[i + 1:] if a not in blocked]
        if "immutable" in ms:
            cands = [a for a in cands if a in E1_ALLOWED]
        if not cands:
            return action, None            # 无路可退 → 保持原样，交给下游闸门
        target = cands[0]
        return target, "；".join(reasons) + " → 由 %s 降为 %s" % (action, target)

    def milestone_details(self) -> list:
        """全部候选（含**未固化**的）与各自理由。

        为什么未固化的也要给出去：只报成功的那几条，读的人就看不到判据在哪里切的，
        也就无法质疑阈值合不合理 —— 而阈值恰好是本层唯一靠猜的数。
        """
        return list(self._milestone_details)

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with io.open(self.path, encoding="utf-8") as handle:
                d = json.load(handle)
            # ★ 极性变量换了定义（E5），旧文件里的同名字段含义完全不同
            #   （旧 patience = 1 − 换题占比 ≈ 0.84；新 patience = 1 − 敏化/4）。
            #   直接按名字载入会把两个不相干的量接在一起 —— 那正是本模块一直在修的错。
            #   所以按 schema 版本判断：版本不符就**丢弃极性值**，保留里程碑（那是历史）。
            if d.get("_schema") == SCHEMA:
                self.polarity = Polarity(**{k: v for k, v in (d.get("polarity") or {}).items()
                                            if k in Polarity.__dataclass_fields__})
            self.milestones = [Milestone(**{k: v for k, v in m.items()
                                            if k in Milestone.__dataclass_fields__})
                               for m in d.get("milestones", [])]
        except (json.JSONDecodeError, TypeError):
            pass

    def save(self) -> None:
        from behavior_learning import atomic_json
        atomic_json(self.path, {
            "_schema": SCHEMA,
            "polarity": self.polarity.to_dict(),
            "milestones": [m.to_dict() for m in self.milestones],
            "note": "性格核。极性变量读机制层的当下状态；里程碑固化后不退回（[E] 意向→习惯）。",
        })

    # ------------------------------------------------ 从经历里长

    def learn(self, assoc, mech: dict | None = None) -> dict:
        """吃一个关联矩阵 + **最近一轮的机制快照**，更新极性变量与里程碑。

        ⚠️ 这里**不做加权优化、不算奖赏**。它做的是：
           ① 读机制层的当下状态 → 极性变量（慢变量，可涨可落）
           ② 数一数我做过什么、对方接着怎么反应 → 行为分布（累积，非状态）
           ③ 某一类事重复够多**且关联方向有据** → 固化成里程碑

        mech 为什么是必需的口子：极性变量是"当下的状态"，而"当下"只能来自
        最近一轮的机制快照。旧版拿累积占比冒充状态，根子就是这里没有"当下"可读。
        mech 为 None 时**不假装有状态**：保持原值并标注读不到。
        """
        pairs = getattr(assoc, "pairs", [])
        if not pairs and not mech:
            return {"updated": 0, "new_milestones": []}

        n = len(pairs)
        by_kind = Counter(p.my_kind for p in pairs)
        by_react = Counter(p.his for p in pairs)

        # ---- ① 极性变量 = 机制层当下状态的倾向读数（名字即公式）

        if mech:
            # * 2026-10-30：**必须把现有 boldness 传进去保留** ——
            #   否则每轮都会把它冲回默认 0.50（实测抓到的最后一处脑裂）。
            self.polarity = polarity_from_mech(
                mech, keep_boldness=getattr(self.polarity, "boldness", None))
            self._state_read_from = "第 %s 轮机制快照" % mech.get("turn", "?")
        # ★ 2026-10-29：`boldness` **必须放在 `polarity_from_mech` 之后**赋值 ——
        #   否则会被那一次整体覆盖冲掉（那正是"经历和当下混在一起"的老毛病）。
        #   它只读经历，不读机制快照。
        #
        #   公式（名字即公式）：clamp(0.5 + 0.08 * (confirmed - rebuffed), 0, 1)
        #   ⚠️ 0.08 是**待标定值（ENG）**：它决定"多少次确认遭遇能让读数明显偏离"。
        #      按 36 轮的量级（最多 30 个转移对）估，0.08 时 6 次净确认 ⇒ +0.48，
        #      正好走到量表上沿附近 —— 所以它既能看出趋势，又不会一轮就翻。
        _cf = int(getattr(assoc, "confirmed_count", 0) or 0)
        _rb = int(getattr(assoc, "rebuffed_count", 0) or 0)
        # ★★ 2026-10-30（架构病灶 5：**无界累加器顶死饱和**）：
        #
        #   原来：`boldness = clamp(0.5 + 0.08*(C-R), 0, 1)`
        #   ⇒ 它对**全量历史**先算总账再截断。
        #     36 轮跑出 C=9, R=1 ⇒ 未截断值 0.5+0.08*8 = 1.14 ⇒ 截到 1.00，
        #     **天花板之上堆了 0.14 的隐形泡沫**。
        #     此后哪怕连遭 10 次 REBUFFED，`C-R` 也只降到 -2 ⇒ 值 0.34 才动，
        #     而泡沫还在 ⇒ **负反馈彻底失效**。
        #
        #   ⇒ 改成**有界状态机**：boldness 是一个**自己持有**的状态，
        #     每次遭遇**在当步内**增量更新并就地 clamp：
        #       CONFIRMED ⇒ +0.03｜REBUFFED ⇒ -0.06｜无遭遇 ⇒ 不动
        #
        #   ⚠️ 为什么两边不对称（0.03 vs 0.06）：**受挫的权重必须是确认的两倍**。
        #      理由与 `modulate` 的防讨好结构一致 —— 一个"被肯定就更敢"的速度
        #      快于"被拒绝就收回"的系统，会长成一个冒失的东西。
        #   ⚠️ 这两个系数仍是**待标定值（ENG）**：量太少（36 轮 C=9/R=2），
        #      现在没有任何数据能推翻它们。已写进认输清单。
        #
        #   ⚠️ 它**只在 `settle_encounter()` 里被改**，`learn()` 不再重算整条历史 ——
        #      否则批处理一次会把"逐步增量"重放成"全量累加"，又回到老问题。
        self._boldness_source = ("stepwise", _cf, _rb)
        self._boldness_basis = {"confirmed": _cf, "rebuffed": _rb}
        # ★ 2026-10-30（主线任务 1）：**最近一次深度遭遇的结果**。
        #   它不参与 `modulate` 的"向左"决策（那永远禁止），
        #   只参与 Rule 4 的"向右收敛"和意识海的 idle 门控。
        self._last_encounter = str(getattr(assoc, "last_encounter", "") or "")
        # ★ 2026-10-29：里程碑**必须在 `boldness` 赋值之后**固化 ——
        #   否则它记下的 `basis` 里 boldness 还是初始的 0.50，
        #   读的人会以为"证据 5 次但读数没动"。（第一版就是这个顺序，实测抓到的。）
        if _cf >= 3 and _cf > _rb:
            self._note_encounter_milestone(_cf, _rb)
        if not mech:
            self._state_read_from = "**读不到**（没有机制快照）—— 保持上一次的值，不代表当下"

        # ★ 行为分布（累积占比）—— **不是状态**，单独留着并标清它会漂移。
        #   保留它的理由：它记录"我一向做过什么"，这是里程碑判据的输入之一，
        #   也有独立的追溯价值。撤下的只是它**冒充状态**的那部分。
        active = sum(v for k, v in by_kind.items()
                     if k in ("问", "承认", "并排呈现", "要求具体的体验", "说自己"))
        ch = by_react.get("CHANGED_SUBJECT", 0) + by_kind.get("我换的话题", 0)
        more = by_react.get("ANSWERED_MORE", 0)
        less = by_react.get("ANSWERED_LESS", 0)
        direct = by_kind.get("问", 0) + by_kind.get("说自己", 0) + by_kind.get("要求具体的体验", 0)
        reflect = by_kind.get("复述", 0)
        warm = by_kind.get("承认", 0) + by_kind.get("接住收尾", 0)
        self._basis = {
            "_口径": "累积占比（**不是状态**）：分母只长大，值会随聊天变长单向漂移。",
            "主动开口占比": (active, n, "主动开口轮／全部配对"),
            "换题占比": (ch, n, "（他明说换题 + 调度换题）／全部配对"),
            "他说更长占比": (more, more + less, "他接下来更长／（更长+更短）"),
            "朝外占比": (direct, direct + reflect, "问+说自己／（问+说自己+复述）"),
            "承认占比": (warm, max(1, n), "承认+接住收尾／全部配对"),
        }
        self._polarity_caveat = dict(POLARITY_CAVEAT)

        # ---- 里程碑：从「我做过什么」改成「我做了之后怎么样」
        #
        # ★★ 这是本层最要紧的一次改动。原判据只有一句：`by_kind[kind] >= A_SOLIDIFY`
        #    —— "这个动作我做够 3 次，就说这是我的性格"。
        #    问题不是阈值定得对不对，是**它根本没看对方那一半**：
        #      · 我自己做的动作，是我写死的规则表决定的，与经历无关
        #      · 于是固化出来的句子必然是"我做过什么"的复述，不可能是性格
        #      · 实测：四条里程碑的证据数（7/3/20/20）与行为统计的次数**逐一对应**，
        #        一个不差 —— 当时我就该看出来它只是在数自己的动作。
        #
        # 依据（三本书各自的落点）：
        #   [E] 米德：自我意识来自**用别人的观点描述自己** —— 所以判据必须落在
        #       "我做了之后他怎么样"，而不是"我做了几次"。
        #   [E] 洛文格：里程碑是**曲线型**的（他举的例子就是遵奉）。"从第一轮起
        #       按固定频率触发的动作"是常量，不是里程碑。新判据要求的是一个
        #       **关联**（做 X → 多半怎样），那才是可以随经历改变的东西。
        #   [D] Δr：一个动作的意义在于**实际结果与预期的差**。所以每个里程碑
        #       都要与**基线**（全部动作之后的平均情况）比，否则"接得住 60%"
        #       这种数字毫无意义 —— 可能所有动作都这样。
        #
        # 三个护栏（缺一不可）：
        #   ① 分母不含 NO_REPLY —— 会话结束不是"他对我这个动作的反应"
        #   ② 必须报**双向计数**，不允许只报有利的那一侧
        #   ③ 反面证据占比高时**不许下断言**，只许并列陈述
        #      （[E] 复合反应 composite rules：证据冲突时给出复合描述，不挑一个）
        cont = {k: 0 for k in ACTION_PHRASE}
        stop = {k: 0 for k in ACTION_PHRASE}
        for p in pairs:
            if p.my_kind not in ACTION_PHRASE:
                continue
            if p.his in CONTINUE_REACTIONS:
                cont[p.my_kind] += 1
            elif p.his in STOP_REACTIONS:
                stop[p.my_kind] += 1
        base_n = sum(cont.values()) + sum(stop.values())
        base_share = (sum(cont.values()) / base_n) if base_n else 0.0

        new = []
        have = {m.key for m in self.milestones}
        details = []
        for kind, phrase in ACTION_PHRASE.items():
            n_k = cont[kind] + stop[kind]
            basis = {
                "n": n_k, "continue": cont[kind], "stop": stop[kind],
                "share": round(cont[kind] / n_k, 3) if n_k else None,
                "baseline_share": round(base_share, 3),
                "acted": by_kind.get(kind, 0),
            }
            if n_k < A_SOLIDIFY:
                # ★ 不够格的也要列出来，并写明为什么 —— 只报固化成功的，
                #   读的人就看不到判据在哪里切的，也就无法质疑它。
                details.append((kind, "未固化", "有反应的样本 %d 次 < 阈值 %d" % (n_k, A_SOLIDIFY), basis))
                continue
            share = cont[kind] / n_k
            if share >= 2 / 3:
                text = "我%s的时候，话多半接得下去。" % phrase
                shape = "一致（接得住）"
            elif share <= 1 / 3:
                text = "我%s的时候，多半就停在那儿。" % phrase
                shape = "一致（停在那儿）"
            else:
                # 复合式：两边都有证据，**不许挑一个当结论**。
                text = "我%s的时候，有时接得下去，有时就停在那儿。" % phrase
                shape = "复合（两边都有证据）"
            near = abs(share - base_share) <= 0.10
            why = ("%s：%d 次里有反应 %d 次（接得住 %d／停在那儿 %d，%.0f%%）"
                   "；基线 %.0f%%%s"
                   % (shape, basis["acted"], n_k, cont[kind], stop[kind], share * 100,
                      base_share * 100,
                      "。**与基线接近，还看不出这个动作本身的影响**" if near else ""))
            details.append((kind, "固化", why, basis))
            if kind not in have:
                m = Milestone(key=kind, text=text, evidence=n_k,
                              era=pairs[0].era if pairs else "?",
                              first_turn=pairs[0].turn if pairs else 0,
                              current=n_k, basis=basis)
                self.milestones.append(m)
                new.append(m.to_dict())
            else:
                for m in self.milestones:
                    if m.key == kind:
                        m.text = text        # 判据变了，陈述必须跟着变
                        m.basis = basis
        # 已固化的：加厚证据（不退回，只变厚）
        for m in self.milestones:
            n_k = cont.get(m.key, 0) + stop.get(m.key, 0)
            m.evidence = max(m.evidence, n_k)
            m.current = n_k
        self._milestone_details = details

        self.save()
        return {"updated": n, "new_milestones": new}

    # ------------------------------------------------ 说出关于自己的话

    def self_statements(self) -> list[str]:
        """★ 这是「性格」的可观察落点。

        主语必须是**我**。凡是主语是"他"的，都不在这里 ——
        那些属于 noticed_about_user（注意到但不说，守 E5）。
        """
        out = []
        if self.milestones:
            for m in self.milestones:
                out.append(m.text)
        else:
            out.append("我还没有重复到足以说出「我一向怎么样」。")
        # 极性变量：**读的是机制层的当下状态**，不是累积占比。
        # 只报偏离中性较远的，否则等于没说。
        d = self.polarity.to_dict()
        for k, v in d.items():
            if v >= 0.65:
                out.append("我现在%s偏高（%.2f，%s）。" % (POLARITY_NAME[k], v, POLARITY_SOURCE[k]))
            elif v <= 0.35:
                out.append("我现在%s偏低（%.2f，%s）。" % (POLARITY_NAME[k], v, POLARITY_SOURCE[k]))
        return out

    def snapshot(self) -> dict:
        return {"polarity": self.polarity.to_dict(),
                "milestones": [m.to_dict() for m in self.milestones],
                "statement_count": len(self.self_statements()),
                "A_solidify": A_SOLIDIFY,
                "note": "A_solidify 是待标定值（ENG）—— 性格何时固化只能靠猜，见认输清单。"}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(_ROOT, "engine"))
    from association import Association

    a = Association(os.path.join(_ROOT, "state", "association.jsonl"))
    if not a.pairs:
        a = Association.derive_from_ledger(
            out_path=os.path.join(_ROOT, "state", "association.jsonl"))
    c = Character(os.path.join(_ROOT, "state", "character.json"))
    r = c.learn(a)

    print("═" * 78)
    print("  性格核：它变成了什么样的东西")
    print("═" * 78)
    print("  吃了 %d 条配对；新固化里程碑 %d 条" % (r["updated"], len(r["new_milestones"])))
    print()
    print("  ── 极性变量（每轮动，可涨可落）")
    for k, v in c.polarity.to_dict().items():
        bar = "█" * int(v * 20)
        print("     %-10s %5.2f  %s" % (k, v, bar))
    print()
    print("  ── 里程碑（固化后不退回）[E]：意向→习惯")
    if c.milestones:
        for m in c.milestones:
            print("     · %s（证据 %d 次，%s 起）" % (m.text, m.evidence, m.era))
    else:
        print("     （还没有 —— 需要某一类事重复到 %d 次）" % A_SOLIDIFY)
    print()
    print("  ── ★ 关于我自己（这是可进输出的部分）")
    for s in c.self_statements():
        print("     · %s" % s)
    print()
    print("  ── 注意到但不说（守 E5，不进输出）")
    for l in a.noticed_about_user():
        print("     · %s" % l)
    print("═" * 78)

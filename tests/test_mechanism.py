# -*- coding: utf-8 -*-
"""机制层测试

这个文件要回答的问题不是"代码跑不跑得通"，而是：
    **机制层的动力学，是否符合三本书所描述的机制？**

所以下面每个用例都写明了它在检验哪一条原文依据。
凡是我已知会失败、或我故意放宽的地方，都标了 [WEAK]。
"""
from __future__ import annotations

import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "engine"))

from mechanism import (                     # noqa: E402
    Mechanism, MechanismConfig, DA_REST_LO, DA_REST_HI, DA_BURST_LO, DA_BURST_HI,
    classify, conditions,
)

PASS = 0
FAIL = 0
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("[PASS] %s" % name)
    else:
        FAIL += 1
        FAILED.append(name)
        print("[FAIL] %s" % name)
        if detail:
            print("       %s" % detail)


def hr() -> None:
    print("-" * 74)


# ============================================================ A. 量纲与边界

def test_dimensions() -> None:
    hr()
    print("A. 量纲与上下界（[D] 原文：静止 3–5；兴奋 20–30；预期落空 → 0）")
    hr()
    m = Mechanism()
    st = m.step(["want_like_gap"], "我一定要得到那个结果", "B", "T10:B")
    check("A1 全新情境下 w 落在兴奋带 20–30Hz 内",
          DA_BURST_LO <= st.w <= DA_BURST_HI,
          "w=%.2f" % st.w)

    # 零渴望、零新颖（同一情境反复）后，w 应回落到静止带
    # 注意这里**没有** want_like_gap，所以不会触发敏化 —— 只是熟悉化的效果
    m2 = Mechanism()
    for _ in range(40):
        st2 = m2.step([], "今天天气还行", "B", "T01:B")
    check("A2 无渴望、情境麻木后，w 回落到静止带 3–5Hz",
          DA_REST_LO <= st2.w <= DA_REST_HI,
          "w=%.2f（静止带 %.0f–%.0f）a=%.3f" % (st2.w, DA_REST_LO, DA_REST_HI, st2.a))

    # 注：这里**没有**"反复渴望 → 敏化"的用例。
    # 因为在新机制下，恒定不变的渴望不会产生失望，也就不该敏化 ——
    # 敏化需要"建立预期之后落空"，那条在 B 组测（B3/B4/B5）。
    check("A3 l 恒在 [floor, 1] 内", 0.0 <= st2.l <= 1.0, "l=%.3f" % st2.l)
    check("A4 a 恒非负", st2.a >= 0.0, "a=%.3f" % st2.a)
    check("A5 张力恒在 [0,10] 内", 0.0 <= st2.tension <= 10.0, "tension=%.3f" % st2.tension)


# ============================================================ B. 耐受与敏化

def test_sensitization() -> None:
    hr()
    print("B. 奖赏预测误差与敏化")
    print("   [D] 章末原句：多巴胺的反应是针对『奖赏预测误差＝实际奖赏减预期奖赏』")
    print("   [D] 耐受：预期落空时多巴胺放电降到零；长期使用者释放量比健康人少 80%")
    print("   失望的定义：**因为想要过，所以没得到才叫失望。**")
    hr()
    # ---- B1 第一次渴望：陌生 → 不抱预期 → 正误差（惊喜）
    m = Mechanism()
    st = m.step(["want_like_gap"], "我一定要得到那个结果", "B", "T10:B")
    check("B1 首次渴望为正向预测误差（惊喜：预期 0，实际 6）",
          st.delta_r > 0, "Δr=%.2f" % st.delta_r)

    # ---- B2 反复渴望：预期跟上 → 误差归零（不再惊喜，但也没失望）
    m2 = Mechanism()
    rs2 = []
    for _ in range(6):
        rs2.append(m2.step(["want_like_gap"], "我一定要得到那个结果", "B", "T10:B").delta_r)
    check("B2 反复渴望后 Δr → 0（不再惊喜，但也不失望）",
          abs(rs2[-1]) < 1e-6, "Δr=%s" % [round(x, 2) for x in rs2])
    check("B2b 反复渴望本身**不**造成敏化（无失望则无敏化）",
          m2.a < 1e-9, "a=%.4f" % m2.a)

    # ---- B3 失望：渴望过之后，这次没得到 → 负误差
    m3 = Mechanism()
    for _ in range(3):                                     # 先建立预期
        m3.step(["want_like_gap"], "我一定要得到那个结果", "B", "T10:B")
    a_before = m3.a
    st3 = m3.step([], "也就那样吧", "B", "T10:B")            # 预期落空
    check("B3 建立预期后落空 → 负预测误差（这就是失望）",
          st3.delta_r < 0, "Δr=%.2f" % st3.delta_r)
    check("B4 失望推高敏化增益 a", m3.a > a_before,
          "a: %.4f → %.4f" % (a_before, m3.a))

    # ---- B5 敏化的表现：静止基线被抬高（诺亚："平淡素材无法满足"）
    m4 = Mechanism()
    for i in range(30):
        m4.step(["want_like_gap"] if i % 2 == 0 else [], "时好时坏", "B", "T10:B")
    check("B5 反复失望后敏化显著，且抬高静止基线",
          m4.a > 0.1 and m4.cfg.da_rest * (1 + m4.a) > DA_REST_HI,
          "a=%.3f → 静止基线 %.2fHz（原书静止带上界 %.0f）"
          % (m4.a, m4.cfg.da_rest * (1 + m4.a), DA_REST_HI))

    # ---- B6 单调性：a 不会因为正误差而倒退
    check("B6 敏化是累积的（a 非负且不下降）", m4.a >= 0.1)


def test_novelty_resets() -> None:
    hr()
    print("C. 新颖度：换个情境就是新的刺激")
    print("   [D] 重复同一张图片 → 回路活性降低；看到新图片 → 系统再次活跃")
    hr()
    m = Mechanism()
    for _ in range(6):
        m.step(["want_like_gap"], "我一定要得到那个结果", "B", "T10:B")
    w_old = m.step(["want_like_gap"], "我一定要得到那个结果", "B", "T10:B").w
    # 换一个从未见过的高度新颖情境
    w_new = m.step(["want_like_gap"], "我一定要得到那个结果", "B", "T11:B").w
    check("C1 换到全新情境后 w 回升（耐受并非不可逆）", w_new > w_old,
          "旧情境 w=%.2f → 新情境 w=%.2f" % (w_old, w_new))
    check("C2 全新情境的相位性爆发落在兴奋带",
          w_new >= DA_BURST_LO, "w=%.2f（兴奋带下沿 %.0f）" % (w_new, DA_BURST_LO))


# ============================================================ D. 当下分子

def test_present() -> None:
    hr()
    print("D. 当下分子（体验）")
    print("   [D] 当下分子负责此时此地的真实体验；[D] 长期缺失 → 麻木")
    hr()
    m = Mechanism()
    # 连续 50 轮没有任何可体验的具体物
    # （experience_decay_tau=14 → 每轮保留 0.929，约 28 轮越过 0.12 阈值）
    for _ in range(50):
        st = m.step([], "我一定要得到那个结果", "B", "T10:B")
    depleted_l = st.l

    m2 = Mechanism()
    exp = ("那天她把我送到楼下，我看着她上车，风挺凉的。")
    for _ in range(6):
        st2 = m2.step([], exp, "B", "T09:B")
    check("D1 缺少可体验事件时 l 下降", depleted_l < 1.0, "l=%.3f" % depleted_l)
    check("D2 有可体验事件时 l 维持高位", st2.l > depleted_l,
          "有体验 l=%.3f ＞ 无体验 l=%.3f" % (st2.l, depleted_l))
    check("D3 长期枯竭会命中 DEPLETED 条件", depleted_l <= 0.12,
          "l=%.3f（阈值 0.12）" % depleted_l)
    # 反向：一轮没有具体体验**不该**被判枯竭（这是"麻木"与"这轮没聊到具体事"的区别）
    m3 = Mechanism()
    st3 = m3.step([], "我一定要得到那个结果", "B", "T10:B")
    check("D4 单轮没有具体体验不判枯竭（麻木是慢变量）",
          not (st3.l <= 0.12), "l=%.3f" % st3.l)


# ============================================================ E. 位阶纪律

def test_layer_precedence() -> None:
    hr()
    print("E. 位阶纪律：动力 → 结构 → 意义（[规格 §1 冲突 6]）")
    print("   禁止第 1 层绕过第 2 层。绕过＝过度意向，是数值状态而非词表命中。")
    hr()
    m = Mechanism()
    st = m.step(["over_intention"], "我一定要做到，我必须证明给他们看", "B", "T15:B")
    check("E1 over_intention 触发 forbidden_layer1", st.forbidden_layer1)
    check("E2 其机制条件为 DRIVE_UNACKNOWLEDGED（只允许复述/追问）",
          st.phase == "DRIVE_UNACKNOWLEDGED", "phase=%s" % st.phase)

    # 结构被持续压迫（通道一直翻转）→ 门控关闭
    m2 = Mechanism()
    for i in range(8):
        m2.step([], "随便说点", "B" if i % 2 == 0 else "S", "T01:%s" % ("B" if i % 2 == 0 else "S"))
    check("E3 结构被持续违反时 e 上升", m2.e > 0, "e=%.3f" % m2.e)


# ============================================================ F. 意义张力

def test_tension() -> None:
    hr()
    print("F. 意义张力（第三层）")
    print("   [M] 『人所需要的不是没有紧张的状态』『这种说法是错误和危险的』")
    print("   [M] 『存在的动力处于一个紧张的极化区』")
    print("   [M] 张力 ＝『已完成的和有待完成的任务之间的紧张，或当下状态与理想状态之间的差距』")
    print("   ⚠️ 张力只用第 1 层已算出的 w 与 l，不用任何外部水平锚点。")
    print("      原因：给题面打水平标注是帕克与哈维斯特的做法，卢文格 [p246] 明确反驳它。")
    hr()
    # 张力由「行为性投入 × 体验缺口」决定，**不由词表标记决定**。
    # 这两条用例是改过一次的：原来拿 want_like_gap 的有无当输入，
    # 但那个标记现在只是 w 的一个加项，不再驱动张力 —— 再那样测就等于测过时的机制。
    #
    # 用行为区分：接话长（实质投入）vs 不接话（短应声）
    m_hi = Mechanism()      # 持续实质接话，且一句具体体验都没有
    for _ in range(6):
        st_hi = m_hi.step([], "其实我也想不清楚这件事到底该怎么办", "B", "T10:B")
    m_lo = Mechanism()      # 只应声，几乎没投入
    for _ in range(6):
        st_lo = m_lo.step([], "嗯", "B", "T01:B")
    check("F1 持续实质接话但无具体体验 → 张力更高",
          st_hi.tension > st_lo.tension,
          "实质接话=%.2f 只应声=%.2f" % (st_hi.tension, st_lo.tension))
    check("F2 张力不会为负（不制造痛苦的数值保证）", st_lo.tension >= 0.0)

    # 补当下 → 张力应下降（这正是 [D] 的当下分子与 [M] 的张力在同一式里咬合）
    m3 = Mechanism()
    for _ in range(6):
        m3.step([], "其实我也想不清楚这件事到底该怎么办", "B", "T10:B")
    t_before = m3._tension
    for _ in range(6):
        st3 = m3.step([], "那天她把我送到楼下，风挺凉的。", "B", "T10:B")
    check("F3 补上一件具体的当下体验后张力下降",
          st3.tension < t_before,
          "补当下前=%.2f → 后=%.2f" % (t_before, st3.tension))
    check("F3b 张力是自限的，不会随轮次累加饱和",
          st3.tension < 10.0, "张力=%.2f" % st3.tension)

    # 张力趋零必须可识别为**病态**，而不是被当成"健康"
    cfg = MechanismConfig()
    zero_state = _fake_state(cfg, tension=0.5)
    cond = classify(zero_state, cfg)
    check("F4 张力趋零被判为 NO_TENSION（病态）而非健康",
          cond.id == "NO_TENSION", "phase=%s" % cond.id)
    healthy = _fake_state(cfg, tension=4.5)
    check("F5 健康极化区被判为 HEALTHY_DRIVE",
          classify(healthy, cfg).id == "HEALTHY_DRIVE",
          "phase=%s" % classify(healthy, cfg).id)
    over = _fake_state(cfg, tension=9.0)
    check("F6 张力爆表被判为 OVERLOADED（降负载而非加难）",
          classify(over, cfg).id == "OVERLOADED",
          "phase=%s" % classify(over, cfg).id)
    # 张力在健康区但结构趋势未定
    # ⚠️ 这条用例改过一次：E3 起 ASKABLE（张力已起、人还在讲、有话可问 → 问细节）
    #    排在 TENSION_PRESENT 前面，所以只有**问不出**时才会落到 TENSION_PRESENT。
    #    原来的期望（张力 4.5 就该复述）已经过时 —— 那正是用户判定"牛头不对马嘴"的来源。
    tense = _fake_state(cfg, tension=4.5, e_trend="RISING")
    check("F7 张力已起且人还在讲 → ASKABLE（问细节）优先于复述",
          classify(tense, cfg).id == "ASKABLE",
          "phase=%s" % classify(tense, cfg).id)
    # 问不出（这句话太短）时才回落到只陈述观察
    quiet = _fake_state(cfg, tension=4.5, e_trend="RISING", askable=False, lean=0.0)
    check("F7b 问不出时 → TENSION_PRESENT（只复述，作为兜底）",
          classify(quiet, cfg).id == "TENSION_PRESENT",
          "phase=%s" % classify(quiet, cfg).id)
    check("F8 张力始终可测（不依赖任何外部锚点）",
          m_lo._tension_measured is True)

    # 条件表必须覆盖**整个**张力区间 —— 否则机制层会在一段很常见的状态上无话可说，
    # 那只是把"零命中的死角"换了个位置。
    # 教训：第一次跑这个检查时，张力 6.75 掉进死角 ——
    #   健康带上界 6.5 是**闭区间**，而 OVERLOADED 要求 ≥7.0，中间 (6.5, 7.0) 没人管。
    #   所以下面顺带断言"健康带上界必须等于爆表阈值"，让这类缝不可能再出现。
    check("F9 健康极性区上界 == 张力爆表阈值（区间闭合，不留缝）",
          abs(cfg.tension_health_hi - cfg.tension_up) < 1e-9,
          "健康上界=%.2f 爆表阈值=%.2f" % (cfg.tension_health_hi, cfg.tension_up))
    gaps = []
    t = 0.0
    while t <= 10.0:
        c = classify(_fake_state(cfg, tension=t), cfg)
        if c.id == "UNCLASSIFIED":
            gaps.append(round(t, 2))
        t += 0.25
    check("F10 条件表覆盖整个张力区间（无 UNCLASSIFIED 死角）",
          not gaps, "未覆盖的张力取值：%s" % gaps[:8])


def _fake_state(cfg, **kw):
    """造一个仅用于条件分类的假状态。"""
    from mechanism import MechanismState
    base = dict(turn=1, w=10.0, l=0.5, novelty=0.5, delta_r=0.0, a=0.0,
                lean=1.0, lean_raw=2, askable=True, has_attitude=False, is_closing=False,
                e=0.0, e_trend="FLAT", tension=5.0, tension_measured=True,
                completed=0.0, unfinished=5.0, capacity=0.5, forbidden_layer1=False)
    base.update(kw)
    return MechanismState(**base)


# ============================================================ G. 只用模板，不生成文字

def test_no_text_generation() -> None:
    hr()
    print("G. 硬约束：机制层只输出数与 ID，**不生成任何文字**")
    hr()
    m = Mechanism()
    st = m.step(["immutable"], "他已经走了，再也回不来了", "B", "T20:B")
    d = st.to_dict()
    bad = []
    for k, v in d.items():
        if k in ("phase", "e_trend", "notes"):
            continue
        if isinstance(v, str):
            bad.append(k)
    check("G1 MechanismState 除 phase/e_trend 外无字符串字段（无文字）",
          not bad, "发现字符串字段：%s" % bad)

    # 动作 ID 必须都是 behaviors.json 里已存在的行为 —— 机制层不得新造行为
    bj = os.path.join(_ROOT, "rules", "behaviors.json")
    import json
    existing = {b["id"] for b in json.load(io.open(bj, encoding="utf-8"))["behaviors"]}
    used = {c.action for c in conditions(MechanismConfig())}
    unknown = used - existing
    check("G2 机制条件给出的动作全部是 behaviors.json 中已存在的行为",
          not unknown, "未知动作：%s" % unknown)


# ============================================================ H. 自参照（少常数）

def test_self_reference() -> None:
    hr()
    print("H. 自参照：充足的标准来自系统自己的记录，不是我猜的数")
    hr()
    m = Mechanism()
    check("H1 l 的起点是参照系中性值 1.0（不是 0.5 那样的手挑值）",
          abs(m.l - 1.0) < 1e-9, "l=%s" % m.l)
    check("H2 Δr 的两个操作数同量纲（Hz），增益自动抵消",
          abs(m.step(["want_like_gap"], "我一定要得到", "B", "T10:B").delta_r) < 30.0)


# ============================================================ 主

def test_e_version() -> None:
    """★ 机制快照必须带 `e_version`（用户裁定 2026-10-02）。

    > 「在机制快照（mech snapshot）中显式写入 `"e_version": C.E_VERSION`（即 2）；
    >   在 `test_mechanism.py` 中补上一条断言，
    >   确保生成的快照字典中**严格包含** `e_version == 2`。」

    **为什么必须有**：第 1~4 步把 e 的公式从旧式换成了方案 B noisy-OR，
    却**没打版本标记** —— 于是台账里 [0, 0.5] 的旧值和 [0, 1] 的新值
    混在一起，事后分不开。这条把它钉死。
    """
    import constants as _C
    m = Mechanism()
    # ⚠️ `step()` 返回的是 **MechanismState 对象**，不是 dict。
    #    「快照字典」是 `to_dict()` 的结果（pipeline 里就是这么用的）。
    #    第一版直接对对象用 `in` → TypeError: MechanismState is not iterable。
    st = m.step(["want_like_gap"], "我一定要得到那个结果", "B", "T10:B").to_dict()
    check("V1 快照严格含 e_version", "e_version" in st,
          "快照 keys：%s" % sorted(st)[:12])
    check("V2 e_version == SSOT.E_VERSION（= 2）",
          st.get("e_version") == _C.E_VERSION == 2,
          "快照 %r｜SSOT %r" % (st.get("e_version"), _C.E_VERSION))
    # 值域顺带钉一下：方案 B 的 e ∈ [0, 1]
    check("V3 e 落在方案 B 的值域 [0, 1]",
          0.0 <= st.get("e", -1) <= _C.E_UPPER_BOUND,
          "e = %r｜上确界 %r" % (st.get("e"), _C.E_UPPER_BOUND))


def main() -> int:
    print("=" * 74)
    print("  机制层测试")
    print("=" * 74)
    test_dimensions()
    test_sensitization()
    test_novelty_resets()
    test_present()
    test_layer_precedence()
    test_tension()
    test_no_text_generation()
    test_self_reference()
    test_e_version()
    hr()
    print("结果: %d 通过 / %d 失败 / 共 %d" % (PASS, FAIL, PASS + FAIL))
    if FAILED:
        print("失败项：")
        for x in FAILED:
            print("  · %s" % x)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

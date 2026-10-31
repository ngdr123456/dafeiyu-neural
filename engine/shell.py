# -*- coding: utf-8 -*-
"""交互式对话外壳

设计约束（都来自已冻结的规格，不是界面偏好）：
  · DISCLOSE_GOAL=OFF  → 默认**不显示**系统对用户的任何判定；要看得显式用 /why
  · 只组装不生成        → 系统的每句话都来自 rules/behaviors.json 的模板
  · 最低限度推理        → /why 展示的是"命中了哪些字面片段"，不是"你是什么样的人"
  · 反事实不可删        → /why 会显示该轮的反事实条目，包括系统自己的错

用法：
    cd C:\\Users\\22082\\Desktop\\DEPSK\\books\\ego-dialogue
    python engine\\shell.py                # 继续使用 state/ledger.jsonl
    python engine\\shell.py --new          # 开新台账
    python engine\\shell.py --debug        # 默认显示内部判定（调试用）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包成 exe 后 `__file__` 指向解包出的临时目录 —— 于是 rules/corpus 找不到，
# 而且**台账会写进临时目录、退出就丢**。所以允许用 EGO_ROOT 指定项目根，
# 由启动器（exe）在导入任何引擎模块之前设置。
# 不设 EGO_ROOT 时行为与从前完全一致（源码运行时就是这个分支）。
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path.insert(0, _HERE)

from pipeline import Pipeline        # noqa: E402
from gear import GearConfig          # noqa: E402
from topics import TopicManager      # noqa: E402

W = 74

# 哪些机制层常数的数值/上下界**确实来自原书**（区别于我挑的工程占位值）。
# 这个名单是 /mech 诚实声明的基础，改它必须同时改 mechanism.py 里的注释。
_SOURCED = {
    "da_rest", "da_ceiling", "experience_floor",
    "sensitization_gain", "error_high", "habituation_k",
    "tension_up", "tension_low",
}

HELP = """
命令
  /why            显示上一轮的内部判定（标记、区间、通道、S、反事实）
  /mech           显示底层机制状态（想要/喜欢/预测误差/敏化/张力，全部带出处）
  /status         当前状态快照（世代、轮数、档位、S 列表）
  /report [路径]    导出完整报告 JSON
  /audit          立刻执行一次自检（[E] 手册修订）
  /era TAG 理由    开启新时代（只追加分界记录，不删历史）
  /topic ID       跳转到指定话题（如 /topic T23）
  /ask            重新显示当前话题题面
  /list           列出全部 36 个话题的编号与题面
  /help           显示本帮助
  /quit           退出（会自动保存）
"""


def hr(ch: str = "─") -> None:
    print(ch * W)


def wrap(text: str, indent: str = "  ") -> None:
    for para in text.split("\n"):
        if not para.strip():
            print()
            continue
        print(textwrap.fill(para, width=W - len(indent), initial_indent=indent,
                            subsequent_indent=indent))


class Shell:
    def __init__(self, ledger_path: str, debug: bool = False, use_api: bool = False,
                 use_render: bool = False, use_think: bool = False,
                 use_cognition: bool | None = None):
        # ★ 2026-10-29（Gemini 第 ① 步批准）：交互入口也**默认跟 use_api 走**。
        #
        #   ⇒ 真实对话（`use_api=True`）时，「意识海 + 去助手化」是默认形态；
        #     `--offline` / demo（`use_api=False`）时不抽取（调不通，多付也没用）。
        #   ⇒ 显式传 True/False 时以参数为准。
        _cog = bool(use_api) if use_cognition is None else bool(use_cognition)
        self.p = Pipeline(ledger_path=ledger_path, config=GearConfig(),
                          character_path=os.path.join(os.path.dirname(ledger_path), "character.json"),
                          auto_audit=True, use_api=use_api, use_render=use_render,
                          use_think=use_think, use_cognition=_cog)
        self.debug = debug
        self.topic_id: str | None = None
        self.last = None
        self.topics = {t["id"]: t for t in self.p.markers.topics["topics"]}
        # 话题服务于人，不是人服务于话题
        self.tm = TopicManager(self.p.markers.topics["topics"])
        self.tm.st.current = self.p.next_topic()
        self.topic_id = self.tm.st.current

    # ------------------------------------------------------------ 输出

    def banner(self) -> None:
        print()
        hr("═")
        # ⚠️ 标题随开关变。原先写死"无基础模型生成"，
        #    开了渲染层之后那是谎话 —— 措辞确实由模型说了。
        #    意思仍然不由模型决定，但那句话不能拿来否认措辞的来源。
        #    ★ 再到大脑模式（--think）：连"说什么"都由模型决定，
        #      所以标题必须再改一次。**界面不许说一件不成立的事。**
        if self.p.thinker is not None:
            print("  自我的发展 · 对话（系统决定该想什么，模型自己想说成什么）")
        elif self.p.renderer is not None:
            print("  自我的发展 · 对话（决定由逻辑体系做，措辞由模型说）")
        else:
            print("  自我的发展 · 对话（纯模板组装，无模型生成文字）")
        hr("═")
        wrap("规则：你说，系统只用你自己说过的话回给你。它不会评价你，不会诊断你，"
             "不会告诉你应该做什么。")
        wrap("想看它内部怎么判的：输入 /why。想看它长成什么样：/character。"
             "想退出：/quit。")
        wrap("[M] 弗兰克尔：治疗师好比眼科专家而不是画家——他只是让你自己去看清。")
        if self.p.thinker is not None:
            wrap("[大脑模式] 已开（乙案）。**系统决定它该想什么** —— 该注意你话里的哪些"
                 "观念、它自己此刻的状态（机制层三层方程 + 极性变量）、"
                 "它长成的样子（里程碑）、以及纪律。**说什么由模型决定。**")
            wrap("闸门只查禁止项（建议／评判／贴标签／替你补内容／术语泄漏／伪造引文），"
                 "不过就退回模板。可追溯性降到「简报」一级：它当时拿到什么，台账里能查。")
        elif self.p.renderer is not None:
            wrap("[渲染层] 已开。**要表达的意思**由理论∩机制状态∩性格决定，"
                 "不由模型决定；模型只负责把那句话说成人话。"
                 "三道闸门任一不过会自动退回模板 —— 开渲染后，"
                 "**输出的措辞不再逐字可追溯**（只能追溯到「意思」一级）。")
        if self.p.api_enabled:
            wrap("[理解层] 已接入 API：把语言映射成结构标记，不参与决定说什么。")
        else:
            wrap("[理解层] 未接 API，仅用规则判定。加 --api 可启用双评定人。")
        hr()

    def ask(self) -> None:
        t = self.topics.get(self.topic_id or "")
        if not t:
            self.topic_id = self.p.next_topic()
            t = self.topics[self.topic_id]
        print()
        # ⚠️ 原先印的是 `【T01】题面` —— **编号在最前面**，于是用户满屏看到的都是
        #    「【T01】当我想做一件事……」，得到的印象是"它一直在说 T01"。
        #    （实测：用户截图问「它每次都会带一个 T01，那到底是干嘛的」。）
        #    编号是内部标识，给调试用；给用户看的应该只有题面。
        if self.debug:
            print("  【%s】%s" % (t["id"], t["stem"]))
        else:
            print("  %s" % t["stem"])
        print()

    # ------------------------------------------------------------ 机制展示

    def show_why(self) -> None:
        if not self.last:
            print("  （还没有可展示的一轮）")
            return
        r = self.last
        entry = self.p.ledger.entries[-1]
        hr()
        print("  上一轮内部判定（仅在你要求时显示）")
        hr()
        print("  命中的字面片段：")
        if entry.marker_evidence:
            for mid, ev in entry.marker_evidence.items():
                print("    · %-18s ← %s" % (mid, "、".join(ev[:4])))
        else:
            print("    · （无命中 → 按【废纸篓类别】记于遵奉水平 [E]）")
        print()
        print("  区间：[%s]   方向：%s   关系：%s"
              % (" / ".join(r.band), r.direction, r.relation))
        print("  通道：%s   水平：%s   行为：%s"
              % (r.channel, r.level, r.behavior))
        print("  意图：%s（裁决：%s）" % (r.intent, r.api_intent or "—"))
        if r.mech_phase:
            print("  机制条件：%s → 建议动作 %s" % (r.mech_phase, r.mech_action))
        if r.agreement is not None:
            print("  双评定人一致度：%.2f" % r.agreement)
            if r.only_rule or r.only_api:
                print("    只有规则引擎判出：%s" % (r.only_rule or "无"))
                print("    只有 API  判出：%s" % (r.only_api or "无"))
        elif self.p.api_enabled:
            print("  双评定人：API 本轮未返回（已降级为单评定人）")
        print("  置信度：%.2f   冲突：%s" % (entry.confidence, "是" if entry.conflict else "否"))
        print("  使用规则：%s" % " → ".join(entry.rule_ids))
        if r.notes:
            print()
            print("  机制提示：")
            for n in r.notes:
                print("    · %s" % n)
        print()
        print("  本轮反事实（[M] 绝对命令，不可删除）：")
        print("    · %s" % entry.counterfactual)
        hr()
        wrap("注意：上面全是【字面匹配】的结果，不是对你这个人的判断。"
             "[E]：『我们试图在最低限度的推理水平上陈述观察。』")
        hr()

    def show_mech(self) -> None:
        """显示底层机制状态。

        这一屏是"底层思维系统"的直接呈现：全部是数，每个数都带原书出处。
        它不是对你的判断 —— 它描述的是**这套机制自己的状态**。
        """
        snap = self.p.mech.snapshot()
        from mechanism import conditions

        def has(kw: str) -> str:
            return "有据" if kw in _SOURCED else "待标定"

        hr()
        print("  工程代理状态（非生理测量、非主观体验，也不是对你的判断）")
        hr()
        cfg = self.p.mech.cfg
        print("  ── 第 1 层　动力（多巴胺）")
        print("     动力代理 w      = %6.3f      [借用原书标度，不是测得的Hz]" % snap["w"])
        print("     偏好代理 l      = %6.3f      [输入特征代理，未证明主体有体验]" % snap["l"])
        print("     增益代理 a      = %6.3f      [输入信号变化，非实测失望；%s]" % (snap["a"], has("sensitization_gain")))
        print("     静止基线        = %6.3f Hz   [= %.1f × (1+a)，%s]"
              % (cfg.da_rest * (1 + snap["a"]), cfg.da_rest, has("da_rest")))
        print("     情境记录        = %d 个不同情境，最多重复 %d 次"
              % (snap["track"]["distinct_keys"], snap["track"]["max_repeat"]))
        print()
        print("  ── 第 2 层　结构（平衡化）")
        print("     通道压力 e      = %6.3f      [通道稳定性；不是语义失配；%s]"
              % (snap["e"], has("error_high")))
        print()
        print("  ── 第 3 层　意义（张力）")
        if snap["level_anchor"] is None:
            print("     张力            = 未测（还没拿到能力锚点，不敢报 0）")
        else:
            print("     张力            = %6.3f      [健康极化区 %.1f–%.1f]"
                  % (snap["tension"] or 0.0, cfg.tension_health_lo, cfg.tension_health_hi))
            print("     能力锚点        = %6.3f      [来自 L3 观测的水平序号 0–9]"
                  % snap["level_anchor"])
        print("     未完成 / 已完成 = %.3f / %.3f" % (snap["unfinished"], snap["completed"]))
        print("     应对能力        = %6.3f      [体验充足度 × 技能 × 结构可用度]"
              % snap["capacity"])
        print()
        print("  ── 机制条件表（先命中者胜）")
        for c in conditions(cfg):
            mark = "← 当前" if False else ""
            print("     %-22s → %-16s %s" % (c.id, c.action, c.label))
        print()
        print("  诚实声明：")
        print("    · 标『待标定』的常数是工程占位值，没有数据支撑 —— 该行为不可信。")
        print("    · 『有据』只表示数值或上下界来自原书，不表示这个模型被验证过。")
        print("    · 机制层只做数学运算；它对你说出的每句话仍来自 behaviors.json 的模板。")
        hr()

    def show_character(self) -> None:
        """显示它**变成了什么样**。

        这一屏是性格层的落点，也是「从对方的反应里学会描述自己」的直接呈现。
        分两栏，**界线是硬的**：
          · 关于我自己 —— 可以进输出
          · 注意到但不说 —— 只用于调整它自己，说出来就违反 E5
        """
        import sys as _sys
        _sys.path.insert(0, _HERE)
        from association import Association
        from character import Character

        a = Association.derive_from_ledger(
            out_path=os.path.join(_ROOT, "state", "association.jsonl"))
        c = Character(os.path.join(_ROOT, "state", "character.json"))
        # ★ 极性变量是"当下的状态"，所以必须把**最近一轮的机制快照**喂进去。
        #   旧版没有这个口子，于是只能拿累积占比冒充状态 —— 根子在这里。
        #   读不到就如实说读不到（learn 会标注），不假装有。
        _last_mech = None
        for _e in reversed(self.p.ledger.effective_entries):
            if _e.mech:
                _last_mech = _e.mech
                break
        r = c.learn(a, mech=_last_mech)
        v = a.self_view()

        hr()
        print("  它变成了什么样（性格层）")
        hr()
        print("  依据 [Mead]：当我们学会了用别人的观点来描述我们自己时，心理的意识就产生了。")
        print()
        # ★ 分母必须先报（实测缺陷：原先只报"配对 59 条"，读的人无从知道
        #   那个 59 与台账 95 行的差在哪 —— 4 条 `/quit` 命令残留、
        #   30 条 E1–E3 老条目没有原话字段，全都糊在一个数里）。
        dn = self.p.ledger.denominators()
        print("  ── 先说口径（这些数各自的分母不同，不可混看）")
        print("     台账行数            %d" % dn["rows"])
        print("     其中作废（不进统计）  %d   ← /命令残留等，只标注不删" % dn["void"])
        print("     有效轮次            %d" % dn["effective"])
        print("     其中有原话          %d   ← 关联/文本类统计只能用这些" % dn["with_text"])
        print("     无原话但有效        %d   ← E4 之前没存原话；该进行为统计" % dn["no_text_but_valid"])
        print("     近零内容轮          %d   ← 如「?」「嗯。」；**不排除**，单列出来" % dn["low_content"])
        print()
        print("  ── 从对方的反应里看到的（配对 %d 条）" % v.get("n", 0))
        for l in v.get("lines", []):
            wrap("· %s" % l, "     ")
        print()
        print("  ── 极性变量（[E] 极性：当下的状态，每轮动、可涨可落）")
        print("     读自：%s" % c.state_read_from())
        caveats = c.polarity_caveats()
        from character import POLARITY_NAME, POLARITY_SOURCE
        for k, val in c.polarity.to_dict().items():
            print("     %-12s %5.2f  %s" % (POLARITY_NAME.get(k, k), val, "█" * int(val * 20)))
            print("                %s" % POLARITY_SOURCE.get(k, ""))
            if k in caveats:
                print("                ⚠️ %s" % caveats[k])
        print()
        print("  ── 行为分布（累积占比）★ **这不是状态**")
        print("     它是「我一向做过什么」的历史占比。分母只长大 → 会随聊天变长单向漂移；")
        print("     同一个系统只聊 5 轮与聊满 55 轮，同一个数能差几倍。只作追溯用。")
        for k, v in (c.polarity_basis() or {}).items():
            if isinstance(v, tuple) and len(v) == 3:
                num, den, formula = v
                print("     %-14s %d/%d = %.0f%%   %s"
                      % (k, num, den, 100.0 * num / den if den else 0, formula))
            else:
                print("     %s" % v)
        _dens = sorted({v[1] for v in (c.polarity_basis() or {}).values()
                        if isinstance(v, tuple) and len(v) == 3})
        if len(_dens) > 1:
            print("     ⚠️ 这几个占比用了 %d 种不同分母（%s）—— 彼此**不可比**，"
                  "更不该与上面的极性变量比。" % (len(_dens),
                                              "／".join(str(x) for x in _dens)))
            print("        实测它们随聊天变长单向漂移，且方向不一定向下：")
            print("        同一批数据，换个统计口径能让其中一项在 0.13 与 0.84 之间来回跳。")
            print("        具体数值看审计：python tests\\audit_polarity.py")
        print()
        print("  ── 里程碑（固化后不退回）[E] 意向→习惯")
        if c.milestones:
            for m in c.milestones:
                cur = getattr(m, "current", m.evidence)
                # ★ 证据数是**历史最高水位**（不退回，只变厚）。若当前值更低，
                #   必须一起显示 —— 否则"不退回"就变成了"不许更正"：
                #   实测修掉跨会话 bug 后，「我换的话题」真实次数 20→9，
                #   而界面仍显示 20，读的人会拿一个作废的数字说服自己。
                if cur < m.evidence:
                    print("     · %s（证据 **当前 %d 次**，历史最高 %d 次，%s 起）"
                          % (m.text, cur, m.evidence, m.era))
                else:
                    print("     · %s（证据 %d 次，%s 起）" % (m.text, m.evidence, m.era))
                b = getattr(m, "basis", None)
                if b:
                    print("         依据：我做这个动作 %d 次；有反应的 %d 次里"
                          "接得住 %d、停在那儿 %d（%.0f%%）；基线 %.0f%%"
                          % (b.get("acted", 0), b.get("n", 0), b.get("continue", 0),
                             b.get("stop", 0), 100 * (b.get("share") or 0),
                             100 * (b.get("baseline_share") or 0)))
        else:
            print("     （还没有 —— 需要某一类事重复到 %d 次）" % c.A_SOLIDIFY if hasattr(c, "A_SOLIDIFY")
                  else "     （还没有）")
        # ★ 未固化的也要列出来：只报成功的那几条，读的人看不到判据在哪里切的，
        #   也就无法质疑阈值 —— 而阈值是本层唯一靠猜的数（A_SOLIDIFY）。
        det = c.milestone_details()
        pend = [d for d in det if d[1] != "固化"]
        if pend:
            print("     ── 未固化的（一并列出，判据才可质疑）")
            for kind, _st, why, _b in pend:
                print("        · %-10s %s" % (kind, why))
        if r.get("new_milestones"):
            print("     ★ 本次新固化 %d 条" % len(r["new_milestones"]))
        print()
        print("  ── ★ 关于我自己（这部分可以进输出）")
        for s in c.self_statements():
            wrap("· %s" % s, "     ")
        print()
        print("  ── 注意到但不说（守 E5，**绝不进输出**）")
        for l in a.noticed_about_user():
            wrap("· %s" % l, "     ")
        print()
        print("  诚实声明：")
        print("    · 固化阈值 A=%d 是**待标定值**，没有数据支撑。" % c.A_SOLIDIFY
              if hasattr(c, "A_SOLIDIFY") else "    · 固化阈值为待标定值。")
        print("    · 判据是**条件关联**：我做这个动作之后、他接着怎么样（双向都算）。")
        print("      基准线也一并给出 —— 没有基准，'接得住六成'这种数字毫无意义。")
        print("    · 但**动作清单（ACTION_PHRASE）仍然是我写的**，不是长出来的 ——")
        print("      它只能从这份清单里固化。这一条没有变，也不能假装它变了。")
        print("    · 反面证据占比高时**不许下断言**，只给复合陈述")
        print("      （[E] 复合反应：证据冲突时描述冲突，不挑一个）。")
        print("    · **会话结束（NO_REPLY）与调度换题（TOPIC_MOVED）两边都不算** ——")
        print("      它们不是他对我的反应。实测：55 对里只有 9 对有真正的反应，")
        print("      其余 31 对是会话结束、15 对是调度换题。")
        print("    · **性格层现在会影响行为**（E5 开启），但只往一个方向：")
        print("      三条规则 —— 耐心低且连着做同一动作／结构压力高时不下断言／")
        print("      里程碑说这个动作多半停在那儿 —— 触发时把动作**降一档更保守**。")
        print("      实测穷举 2304 个组合：**没有任何一次向左移动**，")
        print("      immutable 在场时结果全部在 E1 允许集内（跑 tests\\audit_character_influence.py）。")
        print("    · 为什么只许更保守：讨好的失败模式必然是『做更能留住对方的事』，")
        print("      而那需要向左走 —— 结构上做不到。这是护栏，不是自觉。")
        print("    · **刻意不用 wanting**：它的来源含『他还在说』，拿它决定行为")
        print("      等于按用户说得多不多调整自己 —— 那正是 Baldwin 警告的讨好路径。")
        print("    · ⚠️ 但**这批数据还没触发过它**（耐心 0.91、结构压力 0.43、")
        print("      唯一那条里程碑是复合式）。所以只能说它接好了，")
        print("      **不能说已验证它在真实对话里有效**。")
        hr()

    def show_status(self) -> None:
        snap = self.p.gear.snapshot()
        st = self.p.state.snapshot()
        hr()
        print("  状态")
        hr()
        print("  世代：%s   台账条目：%d" % (self.p.ledger.era, self.p.ledger.turns()))
        if self.p.ledger.boundaries():
            print("  历史世代分界：")
            for b in self.p.ledger.boundaries():
                print("    · %s → %s（%s）" % (b.get("previous_era"), b["era"], b["reason"]))
        print("  当前档位：%s（停留 %d 轮）" % (snap["gear"]["level"], snap["gear"]["dwell_turns"]))
        print("  区间中段：%s   调节维度：%s"
              % (st["peak"], st["adjustment_mean"] if st["adjustment_mean"] is not None else "未测"))
        # 证据覆盖率：说清"这个区间有多少是观察到的，多少是判不出来的"。
        # 实测真人输入约 2/3 轮次零标记命中（tests/probe_topic_answers.py），
        # 所以这个数必须显式给出，否则区间看起来比实际更有信息量。
        cov = st.get("evidence_coverage")
        if cov is not None:
            print("  证据覆盖率：%.0f%%（%d 轮中 %d 轮判不出水平 → 不计入权重）"
                  % (cov * 100, st["turns"], st["unclassifiable"]))
            if cov < 0.5 and st["turns"] >= 4:
                print("    ⚠️ 过半轮次没有任何水平证据：此时的区间**信息量很低**，"
                      "不应被当成结论。")
        print("  当前话题：%s" % (self.topic_id or "—"))
        pm = self.tm.priority_map()
        brought = [r for r in pm["rows"] if r["user_brought"] > 0]
        if brought:
            print("  你自己带进来的主题（R3：以此为准，不以系统问过什么为准）：")
            for r in brought:
                print("    · %-12s 你带进来 %d 次 ｜系统问过 %d 次"
                      % (r["label"], r["user_brought"], r["system_asked"]))
        missed = [r for r in pm["rows"] if r["user_brought"] > r["system_asked"]]
        if missed:
            print("  系统还没跟上的主题：%s" % "、".join(r["label"] for r in missed))
        print("  S 常量：%d（active %d / decayed %d）"
              % (snap["S_count"], snap["S_active"], snap["S_decayed"]))
        for s in snap["S"]:
            print("    · %s 键=%s 行动水平=%s 命中=%d 疲劳=%.3f 状态=%s"
                  % (s["sid"], s["key"], s["action_level"], s["hits"], s["fatigue"], s["status"]))
        if snap["pending"]:
            print("  待固化（未达阈值 A）：%s" % snap["pending"])
        print()
        print("  诚实声明：")
        for n in snap["honest_note"]:
            print("    · %s" % n)
        hr()

    def show_audit(self) -> None:
        a = self.p.ledger.self_audit([m["id"] for m in self.p.markers.rules["markers"]])
        hr()
        print("  自检（[E] 手册修订）")
        hr()
        print("  轮数：%d   数据充足：%s（门槛 %d）"
              % (a["turns"], "是" if a["data_sufficient"] else "否", a["min_turns_for_deletion"]))
        print("  世代计数：%s" % a["era_counts"])
        print("  标记频率：%s" % (a["marker_frequency"] or "（无）"))
        if a["cross_era_drift"]:
            print("  跨世代漂移：%s" % json.dumps(a["cross_era_drift"], ensure_ascii=False))
        print()
        for s in a["_actions_suggested"]:
            wrap("· " + s, indent="    ")
        hr()

    def show_list(self) -> None:
        hr()
        for tid, t in self.topics.items():
            mark = "★不可改变" if t.get("immutable") else ""
            print("  %s  %s %s" % (tid, t["stem"], mark))
        hr()

    def report(self, path: str | None) -> None:
        rep = self.p.report()
        rep["exported_at"] = datetime.now().isoformat(timespec="seconds")
        out = path or os.path.join(_ROOT, "state", "report_%s.json"
                                   % datetime.now().strftime("%Y%m%d_%H%M%S"))
        with open(out, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        print("  已导出：%s" % out)

    # ------------------------------------------------------------ 主循环

    def run(self) -> None:
        self.banner()
        prog = os.path.join(_ROOT, "state", "topic_progress.json")
        if self.tm.load_progress(prog):
            # 恢复上次的话题进度。**这是实测抓出的 bug 的修法**：
            # 原先这里算出了 last_topic 却没用它，而是无条件调 next_topic()，
            # 于是每次重启话题就重置一次，已经答过的题又出现。
            # 实测：用户答了 T02 的题（答得完整、就在题上），重启后 T02 又出现了。
            self.topic_id = self.tm.st.current
            print()
            wrap("台账已有 %d 条记录（世代 %s）。继续。上次停在：[%s]"
                 % (self.p.ledger.turns(), self.p.ledger.era, self.topic_id))
            wrap("（想看它长成什么样：/character　退出：/quit）")
        elif self.p.ledger.turns() == 0:
            self.topic_id = self.p.next_topic()
            self.tm.st.current = self.topic_id
        else:
            # 有台账但没有进度文件（第一次启用持久化）→ 按台账里最后的话题接着来
            last_topic = self.p.ledger.entries[-1].topic_id
            self.tm.st.current = last_topic if last_topic in self.topics \
                else self.p.next_topic()
            self.topic_id = self.tm.st.current
            print()
            wrap("台账已有 %d 条记录（世代 %s）。继续。"
                 % (self.p.ledger.turns(), self.p.ledger.era))

        # ★ 把"当前这一道"也记进 visited。
        #
        # 实测抓到的最后一处：启动时设的 current 从未入册，于是
        # `next_unvisited()` 把它也算成"没碰过的" → 答完它之后又给回它自己。
        # 实测复现：第3次答 T02 → 下一题 T03；第4次答 T03 → 下一题**还是 T03**。
        #
        # `visited` 的含义是「已经用过的」，而"正在问的"当然已经用过了。
        if self.topic_id and self.topic_id not in self.tm.st.visited:
            self.tm.st.visited.append(self.topic_id)
        self.tm.save_progress(prog)

        self.ask()
        # ★ 2026-10-30（Gemini 拍板）：真人交互里**没有外层的 `Trainer._regrow()`**，
        #   所以 `boldness` 靠 `settle_encounter()` 单轮更新，而**里程碑文字**
        #   要在这里补刷一次（每 6 轮一次由 `pipeline.turn()` 负责，退出时再补一次）。
        _turns_before = len(self.p.ledger.effective_entries)
        try:
            while True:
                try:
                    raw = input("  > ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not raw:
                    continue

                # ★ 去掉看不见的字符，再做命令判断。
                #
                # 实测的真 bug：台账里出现了这样的条目 ——
                #     [T01] REFLECT   ﻿/quit
                # 那个 `/quit` 前面有一个 **U+FEFF（BOM／零宽不换行空格）**，是粘贴时带进来的。
                # 后果：`raw.startswith("/")` 判不出来（字符串开头是 U+FEFF 不是 `/`），
                # 于是 **`/quit`、`/why`、`/character` 这些命令被当成用户说的话送进了管道**。
                # 它复述了「/quit」、把当前话题记成了 T01，并且用户无法退出。
                #
                # 修法：剥掉所有零宽／格式类字符再判。它们是**不可见**的，
                # 所以用户完全不知道自己输入了什么，这类错误必须由代码兜住。
                raw = raw.strip().lstrip("\ufeff\u200b\u200c\u200d\u2060\ufffd").strip()
                if not raw:
                    continue

                if raw.startswith("/"):
                    if self._command(raw):
                        break
                    continue

                # 正常一轮
                from input_provenance import digest
                self.last = self.p.turn(raw, self.topic_id, input_origin={
                    "schema": 1, "kind": "interactive_input", "input_sha256": digest(raw),
                    "topic_id": self.topic_id, "independent_human_input_verified": False})
                print()
                for line in self.last.output.split("\n"):
                    print("  %s" % line)
                if self.debug:
                    print()
                    self.show_why()
                # 话题决策：跟随用户／保留当前／推进（见 engine/topics.py 的 R1–R3）
                d = self.tm.decide(raw, self.last.intent)
                self.tm.mark_asked(d["topic_id"])
                self.topic_id = d["topic_id"]
                # ⚠️ 这一行**只在 --debug 下显示**。
                #    它原先在 HOLD／FOLLOW_USER 时无条件打印，于是一整屏都是
                #    〔话题：本轮未答到题上 → 保留当前话题〕——
                #    那是**系统对用户的判定**，而规格里明写着：
                #      「默认不显示系统对你的任何判定（DISCLOSE_GOAL=OFF）。
                #        要看，得你自己打 /why 去要。」
                #    我违反了自己定的规格。这是实测（用户截图）抓出来的。
                if self.debug:
                    print()
                    print("  〔话题：%s〕" % d["reason"])
                # ★ 每轮都存进度 —— 否则"答到哪了"只在这一次运行里活着（见 run() 里的说明）
                self.tm.save_progress(os.path.join(_ROOT, "state", "topic_progress.json"))
                self.ask()

        finally:
            # ★ 2026-10-30：退出时若本场新增轮数 > 0，补刷一次里程碑。
            try:
                if len(self.p.ledger.effective_entries) > _turns_before:
                    self.p._refresh_milestones()
            except Exception:                                  # noqa: BLE001
                pass
        print()
        hr()
        wrap("已保存 %d 条台账记录（世代 %s）。" % (self.p.ledger.turns(), self.p.ledger.era))
        wrap("[M]：曾经存在是最为确定的一种存在——所有条目都会保留，包括系统判错的那些。")
        hr()

    def _command(self, raw: str) -> bool:
        """返回 True 表示退出。"""
        parts = raw.split(maxsplit=2)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        rest = parts[2] if len(parts) > 2 else ""

        if cmd in ("/quit", "/exit", "/q"):
            return True
        if cmd == "/help":
            print(HELP)
        elif cmd == "/why":
            self.show_why()
        elif cmd == "/status":
            self.show_status()
        elif cmd == "/audit":
            self.show_audit()
        elif cmd == "/list":
            self.show_list()
        elif cmd == "/ask":
            self.ask()
        elif cmd == "/mech":
            self.show_mech()
        elif cmd == "/character":
            self.show_character()
        elif cmd == "/report":
            self.report(arg or None)
        elif cmd == "/topic":
            if arg in self.topics:
                self.topic_id = arg
                self.ask()
            else:
                print("  未知话题编号。用 /list 查看。")
        elif cmd == "/era":
            if not arg or not rest:
                print("  用法：/era TAG 理由（理由不可省略）")
            else:
                rec = self.p.ledger.new_era(arg, rest)
                print("  已开启世代 %s（前一代 %s，此前 %d 条记录原样保留）"
                      % (rec["era"], rec["previous_era"], rec["after_turn"]))
                wrap("[E] 判据一变，手册版本随之改变——原书的手册有三代形态。分界只追加，不删历史。")
        else:
            print("  未知命令。输入 /help 查看。")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="自我的发展 · 对话外壳")
    ap.add_argument("--new", action="store_true", help="开新台账")
    ap.add_argument("--debug", action="store_true", help="默认显示内部判定")
    ap.add_argument("--api", action="store_true",
                    help="启用 API 理解层（双评定人）。API 只做结构映射，不参与回应文字。")
    ap.add_argument("--render", action="store_true",
                    help="启用渲染层：把「要表达的意思」交给模型说成人话。"
                         "三道闸门任一不过会自动退回模板。"
                         "⚠️ 开启后输出的措辞不再逐字可追溯（只能追溯到「意思」一级）。")
    ap.add_argument("--think", action="store_true",
                    help="★ 启用**思考层（乙案·大脑模式）**：模型当大脑，"
                         "系统决定它该想什么（该注意的观念／自己此刻的状态／"
                         "自己长成的样子／纪律）。说什么由模型定。"
                         "闸门只查**禁止项**（E3 建议与评判／E4 标签／E5 补内容／"
                         "术语泄漏／伪造引文），不查「有没有添加东西」——"
                         "因为这一层本来就要它自己想出话。默认关闭。")
    ap.add_argument("--ledger", default=None, help="台账路径")
    ap.add_argument("--profile", choices=("trained", "legacy"), default="trained",
                    help="默认使用训练台的身份和规则；legacy 使用根目录历史身份")
    args = ap.parse_args()

    from runtime_profile import paths
    profile = paths(_ROOT, args.profile, args.ledger)
    ledger = profile["ledger"]
    print("使用身份：%s｜记忆目录：%s" % (profile["profile"], profile["memory_directory"]))
    if args.new and os.path.exists(ledger):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.rename(ledger, ledger + ".bak" + stamp)
        print("旧台账已备份为 %s.bak%s" % (ledger, stamp))

    Shell(ledger, debug=args.debug, use_api=args.api,
          use_render=args.render, use_think=args.think).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

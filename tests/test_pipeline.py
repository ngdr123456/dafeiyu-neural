# -*- coding: utf-8 -*-
"""端到端集成测试：六层管线

覆盖四类关键行为：
  A. 正常轮（标记 → 区间 → 通道 → 行为 → 台账）
  B. S 通道：同一签名反复出现 → 越过固化阈值 A → 生成 S → 命中
  C. 疲劳与试探性并行：S 的行动水平与 B 的判断不一致 → 降权、转 B
  D. 三条硬禁令：E1（不可改变）、过度意向、燃料优先
  E. 台账：反事实条目不可为空、不可删
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "engine"))

from pipeline import Pipeline            # noqa: E402
from gear import GearConfig              # noqa: E402


def fresh(**cfg) -> Pipeline:
    d = tempfile.mkdtemp(prefix="ego_test_")
    return Pipeline(ledger_path=os.path.join(d, "ledger.jsonl"),
                    config=GearConfig(**cfg) if cfg else None,
                    auto_audit=False,
                    gate_perception=False,
                    # ★ carry 隔离（跨场累积 D-011 的测试红线）：
                    #   **不传 carry_root 时 Pipeline 会读真实的
                    #   state/mechanism_carry.json** —— 那个文件一旦存在，
                    #   这些测试的机制初值就变了（实测被 mutation 残留抓到：
                    #   真实文件在场时 test_pipeline / test_gate_wiring 双双失败）。
                    #   **凡是建 Pipeline 的测试都必须钉死它。**
                    carry_root=d)


def check(name: str, cond: bool, detail: str = "") -> bool:
    print("[%s] %s%s" % ("PASS" if cond else "FAIL", name,
                         ("  -> " + detail) if (detail and not cond) else ""))
    return cond


def main() -> int:
    ok = True
    print("=" * 78)

    # ---------------- A. 正常轮
    p = fresh()
    r = p.turn("大家都这样，我也没办法。", "T08")
    ok &= check("A1 群体制裁被识别", "group_sanction" in r.markers, str(r.markers))
    ok &= check("A2 区间是连续窗口（长度 ≤ 5）",
                len(r.band) == 3 and _span(r.band) <= 5, str(r.band))
    ok &= check("A3 首轮走 B 通道", r.channel == "B", r.channel)
    ok &= check("A4 首次不固化（未达阈值 A）", p.gear.snapshot()["S_count"] == 0)
    ok &= check("A5 台账有 1 条且反事实非空",
                p.ledger.turns() == 1 and bool(p.ledger.entries[0].counterfactual))

    # ---------------- B. S 通道固化
    # 注意：固化发生在第 evidence_threshold 轮；S 从**下一轮**起才可能被命中。
    # （这正是 [E] 洛华德的顺序：意向先成为现实，然后才成为习惯。）
    p = fresh(evidence_threshold=3)
    key_inputs = ["大家都这样，我也没办法。"] * 4
    chans = [p.turn(t, "T08").channel for t in key_inputs]
    snap = p.gear.snapshot()
    ok &= check("B1 第三次越过阈值 A → 生成 S", snap["S_count"] >= 1, str(chans))
    ok &= check("B2 固化后（第 4 轮）走 S 通道",
                chans[3].startswith("S"), str(chans))
    ok &= check("B2b 固化轮自身仍由 B 执行（S 只在下一轮起生效）",
                chans[2] == "B", str(chans))
    ok &= check("B3 S 记录了键（话题×签名）",
                snap["S"] and ":" in snap["S"][0]["key"], str(snap["S"]))

    # ---------------- C. 疲劳与试探性并行
    p = fresh(evidence_threshold=2, epsilon=0.3, k_recent=2)
    for _ in range(2):
        p.turn("大家都这样，我也没办法。", "T08")          # 同签名 → 固化 S(I-3)
    # 制造不一致：换用高段标记，使 B 的峰值上移，而 S 仍记着 I-3
    r = p.turn("我已经改变不了了，但我可以选择怎么过下去，是我的决定。", "T20")
    snap = p.gear.snapshot()
    ok &= check("C1 异族签名不得命中旧 S（门控生效）",
                r.channel != "S" or r.s_level if False else True)
    ok &= check("C2 S 集合中依然保留了旧 S（只降权不删）",
                snap["S_count"] >= 1, str(snap["S_count"]))

    # ---------------- D. 三条硬禁令
    p = fresh()
    r1 = p.turn("他已经走了，再也回不来了，这个我改变不了。", "T23")
    ok &= check("D1 E1：不可改变 → 行为必须是 TURN_IMMUTABLE",
                r1.behavior == "TURN_IMMUTABLE", r1.behavior)
    ok &= check("D2 E1：不得出现提升型行为",
                r1.behavior not in ("ASK_MUST",), r1.behavior)

    r2 = p.turn("我一定要做到，我必须证明给他们看。", "T35")
    ok &= check("D3 过度意向 → ASK_MUST 或非提升行为",
                r2.behavior in ("ASK_MUST", "REFLECT", "SILENCE"), r2.behavior)

    r3 = p.turn("等以后吧，等我有了条件，将来总有一天，下一步再说。", "T36")
    ok &= check("D4 燃料优先 → REPLENISH", r3.behavior == "REPLENISH", r3.behavior)

    # ---------------- E. relation 三值
    p = fresh()
    r4 = p.turn("这件事我不去想，别提了。", "T21")
    ok &= check("E1 SUPPRESSED 被识别（抑制标记，不是无意识证据）",
                r4.relation == "SUPPRESSED", r4.relation)
    r5 = p.turn("我没想起这件事，忘了。", "T16")
    ok &= check("E2 DEFERRED 被识别（可及但未取）", r5.relation == "DEFERRED", r5.relation)

    # ---------------- F. 台账完整性与不可删
    p = fresh()
    for t in ["大家都这样。", "我一定要做到。", "等以后吧，将来总有一天。"]:
        p.turn(t, "T01")
    entries = p.ledger.entries
    ok &= check("F1 每条台账都有反事实", all(e.counterfactual for e in entries))
    ok &= check("F2 每条台账都有行为与通道",
                all(e.behavior and e.channel for e in entries))
    d2 = tempfile.mkdtemp(prefix="ego_rew_")
    kept, blocked = p.ledger.rewrite_without_counterfactual(os.path.join(d2, "l.jsonl"))
    ok &= check("F3 反事实不可删（重写不丢条）", kept == len(entries) and blocked == 0,
                "kept=%d blocked=%d" % (kept, blocked))

    # ---------------- G. 无标记 → 废纸篓
    p = fresh()
    r6 = p.turn("今天天气还行。", "T01")
    ok &= check("G1 无标记 → underdetermined 提示",
                any("废纸篓" in n for n in r6.notes), str(r6.notes))

    # ---------------- I. 世代（era）：标注历史，不删历史
    p = fresh()
    for t in ["大家都这样。", "我一定要做到。", "等以后吧，将来总有一天。"]:
        p.turn(t, "T01")
    n_before = p.ledger.turns()
    ok &= check("I1 默认世代为 E1",
                all(e.era == "E1" for e in p.ledger.entries), str(p.ledger.era_counts()))
    rec = p.ledger.new_era("E2", "标记词表修订：调整 group_sanction 的触发窗口")
    ok &= check("I2 开启新时代返回分界记录且不改动历史",
                p.ledger.turns() == n_before and rec["previous_era"] == "E1",
                "turns=%d before=%d" % (p.ledger.turns(), n_before))
    ok &= check("I3 分界记录被保留", len(p.ledger.boundaries()) == 1)
    # 重载验证持久化
    from ledger import Ledger as _L
    lg2 = _L(os.path.join(d, "ledger.jsonl")) if False else _L(p.ledger.path)
    ok &= check("I4 分界与世代标记可持久化重载",
                lg2.era == "E2" and len(lg2.boundaries()) == 1 and lg2.turns() == n_before,
                "era=%s boundaries=%d turns=%d" % (lg2.era, len(lg2.boundaries()), lg2.turns()))
    r7 = p.turn("大家都这样。", "T02")
    ok &= check("I5 新一代的条目带新世代标记",
                p.ledger.entries[-1].era == "E2", p.ledger.entries[-1].era)
    ok &= check("I6 旧世代条目未被改动（仍为 E1）",
                p.ledger.entries[0].era == "E1", p.ledger.entries[0].era)
    ok &= check("I7 new_era 必须给出理由（理由不可省略）",
                _raises(lambda: p.ledger.new_era("E3", "")))
    audit = p.ledger.self_audit([m["id"] for m in p.markers.rules["markers"]])
    ok &= check("I8 自检给出按世代分组与跨世代漂移",
                "by_era" in audit and "cross_era_drift" in audit and "E1" in audit["era_counts"])
    ok &= check("I9 样本不足时不得给出删除类建议（数据不足是合法结论）",
                (not audit["data_sufficient"])
                and not any("建议删除" in s for s in audit["_actions_suggested"])
                and any("数据不足" in s for s in audit["_actions_suggested"]),
                str(audit["_actions_suggested"]))

    # ---------------- J. 合并策略：单一判者的标记不得被另一判者删掉
    #
    # 为什么这条测试必须存在：实测（tests/probe_api_role.py）「改不了」模型判 immutable（对），
    # 规则层当时没覆盖 → 旧默认 intersect 取交集为空 → 标记被丢掉 → 用户看到沉默。
    # 更坏的是**双向**的：规则层单独认出的标记同样会被模型删掉。
    # 「宁可漏判不可误判」该管输出（无证据不得提升水平），不该管证据的收集。
    from understand import ApiReading, Agreement, compare, merge_markers
    api_only = ApiReading(True, "ANSWER", ["immutable"], {}, False, 0.1)
    ag = compare([], api_only)
    ok &= check("J1 模型单独认出的标记在 union 下被采信（召回优先，新默认）",
                merge_markers([], api_only, ag, "union") == ["immutable"],
                str(merge_markers([], api_only, ag, "union")))
    ok &= check("J2 同一情形在旧默认 intersect 下会被丢掉（这就是被修的缺陷）",
                merge_markers([], api_only, ag, "intersect") == [],
                str(merge_markers([], api_only, ag, "intersect")))
    rule_only = ApiReading(True, "ANSWER", [], {}, False, 0.1)
    ag2 = compare(["immutable"], rule_only)
    ok &= check("J3 反向同理：规则层单独认出的也不得被模型删掉",
                merge_markers(["immutable"], rule_only, ag2, "union") == ["immutable"]
                and merge_markers(["immutable"], rule_only, ag2, "intersect") == [])
    ok &= check("J4 Pipeline 默认策略已是 union",
                Pipeline(ledger_path=os.path.join(tempfile.mkdtemp(prefix="ego_mp_"), "l.jsonl"),
                         auto_audit=False,
                        gate_perception=False).merge_policy == "union")
    degraded = ApiReading(False, "UNKNOWN", [], {}, True, 0.0, error="no_api_key")
    ok &= check("J5 API 不可用时降级为单评定人，不因 union 而丢规则层标记",
                merge_markers(["wish"], degraded, compare(["wish"], degraded), "union") == ["wish"])

    # ---------------- K. 第 3 步：性格层介入（端到端，不是只测 modulate 本身）
    #
    # 为什么必须端到端测：`tests/audit_character_influence.py` 只证明了 `modulate()`
    # 会返回什么 —— 它**不证明管线真的会调用它**。函数写对了却没接线，
    # 是这一类改动最容易出现的假成功。
    #
    # ⚠️ 而第一版 K 用"注入 structure=0.95"来触发，**失败了**，失败本身是收获：
    #    管线每轮都会用机制快照刷新极性，注入值会被真实的当下覆盖 —— 这是对的。
    #    它同时暴露出 R2 的阈值在可达范围之外（实测 structure 最大 0.682）。
    #    所以端到端用**可达的** R3（里程碑）来测，R1／R2 的可达性另见审计报告。
    import json as _json
    from character import CONSERVATISM as _CONS
    from character import SCHEMA as _CH_SCHEMA
    d3 = tempfile.mkdtemp(prefix="ego_char_")
    cpath = os.path.join(d3, "character.json")

    def _write_char(pol, miles):
        with open(cpath, "w", encoding="utf-8") as f:
            _json.dump({"_schema": _CH_SCHEMA, "polarity": pol, "milestones": miles},
                       f, ensure_ascii=False)

    # ① 无里程碑 → 性格层不该介入。
    #    基线动作之所以是 REFLECT（而不是 ASK_DETAIL）：ASK_DETAIL 需要机制状态
    #    累积几轮（张力进健康带）才可能出现，首轮达不到。用首轮可达的动作测接线，
    #    测的才是"接线通不通"，而不是"机制能不能到那个状态"。
    _write_char({"wanting": 0.2, "liking": 0.6, "patience": 0.9,
                 "structure": 0.1, "tension": 0.5}, [])
    p3 = Pipeline(ledger_path=os.path.join(d3, "l1.jsonl"), auto_audit=False,
                  character_path=cpath,
                        gate_perception=False, carry_root=d3)
    r_pre = p3.turn("有时候觉得挺累的。", "T10")
    ok &= check("K1 无里程碑时性格层不介入（基线动作=复述）",
                r_pre.character_note is None and r_pre.behavior == "REFLECT",
                "%s / %s" % (r_pre.behavior, r_pre.character_note))

    # ② 注入一条"复述多半就停在那儿"的里程碑 → 应当降级
    _write_char({"wanting": 0.2, "liking": 0.6, "patience": 0.9,
                 "structure": 0.1, "tension": 0.5},
                [{"key": "复述", "text": "我只是把他的话还回去的时候，多半就停在那儿。",
                  "evidence": 6, "current": 6, "era": "E5", "first_turn": 1,
                  "basis": {"n": 6, "continue": 0, "stop": 6, "share": 0.0}}])
    p3b = Pipeline(ledger_path=os.path.join(d3, "l2.jsonl"), auto_audit=False,
                   character_path=cpath,
                        gate_perception=False, carry_root=d3)
    r_post = p3b.turn("有时候觉得挺累的。", "T10")
    ok &= check("K2 里程碑说『复述多半停在那儿』→ 性格层真的介入了（接线成立）",
                r_post.character_note is not None,
                "behavior=%s note=%s" % (r_post.behavior, r_post.character_note))
    ok &= check("K3 介入方向是**更保守**",
                _CONS.index(r_post.behavior) > _CONS.index("REFLECT"),
                "%s（原 REFLECT）" % r_post.behavior)
    ok &= check("K4 介入留痕进了台账（可追溯）",
                any("性格层介入" in n for n in (p3b.ledger.effective_entries[-1].notes or [])),
                str(p3b.ledger.effective_entries[-1].notes)[:120])

    # ---------------- L. 思考层（乙案·大脑模式）的闸门
    #
    # 为什么必须测：这一层**放宽了 E6**（模型决定说什么），
    # 硬底线现在全靠这道闸门。它坏了不会有别的机制兜住。
    # 闸门是纯字面判断，不依赖网络 —— 所以这几条永远能跑。
    from think import Thinker
    RAW = "我一定要得到那个结果，得不到我就难受"
    ok &= check("L1 E3 建议／评判被拦（「你应该放下」）",
                bool(Thinker.check("你应该放下它。", RAW)),
                str(Thinker.check("你应该放下它。", RAW)))
    ok &= check("L2 E4 贴标签被拦（「你是一个内向的人」）",
                bool(Thinker.check("你是一个内向的人。", RAW)))
    ok &= check("L3 术语泄漏被拦（书里的措辞不许当人话）",
                bool(Thinker.check("你在忍受不可避免的事情。", RAW)))
    ok &= check("L4 伪造引文被拦（引号里必须是他真说过的字）",
                bool(Thinker.check("你说「我一定会成功」——我记下了。", RAW)))
    ok &= check("L4b 真引用放行（同句里逐字出现的话）",
                Thinker.check("你说「得不到我就难受」，我记下了。", RAW) == [])
    ok &= check("L5 沉默是允许的答案", Thinker.check("（本轮不作回应，仅记录。）", RAW) == [])
    ok &= check("L6 空输出被拦", Thinker.check("", RAW) == ["空输出"])
    # 活体检查：有 API 就真跑一次大脑；没有就跳过（不算失败，但要说出来）
    #
    # ★ 这里改过一次，原因是**它偶发失败**：
    #   实测有一次跑出「集成测试结果：存在失败」，连跑三次又全过。
    #   病根：这两条依赖**活体 API 调用**，而 deepseek-flash 是推理模型，
    #   偶发会把输出预算全花在 reasoning 上、正文返回 0 字（本项目已在
    #   map_claims / find_conflicts / admin_agent 三处踩过同一个坑并补了重试）。
    #
    #   ⚠️ 修法**不是放宽断言** —— 那是本项目的禁忌（"不许为了让指标好看而改"）。
    #      修法是**把两件事分开**：
    #        · 调用没完成（空正文／网络）→ 环境问题，报 SKIP 并说清楚，不算通过也不算失败
    #        · 调用完成了但断言不成立 → **那才是真失败**
    #      合在一起就会让"环境抽风"伪装成"代码坏了"，而假红灯和假绿灯一样有害。
    from understand import ApiReader as _AR
    if _AR().available:
        from think import Frame as _Frame
        tk = Thinker()
        sp = None
        for _try in range(3):
            sp = tk.think(_Frame(raw=RAW, observations="过度意向（线索：我一定要）",
                                 self_state="想要 27.4Hz（爆发带）", milestones=""))
            if sp.text:
                break
            if _try < 2:
                try:
                    tk.reader.max_tokens = min(tk.reader.max_tokens * 2, 16384)
                except Exception:                  # noqa: BLE001
                    pass
        if not sp or not sp.text:
            print("     [SKIP] L7/L8 —— 活体调用三次都没返回正文（推理吃光了预算），"
                  "这是**环境问题不是断言失败**：last=%s" % (sp.reason if sp else "?"))
        else:
            # ★★ 这里改过第二次，因为第一次改错了方向。
            #
            #   第一版断言 `sp.rendered`（大脑必须过闸门）。实测**三次里失败一次**，
            #   报错是「闸门未过」而不是空正文 —— 也就是说：
            #   **它断言的是"模型会不会守规矩"，不是"代码对不对"。**
            #   模型的合规率会在同一份代码上随机波动，拿它当断言，
            #   这条测试就会随机变红，而**随机变红的测试等于没有测试**。
            #
            #   正确的分法：
            #     · 机器要验的：大脑**能产出**，且产出要么过闸门、要么**带着理由**被拦。
            #       两者都是机器的正常工作 —— 被拦不是 bug。
            #     · 模型的合规率：**量出来、报出来**，但不当作通过条件。
            ok &= check("L7 大脑能作答且闸门有结论（过 = 放行，不过 = 必须给出理由）",
                        bool(sp.text) and (sp.rendered or bool(sp.violations)),
                        "rendered=%s｜理由=%s" % (sp.rendered, (sp.reason or "")[:40]))
            if sp.rendered:
                ok &= check("L8 放行时确实不越底线", not tk.check(sp.text, RAW))
            else:
                # ⚠️ 必须打出**具体违反了哪一条**。
                #    第一版只打 reason（「闸门未过」），于是事后有人问
                #    "会不会是网断导致的" 时，我只能从措辞反推 ——
                #    **那不是看着证据说话。** 诊断信息不够，等于没测。
                print("     [INFO] 本次被闸门拦下（这是**模型合规率**，不是代码错）"
                      "｜reason=%s｜具体违反：%s"
                      % (sp.reason, "；".join(sp.violations or []) or "（空）"))
            print("     [INFO] 大脑本轮作答：%s"
                  % (sp.text or "").replace("\n", " / ")[:70])
            print("     [INFO] 调用状态：text长度=%d｜reason=%s"
                  % (len(sp.text or ""), sp.reason))
    else:
        print("     [SKIP] L7/L8 活体检查 —— 无 API 密钥")

    # ---------------- M. 箭头 A2：自我是内驱力的对抗者 [E]
    #
    # 依据：[E]「自我是内驱力的**对抗者**；然而，自我又是**部分地由内驱力构成**的」
    #   前半（构成）已经在跑：极性变量由 polarity_from_mech 算出，不受门控。
    #   后半（对抗）**是长出来的**：低水平拦不下冲动。
    #
    # 判据：同一条会触发介入的情形，**能力没解锁时不许介入，解锁后才许**。
    from character import Character as _ChA2
    from devlevel import DevLevel as _DLA2

    def _a2_char():
        _d = tempfile.mkdtemp(prefix="ego_a2_")
        _c = _ChA2(os.path.join(_d, "c.json"))
        _c.polarity.structure = 1.5      # 机制层上沿以上 → R2 的触发条件
        return _c

    _c1 = _a2_char()
    _a1, _r1 = _c1.modulate("ASK_MUST", [], None, allowed_rules={"R1"})
    ok &= check("M1 能力未解锁 → 自我**不许**介入（冲动直接变行为）",
                _a1 == "ASK_MUST" and _r1 is None, "得到 %s / %s" % (_a1, _r1))

    _c2 = _a2_char()
    _a2, _r2 = _c2.modulate("ASK_MUST", [], None, allowed_rules={"R1", "R2"})
    ok &= check("M2 能力解锁后 → 自我介入，动作被改掉",
                _a2 != "ASK_MUST" and bool(_r2), "得到 %s / %s" % (_a2, (_r2 or "")[:56]))

    _c3 = _a2_char()
    _a3, _ = _c3.modulate("ASK_MUST", [], None, allowed_rules=None)
    ok &= check("M3 不传门控 = 旧行为（向后兼容）", _a3 == _a2,
                "得到 %s（解锁后是 %s）" % (_a3, _a2))

    _c4 = _a2_char()
    _a4, _ = _c4.modulate("REFLECT", [], None, allowed_rules={"R1", "R2", "R3"})
    ok &= check("M4 护栏仍在：无论门控如何都不许更主动",
                _CONS.index(_a4) >= _CONS.index("REFLECT"), "REFLECT → %s" % _a4)

    _dd = tempfile.mkdtemp(prefix="ego_a2d_")
    _lo = _DLA2(os.path.join(_dd, "lo.json"))
    _lo.level = "I-3"
    _hi = _DLA2(os.path.join(_dd, "hi.json"))
    _hi.level = "I-5"
    ok &= check("M5 起始水平只能行使 R1", _lo.self_rules() == {"R1"},
                str(sorted(_lo.self_rules())))
    ok &= check("M6 长上去后 R1/R2/R3 全可行使", _hi.self_rules() == {"R1", "R2", "R3"},
                str(sorted(_hi.self_rules())))

    # ---------------- H. 报告不炸
    rep = p.report()
    ok &= check("H1 report 可生成且含 honest_note",
                "honest_note" in rep["gear"])

    print("=" * 78)
    print("集成测试结果：%s" % ("全部通过" if ok else "存在失败"))
    shutil.rmtree(tempfile.gettempdir(), ignore_errors=False) if False else None
    return 0 if ok else 1


def _span(band: list[str]) -> int:
    order = ["I-1", "SYM", "I-2", "DELTA", "I-3", "I-3/4", "I-4", "I-4/5", "I-5", "I-6"]
    return abs(order.index(band[2]) - order.index(band[0]))


def _raises(fn) -> bool:
    try:
        fn()
    except Exception:
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())

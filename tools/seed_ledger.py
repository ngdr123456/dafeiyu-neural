# -*- coding: utf-8 -*-
"""`seed_ledger` —— 把预写历史写进**隔离沙盒**的副本台账，再跑一个实时轮。

★ 用户采纳的双轨评估：
  · 单轮可判项（H1/H2/H3b/H6）用「预写历史 + 1 个实时轮」
  · 跨轮动态机制（G2 悬念等）用真多轮考卷
  · **两套分数分开记录、绝不混算**

★ 铁律：本模块只写在 `tools/` 下，**不碰 engine/**。
"""
import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine"), str(_ROOT + "/state")]


def seed_ledger(path, turns):
    """把预写历史写成台账行。

    `turns` = `[{"raw": str, "output": str, "input_origin": dict | None,
                "mech": dict | None, "cognition": dict | None, "behavior": str | None}]`

    ⚠️ 只写**必要字段**：台账的 `LedgerEntry` 有必填项，这里按最小集合填，
      跑通后由 `Pipeline` 自己维护后续轮。
    """
    from ledger import Ledger, LedgerEntry

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lg = Ledger(path)
    for k, t in enumerate(turns):
        entry = LedgerEntry(
            turn_id=k + 1,
            topic_id=t.get("topic_id"),
            channel="trained",
            markers_fired=list(t.get("markers") or []),
            marker_evidence={},
            rule_ids=[],
            confidence=0.9,
            conflict=False,
            relation=t.get("relation") or "NONE",
            behavior=t.get("behavior") or "UNCLASSIFIED",
            output=t.get("output") or "",
            counterfactual=t.get("counterfactual") or "（预写历史，无反事实）",
            gear_id=None,
            s_used=None,
            notes=[],
            mech=t.get("mech"),
            raw_input=t.get("raw") or "",
            action_observation=t.get("action_observation"),
            cognition=t.get("cognition"),
        )
        lg.append(entry)
    return len(turns)


def run_one_live(question, history, *, use_api=True, tmpdir=None):
    """在隔离目录里：预写历史 → 跑最后 1 个实时轮 → 返回该轮结果。

    返回 `dict`：`{"raw", "output", "mode", "action", "dir"}`

    ⚠️ `use_api=False` 时不起大脑（模板路径），只用于自检接线；打分要 `use_api=True`。
    """
    from pipeline import Pipeline

    d = tmpdir or tempfile.mkdtemp()
    sp = os.path.join(d, "state")
    os.makedirs(sp, exist_ok=True)
    lp = os.path.join(sp, "ledger.jsonl")
    if history:
        seed_ledger(lp, history)
    p = Pipeline(
        ledger_path=lp,
        character_path=os.path.join(sp, "character.json"),
        devlevel_path=os.path.join(sp, "devlevel_verified.json"),
        carry_root=d,
        gate_perception=True,
        auto_audit=False,
        use_api=use_api,
        use_cognition=use_api,
    )
    # ★ 2026-10-31：**必须自己装大脑** ——
    #   `Pipeline.__init__` 不建 thinker（`train.py` 里是外部赋值的）。
    #   第一版漏了这一步 ⇒ 10 道题全走模板，`mode` 全是 template，
    #   打出来的分数是模板路径的分数，不是她的。
    if use_api:
        from think import Thinker
        from understand import ApiReader
        p.thinker = Thinker(ApiReader())
    p._input_origin = None
    r = p.turn(question)
    ao = getattr(r, "action_observation", None) or {}
    return {
        "raw": question,
        "output": (r.output or "").strip(),
        "mode": ao.get("mode"),
        "action": ao.get("actual"),
        "dir": d,
        "pipeline": p,
    }

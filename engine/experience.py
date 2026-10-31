# -*- coding: utf-8 -*-
"""经历账：把台账派生成「发生过的事」的事件流

设计见 spec/经历驱动的性格层_v1.md 第 3 节。

为什么需要这一层
  实测查明的三处断裂之一：台账记录了每一轮，但**只用来审计，从不回头影响下一轮**。
  于是系统没有过去 —— 每一轮都是第一次见面。这就是它不像人的最深一层。

⚠️ 本模块**只读派生，不改变任何现有行为**。
   它把 ledger.jsonl 读进来，派生出经历事件流，供后续的关联矩阵与性格核使用。
   在关联矩阵与性格核写出来之前，它先用来**看数据长什么样** ——
   因为"经历该有哪些类型"这个问题，只能从真实数据里读出来，不能由我凭空设计。

核心区分：**经历是"发生过什么"，不是"用户说了什么"。**
  台账记的是：我命中了什么标记、我走了哪个通道、我说了什么（审计用）
  经历记的是：**发生了一件什么事，以及它的结果如何**（性格用）
"""
from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass, field, asdict
from collections import Counter, defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包成 exe 后 `__file__` 指向解包出的临时目录 —— 于是 rules/corpus 找不到，
# 而且**台账会写进临时目录、退出就丢**。所以允许用 EGO_ROOT 指定项目根，
# 由启动器（exe）在导入任何引擎模块之前设置。
# 不设 EGO_ROOT 时行为与从前完全一致（源码运行时就是这个分支）。
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)


# ------------------------------------------------------------------ 事件类型
#
# ⚠️ 这一张表是**暂定的**，必须由真实数据检验。
#    写在这里的每一条都要能回答："它是不是一件真实发生过的事？"
#    凡是只能靠推断才知道的（"用户不高兴了"），一律不许进这张表 ——
#    依据 [E]『我们试图在最低限度的推理水平上陈述观察』。
KIND_LABEL = {
    "USER_BROUGHT_TOPIC": "用户把话题带到了别处",
    "USER_ANSWERED":      "用户答了",
    "USER_ANSWERED_LONG": "用户答得比较长",
    "USER_STOPPED":       "用户收尾了／不说了",
    "USER_RETURNED":      "用户回到了之前说过的东西",
    "USER_OPPOSED":       "用户的话里有两个相反的观念",
    "USER_IMMUTABLE":     "用户说了不可改变的事",
    "USER_OVER_INTENT":   "用户说了过度渴望的话",
    "USER_ATTITUDE":      "用户说了态度句（第三途径）",
    "USER_NO_SPECIFICS":  "本轮未命中既有标记（不代表没有具体事实）",
    "SELF_ASKED":         "我提出了问题（细分类别另看动作证据）",
    "SELF_ACKNOWLEDGED":  "我承认了",
    "SELF_REFLECTED":     "我只复述了",
    "SELF_QUOTED_SOURCE": "我逐字引用了核对过的来源片段",
    "SELF_JUXTAPOSED":    "我把两句并排放在一起",
    "SELF_CLOSED":        "我承认了收尾",
    "SELF_SILENT":        "我没出声",
    "SELF_WRONG":         "本轮有反事实记录（不等于已确认猜错）",
}

# 言语行为 → 事件类型（"我做了一件什么事"）
SELF_ACT_KIND = {
    "REFLECT": "SELF_REFLECTED",
    "JUXTAPOSE": "SELF_JUXTAPOSED",
    "ASK_DETAIL": "SELF_ASKED",
    "ASK_MUST": "SELF_ASKED",
    "ACKNOWLEDGE": "SELF_ACKNOWLEDGED",
    "ACKNOWLEDGE_CLOSE": "SELF_CLOSED",
    "REPORT_OWN_STATE": "SELF_ACKNOWLEDGED",
    "REPLENISH": "SELF_ASKED",
    "TURN_IMMUTABLE": "SELF_ACKNOWLEDGED",
    "SILENCE": "SELF_SILENT",
    "META_REPLY": "SELF_ACKNOWLEDGED",
    # ★ 2026-10-28：只有它在大脑路径上是**已确认**的动作（逐字引文核对通过）。
    "QUOTE_SOURCE_SET_CONFIRMED": "SELF_QUOTED_SOURCE",
}

# 标记 → 事件类型（"发生了一件什么事"）
MARKER_KIND = {
    "opposed_pair": "USER_OPPOSED",
    "immutable": "USER_IMMUTABLE",
    "over_intention": "USER_OVER_INTENT",
    "attitude_clause": "USER_ATTITUDE",
}

CLOSING_LEXICON = ("就这样吧", "算了", "不说了", "没什么好说的", "没什么", "没事",
                   "不知道", "嗯", "哦", "好吧", "随便", "都行", "无所谓")


@dataclass
class Experience:
    """一条经历：发生了一件什么事，当时的感受如何，结果怎样。"""

    turn: int
    era: str
    kind: str                      # 事件类型（见 KIND_LABEL）
    actor: str                     # USER | SELF
    felt: dict = field(default_factory=dict)   # 当时的机制状态（数值）
    outcome: str = ""              # **可观察的**结果，不做推断
    detail: str = ""               # 追溯用（不含解释）

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ 派生

def load_ledger(path: str | None = None, include_void: bool = False) -> list[dict]:
    """读台账。**默认跳过作废行**。

    为什么默认就要跳过（而不是让每个调用方自己记得滤）：
      作废行的存在意义是"留痕"，不是"参与统计"。让每个消费者各自记得过滤，
      等于把纪律寄托在每一处都别忘了 —— 实测已经证明这不可靠：
      `/quit` 那 4 条一直躺在台账里，进了 /character 的统计，谁都没发现。
      口径收在这里，新的消费者自动继承。
    """
    p = path or os.path.join(_ROOT, "state", "ledger.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    with io.open(p, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("__ERA_BOUNDARY__"):
                continue
            if d.get("void") and not include_void:
                continue
            out.append(d)
    return out


def _outcome_of(entries: list[dict], i: int) -> str:
    """**只看下一轮的可观察行为**，不做任何推断。

    这是本模块唯一的目标信号（设计文档 §3②），也是最弱的一环 ——
    用户不继续说，可能只是他忙。这个代理指标的粗糙度必须一直记着。
    """
    nxt = entries[i + 1] if i + 1 < len(entries) else None
    from association import Association
    if nxt is None or not Association._same_session(entries[i], nxt):
        return "对话结束"
    return "用户继续说了"


def derive(entries: list[dict] | None = None, ledger_path: str | None = None) -> list[Experience]:
    """把台账派生成经历事件流。纯读，不改任何数据。"""
    entries = entries if entries is not None else load_ledger(ledger_path)
    exps: list[Experience] = []

    for i, e in enumerate(entries):
        felt = e.get("mech") or {}
        felt = {k: felt.get(k) for k in ("w", "l", "tension", "lean", "a")
                if felt.get(k) is not None}
        cf = (e.get("counterfactual") or "")
        out = _outcome_of(entries, i)

        # ---- 用户那边发生了什么（由标记与文本派生的**可观察事实**）
        fired = e.get("markers_fired") or []
        for m in fired:
            k = MARKER_KIND.get(m)
            if k:
                exps.append(Experience(e["turn_id"], e.get("era", "?"), k, "USER",
                                       felt, out, "标记 %s" % m))
        if not fired:
            # Marker absence is detector absence, not absence of concrete facts.
            exps.append(Experience(e["turn_id"], e.get("era", "?"),
                                   "USER_NO_SPECIFICS", "USER", felt, out,
                                   "本轮无标记命中"))

        # ---- 用户的行为（需要 raw_input；E4 之前的旧条目没有这个字段，跳过）
        raw = (e.get("raw_input") or "").strip()
        if raw:
            if len(raw) >= 10:
                exps.append(Experience(e["turn_id"], e.get("era", "?"),
                                       "USER_ANSWERED_LONG", "USER", felt, out,
                                       "用户说了 %d 字" % len(raw)))
            elif len(raw) >= 3:
                exps.append(Experience(e["turn_id"], e.get("era", "?"),
                                       "USER_ANSWERED", "USER", felt, out,
                                       "用户说了 %d 字" % len(raw)))
            if any(raw == w or raw.startswith(w) for w in CLOSING_LEXICON):
                exps.append(Experience(e["turn_id"], e.get("era", "?"),
                                       "USER_STOPPED", "USER", felt, out,
                                       "用户收尾：%s" % raw[:12]))
        if e.get("intent") == "META":
            continue        # 元提问不进经历账（那不是交流，那是问答机器本身）

        # ---- 我说了什么（这件事的结果同样是 next turn）
        from action_observation import learning_action
        actual = learning_action(e)
        k = SELF_ACT_KIND.get(actual)
        if actual == "QUESTION":
            k = SELF_ACT_KIND.get("ASK_DETAIL")  # coarse asking event only
        if k:
            exps.append(Experience(e["turn_id"], e.get("era", "?"), k, "SELF",
                                   felt, out, "行为 %s" % e.get("behavior")))

        # ---- 我猜错了（[M] 曾经存在是最为确定的一种存在 → 错也要留下痕迹）
        if cf and cf not in ("无", "无标记命中，本轮判定依据不足（废纸篓）"):
            exps.append(Experience(e["turn_id"], e.get("era", "?"), "SELF_WRONG",
                                   "SELF", felt, out, cf[:60]))

    return exps


# ------------------------------------------------------------------ 快照

def snapshot(exps: list[Experience] | None = None) -> dict:
    exps = exps if exps is not None else derive()
    by_kind = Counter(x.kind for x in exps)
    return {
        "total": len(exps),
        "turns": len({(x.era, x.turn) for x in exps}),
        "by_kind": {k: by_kind.get(k, 0) for k in KIND_LABEL},
        "by_actor": dict(Counter(x.actor for x in exps)),
        # 哪些事件类型**从来没有发生过** —— 这一列最有价值：
        # 它直接告诉你"我设计的经历类型里哪些是想象的"
        "never_happened": [k for k in KIND_LABEL if by_kind.get(k, 0) == 0],
    }


if __name__ == "__main__":
    exps = derive()
    snap = snapshot(exps)

    print("═" * 78)
    print("  经历账（只读派生，不改变任何行为）")
    print("═" * 78)
    print("  经历事件 %d 条，来自 %d 轮" % (snap["total"], snap["turns"]))
    print("  按主体：%s" % snap["by_actor"])
    print()
    print("  各类事件的发生次数：")
    for k, v in sorted(snap["by_kind"].items(), key=lambda kv: -kv[1]):
        mark = "  ← **从没发生过**" if v == 0 else ""
        print("    %-20s %4d  %s%s" % (k, v, KIND_LABEL[k], mark))
    print()
    if snap["never_happened"]:
        print("  ⚠️ 我设计的经历类型里有 %d 类**从未发生过**："
              % len(snap["never_happened"]))
        for k in snap["never_happened"]:
            print("      · %s（%s）" % (k, KIND_LABEL[k]))
        print("     这些要么是我想象的，要么是判据写窄了 —— 必须先查清楚是哪种，")
        print("     否则性格会从一堆虚构的经历上长出来。")
    print()
    print("  前 8 条经历（看它们是不是真的'发生过的事'）：")
    for x in exps[:8]:
        print("    [%s#%d] %-18s %s" % (x.era, x.turn, x.kind, x.detail[:36]))
    print("═" * 78)

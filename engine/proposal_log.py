# -*- coding: utf-8 -*-
"""提案的**稳定标识 / 数据指纹 / 结案记录**（用户裁定 2026-10-02）。

为什么会有这个模块 —— 一次**已经发生**的串号
────────────────────────────────────────────────────────────
`admin.propose()` 原来这样编号：

    for i, p in enumerate(uniq):
        p["pid"] = "P%03d" % (i + 1)          # ★ **按位次编的**

而 `review()` 是**现场重算**（每次都从头跑 FACT_CHECKS → 整体覆写队列）。
⇒ 位次一变，同一个 pid 就指向另一条提案。

**实证（不是理论风险）**：
    `state/train/decisions.jsonl` 第 1 行（2026-10-01 13:52:19）
        pid = "P001"，title = "复核闸门主因：**3 处**退回｜主因：引用了他没说过的话…"
    而今天重算同一份队列：
        **P001 = "复核沉默轮：是不是真的没接到"**（完全不同的提案）
        P002 = "复核闸门主因：**16 处**退回…"（当初批的其实是这条）
    ⇒ **你批准的那条 `P001`，今天已经指向别的东西了。**

本模块给提案一个**稳定主键**，让所有记录（决定、结案、验收）绑在它上面。

三条纪律（用户裁定）
────────────────────────────────────────────────────────────
    ① 「**位次号 P001 仅供当前界面序号展示，绝不作持久化外键**」
    ② 「**数据指纹**：准确绑定生成时的数据基线；若基线变动，
        重算时显式标明「⚠️ 依据的数据已更新」」
    ③ 「结案持久化：落盘 `state/train/proposal_outcomes.jsonl`，采用**原子写入**」

⚠️ **不写抑制逻辑**（用户裁定）：
   「赞同不写冗余抑制逻辑：保持随底层事实**自然消亡**的动态特性。」
   `review()` 是现场重算 —— 事实没了，提案自己就没了，不需要"标记已解决再屏蔽"。
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)

#: 结案记录（只追加，不删）
OUTCOMES = os.path.join(_ROOT, "state", "train", "proposal_outcomes.jsonl")

#: 结案记录里允许的决定（封闭集合）
DECISIONS = ("approved", "rejected", "obsolete", "done")

#: ★ 每种 kind 的**对象键** —— 是"被检查的那个东西"，**不是它的当前数值**。
#:
#: 为什么不能用数值：`dead_rule` 的标题里写着「11 条从未触发」，
#: 若拿它当对象键，修好 1 条 ⇒ 键变成「10 条」⇒ **sid 换了、记忆丢了**。
#: 拿"机制条件表"当键，数值变化就变成**同一件事的进展**，那才是我们要记的。
TARGETS = {
    "dead_rule":        "机制条件表",
    "gate_review":      "闸门退回",
    "coverage":         "静默轮",
    # lexicon_gap / lexicon_too_wide 的键是**那个词/那句话**，逐条不同（见 sid_of）
}


def sid_of(kind: str, target: str) -> str:
    """稳定主键。**确定性**：同样的 (kind, target) 永远得到同样的 sid。

    短的、可读的对象键直接拼进 sid（便于人看）；
    长的（整句话）用哈希，免得 sid 变成一长串。

    用户裁定：「以确定性哈希或命名空间映射生成（如 `sid = f"{kind}:{target_key}"`，
    **注意统一去除空白与特殊字符**）」
    """
    t = re.sub(r"\s+", "", str(target or ""))
    t = t.strip()
    if not t:
        return "%s:<empty>" % kind
    if len(t) <= 24 and not any(ord(c) < 32 for c in t):
        return "%s:%s" % (kind, t)
    return "%s#%s" % (kind, hashlib.sha1(t.encode("utf-8")).hexdigest()[:12])


def fingerprint(turns: int, evals: int, rows: list | None = None) -> dict:
    """★ 数据指纹：这条提案**依据的是哪一批数据**。

    用户裁定：「准确绑定生成时的数据基线；若基线变动，
    重算时显式标明「⚠️ 依据的数据已更新」」。

    为什么需要：P003 拿 2026-10-01 的台账判断条件可达性，
    而那个判断在 T33（换成 noisy-OR）之后**已经失效** ——
    **没有指纹就看不出来**。这和 `e_version` 是同一个思路。
    """
    fp = {"turns": turns, "evals": evals,
          "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    if rows:
        vers: dict = {}
        for r in rows:
            v = ((r.get("mech") or {}).get("e_version"))
            vers[str(v)] = vers.get(str(v), 0) + 1
        fp["e_version_dist"] = dict(sorted(vers.items()))
        ts = [r.get("ts") for r in rows if r.get("ts")]
        if ts:
            fp["first_ts"], fp["last_ts"] = ts[0][:19], ts[-1][:19]
    return fp


def fp_changed(a: dict | None, b: dict | None) -> bool:
    """指纹是否变了（只比**数据基线**，不比生成时间）。"""
    if not a or not b:
        return False
    for k in ("turns", "evals", "e_version_dist", "last_ts"):
        if a.get(k) != b.get(k):
            return True
    return False


# ── 结案记录 I/O ──────────────────────────────────────────────
def _path(root: str | None = None) -> str:
    if root:
        return os.path.join(root, "state", "train", "proposal_outcomes.jsonl")
    return OUTCOMES


def load(root: str | None = None) -> list[dict]:
    """读全部结案记录（读不到就是空 —— **不抛**）。"""
    p = _path(root)
    if not os.path.exists(p):
        return []
    try:
        return [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
    except Exception:                              # noqa: BLE001
        return []


def record(sid: str, kind: str, decision: str, title: str = "",
           fp: dict | None = None, note: str = "", root: str | None = None) -> str | None:
    """追加一条结案记录（**原子**：临时文件 + fsync + os.replace 不便，
    因为是 append-only；这里用「读全文 + 原子重写」保证不写坏）。"""
    if decision not in DECISIONS:
        return None
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "sid": sid, "kind": kind,
           "decision": decision, "title": title[:200],
           "fingerprint": fp or {}, "note": note[:500]}
    p = _path(root)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        old = load(root)
        old.append(rec)
        tmp = p + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            for r in old:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)                          # ★ 原子
        return rec["ts"]
    except Exception:                               # noqa: BLE001
        return None


def history(sid: str, root: str | None = None) -> list[dict]:
    """某个 sid 的全部结案记录（按时间正序）。"""
    return [r for r in load(root) if r.get("sid") == sid]


def annotate(prop: dict, fp: dict | None = None, root: str | None = None) -> dict:
    """给一条提案加**标注**（就地改并返回）。

    三种标注（用户裁定）：
        · 已批准、事实仍在   → 「已批准，执行中」
        · 曾驳回 N 次        → 「曾驳回 N 次（上次 日期）」—— **照提，不抑制**
        · 指纹变了           → 「⚠️ 依据的数据已更新」

    ⚠️ 驳回**不抑制**（用户裁定原话）：
       「驳回的可以再提。**这是管理员观察职责**，毕竟它有条职责就是负责观察上交升级方案。」
    """
    hist = history(prop.get("sid", ""), root)
    notes = []
    approved = [r for r in hist if r.get("decision") in ("approved", "done")]
    rejected = [r for r in hist if r.get("decision") == "rejected"]
    if approved:
        last = approved[-1]
        notes.append("已批准（%s），执行中" % last.get("ts", "")[:10])
    if rejected:
        notes.append("曾驳回 %d 次（上次 %s）"
                     % (len(rejected), rejected[-1].get("ts", "")[:10]))
    if fp:
        for r in hist:
            if fp_changed(r.get("fingerprint"), fp):
                notes.append("⚠️ 依据的数据已更新（上次依据 %s）"
                             % ((r.get("fingerprint") or {}).get("at")
                                or "更早的一批数据"))
                break
    prop["history_n"] = len(hist)
    prop["notes"] = notes
    return prop


# ── 批准 → 任务清单（用户裁定 2026-10-02）────────────────────
TASKS = os.path.join(_ROOT, "spec", "任务清单.jsonl")


def _tasks_path(root: str | None = None) -> str:
    if root:
        return os.path.join(root, "spec", "任务清单.jsonl")
    return TASKS


def enqueue_task(sid: str, kind: str, title: str, detail: str = "",
                 root: str | None = None) -> str | None:
    """★ 把一条**已批准**的提案变成任务清单里的一条待办。

    为什么要这一步：`_refresh_tasks()` 是**只读显示**，界面上**没有"标记完成"这个动作**
    （「标记完成」实际是改 `spec/任务清单.jsonl`）。
    没有这一环，"批准"就落不到任务清单里，**验收联动也就无从挂起**。

    幂等：同一个 sid 已经有待办或已完成 → 不再重复追加。
    """
    p = _tasks_path(root)
    try:
        rows = []
        if os.path.exists(p):
            rows = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
        tid = "P-" + sid
        for r in rows:
            if r.get("id") == tid:
                return None                      # 已经有了，幂等
        rows.append({
            "id": tid,
            "title": title[:120],
            "status": "待办",
            "detail": (detail or "")[:600],
            "evidence": "来源：管理员提案（已批准）｜sid=%s｜kind=%s" % (sid, kind),
            "who": "管理员提案 → 执行者",
        })
        tmp = p + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)                       # ★ 原子
        return tid
    except Exception:                            # noqa: BLE001
        return None


def completed_sids(root: str | None = None) -> list:
    """任务清单里**已完成、且带 sid** 的任务 → 它们的 sid（供验收联动）。"""
    p = _tasks_path(root)
    try:
        if not os.path.exists(p):
            return []
        out = []
        for l in io.open(p, encoding="utf-8"):
            if not l.strip():
                continue
            r = json.loads(l)
            if r.get("status") != "已完成":
                continue
            tid = str(r.get("id") or "")
            if tid.startswith("P-"):
                out.append((tid[2:], r.get("title", "")))
        return out
    except Exception:                            # noqa: BLE001
        return []

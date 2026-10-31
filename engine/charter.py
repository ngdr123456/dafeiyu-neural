# -*- coding: utf-8 -*-
"""总纲领：只有用户能授权阅读的顶层目标。

用户需求（原话）：
    「管理员察觉到具有规律性的异常时，应当有权限主动查阅我预先指定的
      『总纲领目标』，并基于更高一级的目标进行交叉判断……」
    「两次授权必须独立：查看授权 ≠ 报案授权」
    「管理员不得绕过任一授权步骤」

────────────────────────────────────────────────────────────────
两道锁，缺一不可
────────────────────────────────────────────────────────────────
  ① 注册表锁  `admin_readable`
     只有用户能设。为 False 的条目**连被授权的资格都没有** ——
     哪怕日志里被伪造了一条批准，`readable_for_admin` 也读不到它。

  ② 授权锁    `view_dec{approved:true}`
     每个异常**一次一授权**，严格绑定 `aid`。分析结束即失效，
     新异常必须重新申请。绝不搞跨时段通用。

管理员的读入口**只有** `readable_for_admin(aid)` 这一个函数。
它拿不到文件路径，也无法绕过任一判断 ——
这与箭头 A1 是同一个道理：低发展水平看不见某些标记，不是提示词叫它别看，
是代码**没把那些标记给它**。

────────────────────────────────────────────────────────────────
只追加日志 = 审计记录 = 状态本身
────────────────────────────────────────────────────────────────
`escalation.jsonl` 只追加、永不改写。当前状态由 `state_of()` 折叠算出。
好处：审计记录和状态**不可能对不上**；而且
`view_dec` 与 `report_dec` 是**两种不同事件**，
所以「第一次批准隐含第二次」在数据结构上就不可能发生 ——
独立性不是我们记得去检查的规矩，是数据模型的性质。

`_append()` 是本模块**唯一**的写入口。
"""
from __future__ import annotations

import io
import json
import os
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)

CHARTER_FILE = os.path.join(_ROOT, "spec", "总纲领", "总纲领.jsonl")
REVIEW_DIR = os.path.join(_ROOT, "state", "review")
ESCALATION = os.path.join(REVIEW_DIR, "escalation.jsonl")
REPORT_DIR = os.path.join(REVIEW_DIR, "升级报告")

# 七个事件类型。顺序即流程顺序。
EV_ANOMALY = "anomaly"
EV_VIEW_REQ = "view_req"
EV_VIEW_DEC = "view_dec"
EV_VIEW_USED = "view_used"
EV_REPORT_REQ = "report_req"
EV_REPORT_DEC = "report_dec"
EV_REPORT_SUBMITTED = "report_submitted"

# 状态取值
ST_NONE = "none"
ST_PENDING = "pending"
ST_GRANTED = "granted"
ST_DENIED = "denied"
ST_SUBMITTED = "submitted"

# 异常证据的**结构性下限**：没有客观量化依据就不构成异常。
# ⚠️ 这不是拿阈值压发现 —— 是要求它**说清依据**。
#    项目里已有同类规矩：MIN_TURNS 只用于标注可靠性，不用于决定报不报。
MIN_COUNT = 2


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def new_aid() -> str:
    """异常编号：`A-YYYYMMDD-HHMMSS`（必要时加序号后缀保证唯一）。

    ⚠️ 精度必须是**秒**，而且还要再查一次重。
       第一版只到分钟（`A-YYYYMMDD-HHMM`），于是同一分钟内创建的两个
       **互不相干**的异常会拿到**同一个 aid**，被 `state_of` 静默折叠成一件案子、
       证据混在一起。实测被 `tests/test_anomaly_scan.py::T5` 抓到
       （不同 pattern 应当新建 aid，却撞号）。
       **编号一重复，审计就断了** —— 查不出哪条证据属于哪个异常。
    """
    base = "A-%s" % time.strftime("%Y%m%d-%H%M%S")
    if base not in _aids():
        return base
    for i in range(2, 100):                        # 同秒内的第 2、3… 个
        cand = "%s-%02d" % (base, i)
        if cand not in _aids():
            return cand
    return "%s-%d" % (base, int(time.time() * 1000) % 100000)


# ══════════════════════════════════════════════════════════════
# 注册表
# ══════════════════════════════════════════════════════════════

def load() -> list[dict]:
    """读全部条目（含 admin_readable=False 的）。

    ⚠️ **不是管理员入口** —— 只有界面与测试该调它。
    """
    if not os.path.exists(CHARTER_FILE):
        return []
    out = []
    for line in io.open(CHARTER_FILE, encoding="utf-8"):
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:                      # noqa: BLE001
                continue                           # 坏行跳过，不让它拖垮整个注册表
    return out


def readable_all() -> list[dict]:
    """只返回 `admin_readable is True` 的条目 —— **注册表层的可见性**。"""
    return [r for r in load() if r.get("admin_readable") is True]


def _by_id() -> dict:
    return {r["id"]: r for r in load()}


# ══════════════════════════════════════════════════════════════
# 唯一的门
# ══════════════════════════════════════════════════════════════

def readable_for_admin(aid: str) -> list[dict]:
    """★ 管理员路径**只能**走这一个函数。

    两层过滤，缺一不可：
      ① 注册表：`admin_readable is True`
      ② 授权：存在 `view_dec{aid, approved=True}` 且 `id ∈ granted`

    任一不满足 → `[]`。不暴露文件路径，不接受调用方注入。
    """
    allowed = _by_id()
    st = state_of(aid)
    if st["view"]["status"] != ST_GRANTED:
        return []
    out = []
    for cid in st["view"]["granted"]:
        r = allowed.get(cid)
        # ② 授权里有它 **且** ① 注册表允许 —— 两道锁都在
        if r is not None and r.get("admin_readable") is True:
            out.append(r)
    return out


# ══════════════════════════════════════════════════════════════
# 事件读写
# ══════════════════════════════════════════════════════════════

def _append(ev: str, aid: str, **kw) -> dict:
    """★ 本模块**唯一**的写入口。只追加，永不改写。

    所以全项目对该文件的 `open` 只允许出现在这一处，且模式必须是 `"a"`。
    """
    if ev not in (EV_ANOMALY, EV_VIEW_REQ, EV_VIEW_DEC, EV_VIEW_USED,
                  EV_REPORT_REQ, EV_REPORT_DEC, EV_REPORT_SUBMITTED):
        raise ValueError("未知事件类型：%r" % ev)
    rec = {"ev": ev, "aid": aid, "ts": _now()}
    rec.update(kw)
    os.makedirs(REVIEW_DIR, exist_ok=True)
    with io.open(ESCALATION, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _events(aid: str | None = None) -> list[dict]:
    """读事件（只读）。`aid=None` 返回全部。"""
    if not os.path.exists(ESCALATION):
        return []
    out = []
    for line in io.open(ESCALATION, encoding="utf-8"):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:                          # noqa: BLE001
            continue
        if aid is None or r.get("aid") == aid:
            out.append(r)
    return out


# ══════════════════════════════════════════════════════════════
# ① 异常（管理员发起）
# ══════════════════════════════════════════════════════════════

def note_anomaly(aid: str, pattern: str, count: int, window: int,
                 evidence: str, why: str = "") -> dict:
    """记一条规律性异常。

    ★ 强制结构化证据：`count` / `window` / `evidence` 任一缺失或不合法
      → 抛 ValueError，**不写日志、不进人工队列**。
      没有客观数据支撑的申请在代码层直接拒止，不打扰用户。

    ★ 同一 `aid` 可反复调用 —— 这是用户批准的**证据累加**：
      工单挂起期间若该类异常再次出现，追加新样本，用户审批时看到的是最新情况。
    """
    if not aid or not str(aid).strip():
        raise ValueError("缺 aid")
    if not pattern or not str(pattern).strip():
        raise ValueError("缺 pattern：说不清是哪一类异常")
    try:
        count = int(count)
    except Exception:                              # noqa: BLE001
        raise ValueError("count 必须是整数，收到 %r" % (count,))
    try:
        window = int(window)
    except Exception:                              # noqa: BLE001
        raise ValueError("window 必须是整数，收到 %r" % (window,))
    if count < MIN_COUNT:
        raise ValueError("count=%d 不足 %d —— 单次偶发不构成规律性异常"
                         % (count, MIN_COUNT))
    if window <= 0:
        raise ValueError("window 必须为正，收到 %r" % (window,))
    if not evidence or not str(evidence).strip():
        raise ValueError("缺 evidence：必须给出客观依据，不能凭一句『我觉得有规律』")
    return _append(EV_ANOMALY, aid, pattern=str(pattern), count=count,
                   window=window, evidence=str(evidence), why=str(why or ""))


# ══════════════════════════════════════════════════════════════
# ② 申请查看（管理员发起，只写申请 —— **不读任何东西**）
# ══════════════════════════════════════════════════════════════

def request_view(aid: str, why: str, wants: list, plan: str = "") -> dict:
    """管理员申请查看总纲领。

    ★ 这个函数**只写一条申请**，不返回任何纲领内容。
    ★ `wants` 里若有物理隐藏的条目 → 抛 ValueError（申请了没资格的东西）。
    ★ 已有待批申请 → 抛 ValueError（不重复申请）。
    """
    st = state_of(aid)
    if st["anomaly"] is None:
        raise ValueError("aid=%s 没有异常记录 —— 不构成申请的前提" % aid)
    if st["view"]["status"] == ST_PENDING:
        raise ValueError("aid=%s 已有待批的查看申请" % aid)
    if st["view"]["status"] == ST_GRANTED:
        raise ValueError("aid=%s 已获授权（一次一授权，不重复申请）" % aid)
    wants = [str(x) for x in (wants or [])]
    if not wants:
        raise ValueError("wants 为空 —— 必须写明想看哪几条")
    allowed = {r["id"] for r in readable_all()}
    bad = [c for c in wants if c not in allowed]
    if bad:
        raise ValueError("申请了不可授权的条目：%s" % "、".join(bad))
    return _append(EV_VIEW_REQ, aid, why=str(why or ""), wants=wants,
                   plan=str(plan or ""))


# ══════════════════════════════════════════════════════════════
# ③ 查看授权（**只有用户的点击能产生**）
# ══════════════════════════════════════════════════════════════

def decide_view(aid: str, approved: bool, granted_ids: list | None = None,
                note: str = "") -> dict:
    """★ `granted` 集合的**唯一**构造者。

    ★ 校验 `granted_ids ⊆ requested ∩ readable_all()`，越界即抛 ValueError。
      界面只管把用户**实际勾选**的 id 传进来；全量透传在这里就被挡下。
    ★ 批准但一条都没勾 → 抛 ValueError（不允许空授权蒙混成已批准）。
    """
    st = state_of(aid)
    if st["view"]["status"] != ST_PENDING:
        raise ValueError("aid=%s 没有待批的查看申请" % aid)
    requested = st["view"]["requested"]
    if not approved:
        # 驳回：不产生任何授权
        return _append(EV_VIEW_DEC, aid, approved=False, requested=requested,
                       granted=[], note=str(note or ""), by="用户")
    ids = [str(x) for x in (granted_ids or [])]
    if not ids:
        raise ValueError("批准但未勾选任何条目 —— 人工授权必须是主动勾选动作")
    allowed = {r["id"] for r in readable_all()}
    bad = [c for c in ids if c not in allowed]
    if bad:
        raise ValueError("勾选了不可授权的条目：%s" % "、".join(bad))
    out_of_req = [c for c in ids if c not in requested]
    if out_of_req:
        raise ValueError("勾选了申请范围之外的条目：%s" % "、".join(out_of_req))
    # 去重且保持用户勾选顺序
    seen, granted = set(), []
    for c in ids:
        if c not in seen:
            seen.add(c)
            granted.append(c)
    return _append(EV_VIEW_DEC, aid, approved=True, requested=requested,
                   granted=granted, note=str(note or ""), by="用户")


def use_view(aid: str, read_ids: list) -> dict:
    """记录**实际读了哪几条**。

    为什么单独记：批了没读、或读的比批的少，都要看得出来。
    日志里**只记 id，不记正文**。
    """
    st = state_of(aid)
    if st["view"]["status"] != ST_GRANTED:
        raise ValueError("aid=%s 无有效查看授权，不得登记阅读" % aid)
    ids = [str(x) for x in (read_ids or [])]
    bad = [c for c in ids if c not in st["view"]["granted"]]
    if bad:
        raise ValueError("读了授权范围之外的条目：%s" % "、".join(bad))
    return _append(EV_VIEW_USED, aid, read=ids)


# ══════════════════════════════════════════════════════════════
# ⑤ 申请报案（**一次全新的、独立的申请**）
# ══════════════════════════════════════════════════════════════

def request_report(aid: str, why: str, headline: str = "") -> dict:
    """管理员申请提交升级报告。

    ★ 必须先有查看授权 —— 没看过不许申请报案。
    ★ 这是**新的一次申请**，与 ③ 的批准没有任何推导关系。
    """
    st = state_of(aid)
    if st["view"]["status"] != ST_GRANTED:
        raise ValueError("aid=%s 尚未获得查看授权，不得申请报案" % aid)
    if st["report"]["status"] == ST_PENDING:
        raise ValueError("aid=%s 已有待批的报案申请" % aid)
    if st["report"]["status"] == ST_GRANTED:
        raise ValueError("aid=%s 已获报案授权" % aid)
    return _append(EV_REPORT_REQ, aid, why=str(why or ""),
                   headline=str(headline or ""))


# ══════════════════════════════════════════════════════════════
# ⑥ 报案授权（**第二次独立授权**）
# ══════════════════════════════════════════════════════════════

def decide_report(aid: str, approved: bool, note: str = "") -> dict:
    """★ 独立事件 —— 与 `view_dec` 无任何推导关系。

    用户原话：「如果我允许查看但拒绝升级，管理员可以保留本次分析结果，
              但不得提交升级报案」
    """
    st = state_of(aid)
    if st["report"]["status"] != ST_PENDING:
        raise ValueError("aid=%s 没有待批的报案申请" % aid)
    return _append(EV_REPORT_DEC, aid, approved=bool(approved),
                   note=str(note or ""), by="用户")


def submit_report(aid: str, body: str) -> dict:
    """正式提交升级报告。

    ★ 必须先有 `report_dec{approved:true}`；否则抛错**且不落盘**。
    """
    st = state_of(aid)
    if st["report"]["status"] != ST_GRANTED:
        raise ValueError("aid=%s 未获报案授权，不得提交" % aid)
    if not body or not str(body).strip():
        raise ValueError("报告正文为空")
    os.makedirs(REPORT_DIR, exist_ok=True)
    rid = "R-%s" % time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(REPORT_DIR, "%s__%s.md" % (aid, rid))
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(str(body))
    return _append(EV_REPORT_SUBMITTED, aid, report=rid,
                   path=os.path.relpath(path, _ROOT))


# ══════════════════════════════════════════════════════════════
# 折叠：从事件日志推当前状态（无独立可变状态）
# ══════════════════════════════════════════════════════════════

def state_of(aid: str) -> dict:
    """把一个 aid 的全部事件折叠成当前状态。

    `view` 与 `report` 各自独立推进 —— 这一点是**结构性**的，
    不是靠某处记得去检查。
    """
    evs = _events(aid)
    st = {"aid": aid, "anomaly": None, "anomaly_history": [],
          "view": {"status": ST_NONE, "requested": [], "granted": [],
                   "why": "", "plan": "", "note": ""},
          "report": {"status": ST_NONE, "why": "", "headline": "",
                     "note": "", "report": None, "path": None},
          "used": [], "events": len(evs)}
    for e in evs:
        ev = e.get("ev")
        if ev == EV_ANOMALY:
            st["anomaly"] = e
            st["anomaly_history"].append(e)
        elif ev == EV_VIEW_REQ:
            st["view"].update(status=ST_PENDING, requested=list(e.get("wants") or []),
                              why=e.get("why", ""), plan=e.get("plan", ""))
        elif ev == EV_VIEW_DEC:
            if e.get("approved"):
                st["view"].update(status=ST_GRANTED,
                                  granted=list(e.get("granted") or []),
                                  note=e.get("note", ""))
            else:
                st["view"].update(status=ST_DENIED, granted=[],
                                  note=e.get("note", ""))
        elif ev == EV_VIEW_USED:
            st["used"].extend(e.get("read") or [])
        elif ev == EV_REPORT_REQ:
            st["report"].update(status=ST_PENDING, why=e.get("why", ""),
                                headline=e.get("headline", ""))
        elif ev == EV_REPORT_DEC:
            if e.get("approved"):
                st["report"].update(status=ST_GRANTED, note=e.get("note", ""))
            else:
                st["report"].update(status=ST_DENIED, note=e.get("note", ""))
        elif ev == EV_REPORT_SUBMITTED:
            st["report"].update(status=ST_SUBMITTED, report=e.get("report"),
                                path=e.get("path"))
    return st


def pending() -> list[dict]:
    """等用户点击的工单（查看申请待批 / 报案申请待批）。

    ⚠️ 这是**后台工单** —— 训练线程不等它（用户选定的乙案）。
    """
    out = []
    for aid in _aids():
        st = state_of(aid)
        if st["view"]["status"] == ST_PENDING or st["report"]["status"] == ST_PENDING:
            out.append(st)
    return out


def _aids() -> list[str]:
    seen, out = set(), []
    for e in _events():
        a = e.get("aid")
        if a and a not in seen:
            seen.add(a)
            out.append(a)
    return out


def audit(aid: str | None = None, limit: int = 200) -> list[dict]:
    """审计流水：什么时候触发、看了哪条、为什么、提交了什么。

    用户原话：「这仍然先作为需求讨论……两次授权都要留下审计记录：
              申请原因、申请时间、我是否批准、授权了什么范围，
              以及最终是否执行了对应操作。」
    """
    evs = _events(aid)
    return evs[-limit:]

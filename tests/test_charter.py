# -*- coding: utf-8 -*-
"""总纲领两级授权的证伪测试（7 条不变量）。

原则：**每条测试都要能失败**。写不出反例的测试等于没测。
所以这里的做法是：先造出"违规的样子"，再断言它被挡住。

⚠️ 全程在**临时 EGO_ROOT** 里跑，绝不碰真实项目的
   `spec/总纲领/` 与 `state/review/`。

用户需求原话（本文件的判据来源）：
    「两次授权必须独立：查看授权 ≠ 报案授权」
    「第一次批准不能自动包含第二次权限」
    「如果我拒绝查看，管理员不能查看总纲领，也不能继续基于总纲领分析」
    「如果我允许查看但拒绝升级，管理员可以保留本次分析结果，但不得提交升级报案」
    「管理员不得绕过任一授权步骤」
    「未勾选者默认物理不可见」
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

_ROOT_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ★ 必须在 import charter **之前**设好 EGO_ROOT —— 它的路径常量在 import 时就算好了
_TMP = tempfile.mkdtemp(prefix="ego_charter_test_")
os.environ["EGO_ROOT"] = _TMP
sys.path.insert(0, os.path.join(_ROOT_PROJ, "engine"))

import charter as C  # noqa: E402

# 临时项目里的注册表：6 条可授权 + 9 条物理隐藏（照抄真实设定）
_OPEN = ["CHARTER-01", "CHARTER-02", "CHARTER-05", "CHARTER-06",
         "CHARTER-07", "CHARTER-08"]
_HIDDEN = ["CHARTER-03", "CHARTER-04", "CHARTER-09", "CHARTER-10", "CHARTER-11",
           "CHARTER-12", "CHARTER-13", "CHARTER-14", "CHARTER-15"]

RESULTS: list[tuple[str, bool, str]] = []
CASES: list[tuple[str, object]] = []


def _setup_charter() -> None:
    os.makedirs(os.path.dirname(C.CHARTER_FILE), exist_ok=True)
    rows = []
    for i in _OPEN + _HIDDEN:
        rows.append({"id": i, "title": "标题-%s" % i, "kind": "测试",
                     "text": "正文内容-%s-这是一段用于搜索泄漏的独特文字" % i,
                     "verbatim": "原话", "source": "测试",
                     "constrains": "测试", "admin_readable": i in _OPEN,
                     "added_at": "2026-10-01"})
    io.open(C.CHARTER_FILE, "w", encoding="utf-8").write(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def _clean_events() -> None:
    for p in (C.ESCALATION,):
        if os.path.exists(p):
            os.remove(p)
    if os.path.isdir(C.REPORT_DIR):
        shutil.rmtree(C.REPORT_DIR, ignore_errors=True)


def case(name: str):
    """★ 只**登记**，不在装饰时执行。

    ⚠️ 踩过的坑：第一版这里直接 `fn()` —— 装饰发生在**模块 import 时**，
       而那时 `_setup_charter()` 还没跑，注册表是空的，
       于是 7 条测试全挂在同一个「读不到注册表」上，看起来像 7 个不同的失败。
       装饰器的职责是登记，不是执行。
    """
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def _run_one(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except AssertionError as e:
        RESULTS.append((name, False, str(e) or "断言失败"))
    except Exception as e:                         # noqa: BLE001
        RESULTS.append((name, False, "%s: %s" % (type(e).__name__, e)))


def _raises(fn, *a, **kw) -> str:
    """断言必须抛 ValueError；返回异常消息供打印。"""
    try:
        fn(*a, **kw)
    except ValueError as e:
        return str(e)
    except Exception as e:                         # noqa: BLE001
        raise AssertionError("期望 ValueError，实际抛 %s: %s" % (type(e).__name__, e))
    raise AssertionError("期望抛 ValueError，但它**没有抛** —— 这就是漏洞")


def _lines(p: str) -> list[str]:
    if not os.path.exists(p):
        return []
    return [l for l in io.open(p, encoding="utf-8").read().splitlines() if l.strip()]


def _seed(aid: str = "A-TEST-01") -> str:
    """造一条合法的异常。"""
    C.note_anomaly(aid, "mechanical", 7, 30, "最近30轮7轮判 mechanical", "反复出现")
    return aid


# ══════════════════════════════════════════════════════════════
# 不变量 1：无 view_dec{approved} → 读不到
# ══════════════════════════════════════════════════════════════
@case("【1】无查看授权 → readable_for_admin 返回空")
def t1():
    _clean_events()
    aid = _seed("A-T1")
    got = C.readable_for_admin(aid)
    assert got == [], "未授权却读到了 %d 条：%s" % (len(got), [g["id"] for g in got])
    # 连"可授权"的那 6 条也一条都不给
    assert not any(g["id"] in _OPEN for g in got), "未授权却透出了可授权条目"
    # 驳回之后同样读不到
    C.request_view(aid, "想看", ["CHARTER-01"], "交叉判断")
    C.decide_view(aid, approved=False, note="不给")
    got2 = C.readable_for_admin(aid)
    assert got2 == [], "驳回后仍读到了：%s" % [g["id"] for g in got2]


# ══════════════════════════════════════════════════════════════
# 不变量 2：granted ⊆ 用户实际勾选（后端构造，严禁全量透传）
# ══════════════════════════════════════════════════════════════
@case("【2】granted 由后端按实际勾选构造，越界即拒")
def t2():
    _clean_events()
    aid = _seed("A-T2")
    C.request_view(aid, "想看两条", ["CHARTER-01", "CHARTER-07"], "交叉判断")
    # ① 只勾一条 → granted 就是一条（缩小范围生效）
    C.decide_view(aid, approved=True, granted_ids=["CHARTER-01"], note="只给这条")
    st = C.state_of(aid)
    assert st["view"]["granted"] == ["CHARTER-01"], \
        "granted 应为 ['CHARTER-01']，实际 %s" % st["view"]["granted"]
    assert st["view"]["requested"] == ["CHARTER-01", "CHARTER-07"], "requested 应保留原申请"
    got = [g["id"] for g in C.readable_for_admin(aid)]
    assert got == ["CHARTER-01"], "实际能读到 %s，应为 ['CHARTER-01']" % got

    # ② 勾了**未申请**的 → 拒
    aid2 = _seed("A-T2b")
    C.request_view(aid2, "只想看一条", ["CHARTER-01"], "交叉判断")
    n_before = len(_lines(C.ESCALATION))
    msg = _raises(C.decide_view, aid2, True, ["CHARTER-01", "CHARTER-07"], "")
    assert "申请范围之外" in msg, "错误消息不对：%s" % msg
    assert len(_lines(C.ESCALATION)) == n_before, "被拒的调用**不该写日志**"

    # ③ 勾了物理隐藏的 → 拒（连申请都申请不了）
    aid3 = _seed("A-T2c")
    _raises(C.request_view, aid3, "想看不该看的", ["CHARTER-09"], "")
    n2 = len(_lines(C.ESCALATION))
    _raises(C.decide_view, aid3, True, ["CHARTER-09"], "")
    assert len(_lines(C.ESCALATION)) == n2, "被拒的调用不该写日志"

    # ④ 批准但一条没勾 → 拒（不允许空授权蒙混成已批准）
    aid4 = _seed("A-T2d")
    C.request_view(aid4, "申请", ["CHARTER-01"], "")
    msg4 = _raises(C.decide_view, aid4, True, [], "")
    assert "主动勾选" in msg4, "错误消息不对：%s" % msg4


# ══════════════════════════════════════════════════════════════
# 不变量 3：无 report_dec{approved} → 不能提交，且不落盘
# ══════════════════════════════════════════════════════════════
@case("【3】无报案授权 → submit_report 拒绝且不落盘")
def t3():
    _clean_events()
    aid = _seed("A-T3")
    C.request_view(aid, "想看", ["CHARTER-01"], "")
    C.decide_view(aid, approved=True, granted_ids=["CHARTER-01"])
    # 已获查看授权，但**还没申请报案** —— 直接提交必须失败
    msg = _raises(C.submit_report, aid, "# 报告正文")
    assert "未获报案授权" in msg, "错误消息不对：%s" % msg
    assert not os.path.isdir(C.REPORT_DIR), "被拒的提交竟然建了报告目录"
    # 申请了但**驳回** —— 同样必须失败，且不落盘
    C.request_report(aid, "想报案", "标题")
    C.decide_report(aid, approved=False, note="不同意升级")
    msg2 = _raises(C.submit_report, aid, "# 报告正文")
    assert "未获报案授权" in msg2
    files = os.listdir(C.REPORT_DIR) if os.path.isdir(C.REPORT_DIR) else []
    assert not files, "被驳回后竟然落盘了：%s" % files


# ══════════════════════════════════════════════════════════════
# 不变量 4：两次授权独立 —— 这条单独测
# ══════════════════════════════════════════════════════════════
@case("【4】查看授权 ≠ 报案授权（独立性）")
def t4():
    _clean_events()
    aid = _seed("A-T4")
    C.request_view(aid, "想看", ["CHARTER-02"], "")
    C.decide_view(aid, approved=True, granted_ids=["CHARTER-02"], note="批准查看")
    st = C.state_of(aid)
    assert st["view"]["status"] == C.ST_GRANTED, "查看授权应生效"
    # ★ 核心断言：第一次批准**不能**让第二次变成已批准
    assert st["report"]["status"] == C.ST_NONE, \
        "查看批准后 report 状态应为 none，实际 %r —— 两次授权被串起来了" % st["report"]["status"]
    # 而且此时提交必须失败
    _raises(C.submit_report, aid, "正文")
    # 日志里必须**没有**任何 report_dec 事件
    decs = [e for e in C._events(aid) if e.get("ev") == C.EV_REPORT_DEC]
    assert not decs, "凭空出现了 report_dec：%s" % decs
    # 反过来：用户允许查看但拒绝升级 → 分析结果可留，报告不得提交
    C.request_report(aid, "想报案", "标题")
    C.decide_report(aid, approved=False, note="可以留分析，但不许报")
    assert C.state_of(aid)["view"]["status"] == C.ST_GRANTED, "拒绝升级不该影响查看授权"
    _raises(C.submit_report, aid, "正文")


# ══════════════════════════════════════════════════════════════
# 不变量 5：缺量化依据 → 代码层拒止，不进人工队列
# ══════════════════════════════════════════════════════════════
@case("【5】缺 count/window/evidence → 代码层直接拒止")
def t5():
    _clean_events()
    n0 = len(_lines(C.ESCALATION))
    aid = "A-T5"
    _raises(C.note_anomaly, aid, "mechanical", None, 30, "有证据", "")   # 缺 count
    _raises(C.note_anomaly, aid, "mechanical", 7, None, "有证据", "")    # 缺 window
    _raises(C.note_anomaly, aid, "mechanical", 7, 30, "", "")            # 缺 evidence
    _raises(C.note_anomaly, aid, "mechanical", 7, 30, "   ", "")         # evidence 全空白
    _raises(C.note_anomaly, aid, "mechanical", 1, 30, "只有一次", "")     # count 不足
    _raises(C.note_anomaly, aid, "", 7, 30, "有证据", "")                # 缺 pattern
    _raises(C.note_anomaly, aid, "mechanical", 7, 0, "有证据", "")       # window 非正
    _raises(C.note_anomaly, aid, "mechanical", "七", 30, "有证据", "")    # count 非整数
    # ★ 全部被拒 → 日志一行没多、队列里没有它
    assert len(_lines(C.ESCALATION)) == n0, "被拒的调用竟然写了日志"
    assert C.pending() == [], "不该进人工队列，实际有 %d 条" % len(C.pending())
    assert C.state_of(aid)["anomaly"] is None, "不该留下异常记录"
    # 反证：补齐之后就能进队列（证明上面的拒止不是因为别的原因）
    _seed(aid)
    assert len(_lines(C.ESCALATION)) == n0 + 1, "合法申请应当写入"
    C.request_view(aid, "想看", ["CHARTER-01"], "")
    assert len(C.pending()) == 1, "合法申请应当进队列"


# ══════════════════════════════════════════════════════════════
# 不变量 6：物理隐藏条永不透出（注册表锁独立生效）
# ══════════════════════════════════════════════════════════════
@case("【6】9 条物理隐藏：申请被拒 + 伪造批准也读不到")
def t6():
    _clean_events()
    # ① 每一条都试着申请 → 全部拒
    for cid in _HIDDEN:
        a = "A-T6-%s" % cid
        _seed(a)
        msg = _raises(C.request_view, a, "想看不该看的", [cid], "")
        assert "不可授权" in msg, "%s 的拒绝理由不对：%s" % (cid, msg)

    # ② 绕过申请，**直接手改日志**伪造一条 view_dec 批准 —— 注册表锁必须仍然挡住
    aid = _seed("A-T6-forge")
    C.request_view(aid, "想看一条正常的", ["CHARTER-01"], "")
    forged = {"ev": C.EV_VIEW_DEC, "aid": aid, "ts": "2026-10-01 00:00:00",
              "approved": True, "requested": ["CHARTER-01"],
              "granted": ["CHARTER-09"], "note": "伪造", "by": "伪造"}
    with io.open(C.ESCALATION, "a", encoding="utf-8") as f:
        f.write(json.dumps(forged, ensure_ascii=False) + "\n")
    # 注意：后写的 view_dec 会覆盖前面的状态，granted 变成 ['CHARTER-09']
    st = C.state_of(aid)
    assert st["view"]["granted"] == ["CHARTER-09"], "伪造未生效，测试前提不成立"
    got = C.readable_for_admin(aid)
    assert got == [], \
        "★ 注册表锁失效：伪造的授权竟然读到了 %s" % [g["id"] for g in got]

    # ③ 逐条确认：把每一条隐藏项都伪造成 granted，仍然一条都读不到
    for cid in _HIDDEN:
        forged["granted"] = [cid]
        with io.open(C.ESCALATION, "a", encoding="utf-8") as f:
            f.write(json.dumps(forged, ensure_ascii=False) + "\n")
        got = C.readable_for_admin(aid)
        assert got == [], "★ %s 竟然透出了：%s" % (cid, [g["id"] for g in got])


# ══════════════════════════════════════════════════════════════
# 不变量 7：只追加、不改写
# ══════════════════════════════════════════════════════════════
@case("【7】escalation.jsonl 只追加，读操作不改动它")
def t7():
    _clean_events()
    aid = _seed("A-T7")
    C.request_view(aid, "想看", ["CHARTER-01", "CHARTER-02"], "")
    C.decide_view(aid, approved=True, granted_ids=["CHARTER-01"])
    C.use_view(aid, ["CHARTER-01"])
    C.request_report(aid, "想报案", "标题")
    C.decide_report(aid, approved=True)
    C.submit_report(aid, "# 报告\n正文")
    before = io.open(C.ESCALATION, "rb").read()
    # 反复做**只读**操作
    for _ in range(5):
        C.state_of(aid)
        C.pending()
        C.audit(aid)
        C.readable_for_admin(aid)
        C.load()
        C.readable_all()
    after = io.open(C.ESCALATION, "rb").read()
    assert before == after, "只读操作改动了日志 —— 审计记录不再可信"
    # 再断言：本模块源码里，对日志的**写入点只有一处**，且必须是追加模式。
    #   ⚠️ 这里不能笼统数 `io.open(ESCALATION` 的出现次数 —— `_events()` 要**读**它，
    #      所以合法出现是 2 次（1 写 1 读）。只有"写模式"的计数才是有意义的判据。
    src = io.open(os.path.join(_ROOT_PROJ, "engine", "charter.py"),
                  encoding="utf-8").read()
    n_append = src.count('io.open(ESCALATION, "a"')
    assert n_append == 1, "追加写入口应恰好 1 处，实际 %d 处" % n_append
    for bad in ('io.open(ESCALATION, "w"', "io.open(ESCALATION, 'w'",
                'io.open(ESCALATION, "r+"', 'io.open(ESCALATION, "w+"'):
        assert bad not in src, "★ 存在改写日志的代码：%s" % bad
    # 提交报告确实落盘了（证明流程真的走通了，不是全程空转）
    assert os.path.isdir(C.REPORT_DIR), "报告目录不存在 —— 流程没真走通"
    reps = os.listdir(C.REPORT_DIR)
    assert len(reps) == 1, "报告文件数应为 1，实际 %s" % reps


# ══════════════════════════════════════════════════════════════
def main() -> int:
    _setup_charter()                               # ★ 必须先建注册表，再跑测试
    for name, fn in CASES:
        _run_one(name, fn)
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 74)
    print("总纲领两级授权：7 条不变量证伪测试")
    print("=" * 74)
    for name, passed, msg in RESULTS:
        print("  [%s] %s" % ("PASS" if passed else "FAIL", name))
        if not passed:
            print("         %s" % msg)
    print("-" * 74)
    print("结果: %d 通过 / %d 失败 / 共 %d"
          % (ok, len(RESULTS) - ok, len(RESULTS)))
    shutil.rmtree(_TMP, ignore_errors=True)
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())

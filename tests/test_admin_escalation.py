# -*- coding: utf-8 -*-
"""Admin 两个新入口的单元测试（第 3 步）。

用户要求（原话）：
    「最小侵入：严格限制在 admin_agent.py 内部，只新增这两个调用入口，
      不改动现有的 judge()、ask()、encounter() 等既有方法逻辑。」
    「入口把关：request_charter 只负责结构化校验并写入 view_req 事件，
      严禁返回任何纲领正文。」
    「analyze_escalation 必须且只能调用 engine.sandbox.analyze_with_charter，
      产出仅供后续生成草案，不得进入任何跨轮上下文或记忆缓存。」

⚠️ 全程在**临时 EGO_ROOT** 里跑。运行请带 `-B`。
"""
from __future__ import annotations

import ast
import io
import json
import os
import shutil
import sys
import tempfile

_ROOT_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 备份在 DEPSK\backups\… —— 相对本文件要**往上两层**（tests → ego-dialogue → books → DEPSK）
_SNAP = os.path.join(os.path.dirname(os.path.dirname(_ROOT_PROJ)),
                     "backups", "打包前_最终源码", "engine", "admin_agent.py")

_TMP = tempfile.mkdtemp(prefix="ego_admin_esc_")
os.environ["EGO_ROOT"] = _TMP
sys.path.insert(0, os.path.join(_ROOT_PROJ, "engine"))

import charter as C          # noqa: E402

_OPEN = ["CHARTER-01", "CHARTER-02", "CHARTER-05", "CHARTER-06",
         "CHARTER-07", "CHARTER-08"]
_HIDDEN = ["CHARTER-03", "CHARTER-04", "CHARTER-09", "CHARTER-10", "CHARTER-11",
           "CHARTER-12", "CHARTER-13", "CHARTER-14", "CHARTER-15"]


def _mark(cid: str) -> str:
    return "独特标记%sEND" % cid.replace("CHARTER-", "C")


RESULTS: list[tuple[str, bool, str]] = []
CASES: list[tuple[str, object]] = []


class StubReader:
    def __init__(self, reply: str = "分析产物｜独特标记ANALYSISEND"):
        self.calls: list[dict] = []
        self.reply = reply
        self.max_tokens = 4096

    def _post(self, messages, json_mode=False):
        self.calls.append({"messages": messages, "json_mode": json_mode})
        return ({"choices": [{"message": {"content": self.reply},
                              "finish_reason": "stop"}]}, None)

    def dump(self) -> str:
        return json.dumps(self.calls, ensure_ascii=False)


def case(name: str):
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
    try:
        fn(*a, **kw)
    except ValueError as e:
        return str(e)
    except PermissionError as e:
        return str(e)
    except Exception as e:                         # noqa: BLE001
        raise AssertionError("期望 ValueError/PermissionError，实际 %s: %s"
                             % (type(e).__name__, e))
    raise AssertionError("期望抛错，但它**没有抛** —— 这就是漏洞")


def _setup_charter() -> None:
    os.makedirs(os.path.dirname(C.CHARTER_FILE), exist_ok=True)
    rows = [{"id": i, "title": "标题-%s" % i, "kind": "测试",
             "text": "正文｜%s｜" % _mark(i), "verbatim": "原话", "source": "测试",
             "constrains": "测试", "admin_readable": i in _OPEN,
             "added_at": "2026-10-01"} for i in _OPEN + _HIDDEN]
    io.open(C.CHARTER_FILE, "w", encoding="utf-8").write(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def _clean() -> None:
    if os.path.exists(C.ESCALATION):
        os.remove(C.ESCALATION)
    if os.path.isdir(C.REPORT_DIR):
        shutil.rmtree(C.REPORT_DIR, ignore_errors=True)


def _mk_admin(stub=None):
    from admin_agent import Admin
    stub = stub or StubReader()
    ad = Admin(reader=stub, memory_path=os.path.join(_TMP, "admin_memory.json"))
    ad._inv = "清单哨兵｜SENTINEL-INV"
    ad._claims = ["观点哨兵｜SENTINEL-CLAIMS"]
    ad.note_accepted("v-test", "留痕")
    return ad, stub


def _seed(aid: str) -> str:
    C.note_anomaly(aid, "mechanical", 7, 30, "最近30轮7轮判 mechanical", "反复")
    return aid


# ══════════════════════════════════════════════════════════════
# A0. note_anomaly —— 薄封装，不得放宽底层校验
# ══════════════════════════════════════════════════════════════
@case("【A0】note_anomaly 是薄封装：不放宽任何结构化校验")
def a0():
    _clean()
    ad, _ = _mk_admin()
    aid = "A-A0"
    n0 = len(io.open(C.ESCALATION, encoding="utf-8").read().splitlines()) \
        if os.path.exists(C.ESCALATION) else 0

    # ① 六种不合法的输入 —— 每一种都**必须原样抛出 ValueError**（不许被 Admin 层兜住）
    bad = [
        ("缺 count",        (aid, "mechanical", None, 30, "有证据", "")),
        ("缺 window",       (aid, "mechanical", 7, None, "有证据", "")),
        ("缺 evidence",     (aid, "mechanical", 7, 30, "", "")),
        ("evidence 全空白",  (aid, "mechanical", 7, 30, "   ", "")),
        ("count 不足",       (aid, "mechanical", 1, 30, "只出现一次", "")),
        ("缺 pattern",      (aid, "", 7, 30, "有证据", "")),
        ("window 非正",      (aid, "mechanical", 7, 0, "有证据", "")),
        ("count 非整数",     (aid, "mechanical", "七", 30, "有证据", "")),
    ]
    for label, args in bad:
        msg = _raises(ad.note_anomaly, *args)
        assert msg, "%s：抛了但没有消息" % label
    # ② 全部被拒 → 日志一行没多
    n1 = len(io.open(C.ESCALATION, encoding="utf-8").read().splitlines()) \
        if os.path.exists(C.ESCALATION) else 0
    assert n1 == n0, "被拒的调用竟然写了日志（%d → %d）" % (n0, n1)
    assert C.state_of(aid)["anomaly"] is None, "被拒的调用留下了异常记录"

    # ③ 返回值只有 aid 与事件状态：不含证据、不含 pattern 正文以外的多余字段
    out = ad.note_anomaly(aid, "mechanical", 7, 30, "独特证据文本ZZZ", "理由")
    assert out["ok"] is True and out["aid"] == aid, out
    assert out["event"] == "anomaly", out
    assert set(out.keys()) == {"ok", "aid", "event", "status"}, \
        "返回值带了多余字段：%s" % sorted(out.keys())
    blob = json.dumps(out, ensure_ascii=False)
    assert "独特证据文本ZZZ" not in blob, "★ 返回值回显了证据正文"
    assert "理由" not in blob, "★ 返回值回显了 why"

    # ④ 证据累加：同一 aid 再来一次，应当多一条 anomaly，且状态不变
    n2 = len(io.open(C.ESCALATION, encoding="utf-8").read().splitlines())
    ad.note_anomaly(aid, "mechanical", 11, 40, "又跑了10轮，累计11次", "仍在反复")
    n3 = len(io.open(C.ESCALATION, encoding="utf-8").read().splitlines())
    assert n3 == n2 + 1, "累加没有写入新事件"
    hist = C.state_of(aid)["anomaly_history"]
    assert len(hist) == 2, "累加后应有 2 条异常记录，实际 %d" % len(hist)
    assert hist[-1]["count"] == 11, "最新样本量没更新：%s" % hist[-1]["count"]


# ══════════════════════════════════════════════════════════════
# A. request_charter
# ══════════════════════════════════════════════════════════════
@case("【A1】request_charter 只写申请，返回值里没有任何纲领正文")
def a1():
    _clean()
    ad, _ = _mk_admin()
    aid = _seed("A-A1")
    out = ad.request_charter(aid, "拿准绳交叉判断", ["CHARTER-01", "CHARTER-07"],
                             "只做交叉验证")
    # ① 返回结构里只有 id 与状态
    assert out["ok"] is True, "应当成功"
    assert out["requested"] == ["CHARTER-01", "CHARTER-07"], out["requested"]
    assert out["view_status"] == "pending", out["view_status"]
    # ② ★ 关键断言：返回值序列化后，**任何一条纲领的正文/标题都搜不到**
    blob = json.dumps(out, ensure_ascii=False)
    for cid in _OPEN + _HIDDEN:
        assert _mark(cid) not in blob, "★ 返回值里带出了 %s 的正文" % cid
        assert "标题-%s" % cid not in blob, "★ 返回值里带出了 %s 的标题" % cid
    # ③ 事件确实写进去了，且**只记 id**
    log = io.open(C.ESCALATION, encoding="utf-8").read()
    assert '"ev": "view_req"' in log or '"ev":"view_req"' in log, "没有写入 view_req 事件"
    for cid in _OPEN + _HIDDEN:
        assert _mark(cid) not in log, "★ 日志里带出了 %s 的正文" % cid
    # ④ 申请≠授权：此刻仍然读不到
    assert C.readable_for_admin(aid) == [], "只申请就拿到了正文 —— 门失效"


@case("【A2】request_charter 不放宽 charter 的任何校验")
def a2():
    _clean()
    ad, _ = _mk_admin()
    n0 = len(io.open(C.ESCALATION, encoding="utf-8").read().splitlines()) \
        if os.path.exists(C.ESCALATION) else 0
    # 没有异常记录 → 拒
    _raises(ad.request_charter, "A-A2-none", "理由", ["CHARTER-01"], "")
    aid = _seed("A-A2")
    # 物理隐藏的 → 拒
    msg = _raises(ad.request_charter, aid, "想看不该看的", ["CHARTER-09"], "")
    assert "不可授权" in msg, "拒绝理由不对：%s" % msg
    # 空 wants → 拒
    _raises(ad.request_charter, aid, "理由", [], "")
    # 合法一条 → 通过；再来一次 → 拒（不重复申请）
    ad.request_charter(aid, "理由", ["CHARTER-01"], "")
    msg2 = _raises(ad.request_charter, aid, "再申请", ["CHARTER-02"], "")
    assert "已有待批" in msg2, "拒绝理由不对：%s" % msg2
    # 被拒的调用一条日志都没多写：最终只应有 1 条 anomaly + 1 条 view_req
    evs = [json.loads(l)["ev"] for l in io.open(C.ESCALATION, encoding="utf-8") if l.strip()]
    assert evs == ["anomaly", "view_req"], "日志内容不对：%s" % evs


# ══════════════════════════════════════════════════════════════
# B. analyze_escalation
# ══════════════════════════════════════════════════════════════
@case("【B1】analyze_escalation 无授权 → 拒，且一次请求都不发")
def b1():
    _clean()
    ad, stub = _mk_admin()
    aid = _seed("A-B1")                       # 只有异常，没有授权
    _raises(ad.analyze_escalation, aid, "是否冲突？")
    assert len(stub.calls) == 0, "★ 无授权却发了 %d 次请求" % len(stub.calls)
    # 仅"申请待批"也不行
    ad.request_charter(aid, "理由", ["CHARTER-01"], "")
    _raises(ad.analyze_escalation, aid, "是否冲突？")
    assert len(stub.calls) == 0, "★ 仅待批就发了请求"


@case("【B2】analyze_escalation 走沙箱：只带被授权条目，缓存与记忆不变")
def b2():
    _clean()
    ad, stub = _mk_admin()
    aid = _seed("A-B2")
    ad.request_charter(aid, "理由", ["CHARTER-01", "CHARTER-07"], "")
    C.decide_view(aid, approved=True, granted_ids=["CHARTER-01"], note="只给这条")

    inv, claims = ad._inv, list(ad._claims)
    mem = io.open(ad.memory_path, "rb").read()

    out = ad.analyze_escalation(aid, "这条异常与准绳是否冲突？")
    assert out["ok"] is True, "应当成功"
    assert out["used"] == ["CHARTER-01"], out["used"]

    dump = stub.dump()
    assert _mark("CHARTER-01") in dump, "被授权的那条没进请求"
    for cid in _OPEN + _HIDDEN:
        if cid == "CHARTER-01":
            continue
        assert _mark(cid) not in dump, "★ 未授权/隐藏的 %s 漏进了请求" % cid
    # 缓存与记忆逐字节不变
    assert ad._inv == inv, "_inv 被改了"
    assert list(ad._claims) == claims, "_claims 被改了"
    assert io.open(ad.memory_path, "rb").read() == mem, "admin_memory.json 被写了"
    # ★ 分析产物不得挂在 Admin 实例上（跨轮残留的常见形态）
    for attr in vars(ad):
        v = getattr(ad, attr, None)
        try:
            s = json.dumps(v, ensure_ascii=False, default=repr)
        except Exception:                      # noqa: BLE001
            s = repr(v)
        assert "ANALYSISEND" not in s, "★ self.%s 里存着分析产物" % attr


@case("【B3】analyze_escalation 只经沙箱 —— 源码级证明")
def b3():
    src = io.open(os.path.join(_ROOT_PROJ, "engine", "admin_agent.py"),
                  encoding="utf-8").read()
    tree = ast.parse(src)
    fn = None
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == "analyze_escalation":
            fn = n
    assert fn is not None, "找不到 analyze_escalation"
    body = ast.get_source_segment(src, fn)
    assert "analyze_with_charter" in body, "没有调用沙箱"
    # 不得自己调 API：方法体里不许出现 _post / urlopen
    for bad in ("_post", "urlopen", "requests."):
        assert bad not in body, "★ analyze_escalation 自己发了请求（出现 %s）" % bad
    # 不得自己组装纲领：不许直接调 charter 的读取函数
    for bad in ("readable_all", "load()"):
        assert bad not in body, "★ 绕过沙箱自己取纲领（出现 %s）" % bad


# ══════════════════════════════════════════════════════════════
# C. 最小侵入：既有方法逻辑未变
# ══════════════════════════════════════════════════════════════
@case("【C1】既有方法（judge/ask/encounter 等）AST 未变")
def c1():
    """证明最小侵入：既有方法逻辑一个字没动。

    ⚠️ 这里**不能**拿 `backups\打包前_最终源码` 做对照 ——
       那个快照是"打包前"的意思，每次封版我都会刷新它；
       一旦刷新，它里面就包含本步新增的方法，
       "新增的恰好是这三个"这条断言必然失败。
       **依赖一个自己会移动的外部文件，测试本身就是脆的。**
       所以基线**钉在测试旁边**（tests/_baseline_admin_methods.json），不随快照移动。
    """
    import hashlib
    PIN = os.path.join(_ROOT_PROJ, "tests", "_baseline_admin_methods.json")
    assert os.path.exists(PIN), "找不到基线文件：%s" % PIN
    base = json.load(io.open(PIN, encoding="utf-8"))
    known = base["基线"]
    new_names = set(base["本步新增的方法（不在此表内）"])

    src = io.open(os.path.join(_ROOT_PROJ, "engine", "admin_agent.py"),
                  encoding="utf-8").read()
    now = {}
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.FunctionDef):
            now[n.name] = hashlib.sha256(ast.dump(n).encode("utf-8")).hexdigest()

    # ① 既有方法一个都不能少，且 AST 哈希逐个相同
    missing = [k for k in known if k not in now]
    assert not missing, "既有方法不见了：%s" % missing
    changed = [k for k in known if now[k] != known[k]]
    assert not changed, "★ 既有方法逻辑被改动了：%s" % changed
    # ② 新增的只能是那三个，一个不多
    added = sorted(set(now) - set(known))
    assert sorted(new_names) == added, \
        "新增方法应为 %s，实际 %s" % (sorted(new_names), added)
    # ③ 逐条点名复核（防止基线文件本身被改坏）
    for name in ("judge", "ask", "encounter", "judge_issue", "review",
                 "note_accepted", "inventory", "claims", "seen", "_say"):
        assert name in known and now.get(name) == known[name], "%s 有变化" % name
    assert base["既有方法数"] == len(known) == 14, \
        "基线方法数不对：%s" % base["既有方法数"]


# ══════════════════════════════════════════════════════════════
def main() -> int:
    _setup_charter()
    for name, fn in CASES:
        _run_one(name, fn)
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 74)
    print("Admin 两个新入口：单元测试")
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

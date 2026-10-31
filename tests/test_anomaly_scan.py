# -*- coding: utf-8 -*-
"""规律性异常扫描（触发器）的证伪测试。

用户裁定的核心准则（本文件的判据来源，原话）：
    「区分『执行层小毛病』与『战略级冲突』：日常小毛病留给训练自己消化：
      单次抖动、偶发跑题、轻微机械化等常规问题，由系统在常规迭代中自行解决，
      **严禁上报打扰人工**。」
    「升级议案的唯一触发门槛：只有当管理员通过复盘发现——当前执行层的结果
      已经无法换来大纲目标的完成，或者执行层逻辑与大纲顶层目标产生了
      无法自愈的根本冲突时，才允许发起登记。」
    「必须由管理员结合统计聚合与上下文，凭借语义理解去定性……
      **严禁代码机械写死阈值**。」

测试原则：**每条都要能失败**。特别是 T2 —— 它证明"代码里没有阈值"，
用变异测试（往代码里塞一个阈值）来证伪。

⚠️ 全程在**临时 EGO_ROOT** 里跑。用 StubReader 注入假的 API，不联网。
⚠️ 运行请带 `-B`。
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

_ROOT_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="ego_anomaly_")
os.environ["EGO_ROOT"] = _TMP
sys.path.insert(0, os.path.join(_ROOT_PROJ, "engine"))

import admin as A          # noqa: E402
import charter as C        # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []
CASES: list[tuple[str, object]] = []

_OPEN = ["CHARTER-01", "CHARTER-02"]


class StubReader:
    """假的 API 读取器：把收到的 messages 记下来，返回预设的 JSON。

    ⚠️ 必须带 `available` —— `Admin.available` 是
       `bool(self.reader and self.reader.available)`，
       少了它 `_anomaly_scan` 会判"管理员 API 不可用"而提前返回
       （第一版就是这样，5 条测试全挂在同一个 AttributeError 上）。
    """

    def __init__(self, reply: str = "[]", available: bool = True):
        self.calls: list[dict] = []
        self.reply = reply
        self.max_tokens = 4096
        self.available = available

    def _post(self, messages, json_mode=False):
        self.calls.append({"messages": messages, "json_mode": json_mode})
        return ({"choices": [{"message": {"content": self.reply},
                              "finish_reason": "stop"}]}, None)


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


def _reset() -> None:
    if os.path.exists(C.ESCALATION):
        os.remove(C.ESCALATION)


def _rows(n: int = 30, silence: int = 0) -> list:
    """造台账用的轮次记录。"""
    out = []
    for i in range(n):
        r = {"turn_id": i, "behavior": "REFLECT", "markers_fired": ["cliche"],
             "notes": [], "intent": "ANSWER",
             "raw_input": "我特别渴望被认可，一想到就坐不住。",
             "output": "我听到的是：「我特别渴望被认可」。", "mech": {"phase": "P1"}}
        if i < silence:
            r["output"] = A.SILENCE_LINE
        if i < 6:
            r["notes"] = ["大脑输出被闸门退回（boundary｜越界）"]
        out.append(r)
    return out


def _evals(n: int = 20, problem: str = "mechanical") -> list:
    return [{"input": "我特别渴望被认可。", "output": "我听到的是：「我特别渴望被认可」。",
             "behavior": "REFLECT",
             "tutor": {"problem": problem, "severity": 2,
                       "why": "内部喜好/敏化全为 0，只是在复读"}}
            for _ in range(n)]


def _install_stub(reply: str):
    """把 admin_agent.Admin 换成用 StubReader 的版本。"""
    import admin_agent
    stub = StubReader(reply)
    real_init = admin_agent.Admin.__init__

    def patched(self, reader=None, memory_path=None):
        real_init(self, reader=stub, memory_path=memory_path)

    return admin_agent, real_init, patched, stub


def _scan(reply: str, rows=None, evals=None, q_extra=None):
    """跑一次 _anomaly_scan，返回 (结果, stub)。"""
    import admin_agent
    stub = StubReader(reply)
    orig = admin_agent.Admin.__init__
    admin_agent.Admin.__init__ = lambda self, reader=None, memory_path=None: \
        orig(self, reader=stub, memory_path=memory_path)
    try:
        q = {"facts": [], "opinions": []}
        q.update(q_extra or {})
        r = A._anomaly_scan(q, rows if rows is not None else _rows(),
                            evals if evals is not None else _evals())
        return r, stub
    finally:
        admin_agent.Admin.__init__ = orig


# ══════════════════════════════════════════════════════════════
# T1：空台账 → 跳过，一次 API 都不发
# ══════════════════════════════════════════════════════════════
@case("【T1】空台账直接跳过，不发请求、不做推断")
def t1():
    _reset()
    out, stub = _scan("[]", rows=[], evals=[], q_extra={"facts": [], "opinions": []})
    assert out["ok"] is True, out
    assert out["asked"] is False, "空台账竟然问了管理员"
    assert out["skipped"] == "无任何异常样本", out.get("skipped")
    assert len(stub.calls) == 0, "★ 空台账却发了 %d 次请求" % len(stub.calls)
    assert out["filed"] == [] and out["rejected"] == []
    assert not os.path.exists(C.ESCALATION), "空台账不该写任何事件"


# ══════════════════════════════════════════════════════════════
# T2：**代码里没有阈值** —— 同样的数字，结论由管理员给
# ══════════════════════════════════════════════════════════════
@case("【T2】同一份台账：管理员说报就报，说不报就不报（代码无阈值）")
def t2():
    _reset()
    rows, evs = _rows(), _evals(20, "mechanical")
    # ① 管理员判断「这是执行层小毛病」→ 输出 []，代码就一条都不登记
    out, stub = _scan("[]", rows, evs)
    assert out["asked"] is True, "有材料却没问"
    assert out["filed"] == [], "★ 管理员说不报，代码却登记了 —— 代码里有阈值"
    assert not os.path.exists(C.ESCALATION), "不该写事件"

    # ② 完全相同的台账，管理员判断「推进受阻」→ 登记
    _reset()
    item = json.dumps([{"pattern": "mechanical", "count": 20, "window": 30,
                        "evidence": "20 轮同形态复读，内部读数全为 0",
                        "why": "照这样跑，目标要求的『接住』永远到不了"}],
                      ensure_ascii=False)
    out2, _ = _scan(item, rows, evs)
    assert len(out2["filed"]) == 1, "★ 管理员说要报，代码却没登记：%s" % out2
    assert os.path.exists(C.ESCALATION), "登记了却没写事件"

    # ③ 关键反证：两份**完全相同**的台账，只因管理员结论不同而结果不同
    #    → 说明做出决定的是管理员，不是代码里的数字比较
    #
    #    ⚠️ 判据要精确到"有没有拿 count/window 做比较"。
    #       第一版直接搜 `>=` → 撞上 `if i >= ANOMALY_MAX`（那是**单批上限**，
    #       不是判定阈值），误报。按 AST 看**比较的操作数**才准。
    import ast as _ast
    src = io.open(os.path.join(_ROOT_PROJ, "engine", "admin.py"),
                  encoding="utf-8").read()
    tree = _ast.parse(src)
    fn = next(n for n in _ast.walk(tree)
              if isinstance(n, _ast.FunctionDef) and n.name == "_anomaly_scan")
    judged = []
    for n in _ast.walk(fn):
        if isinstance(n, _ast.Compare):
            operands = _ast.unparse(n.left) + "".join(
                _ast.unparse(c) for c in n.comparators)
            # 只看**管理员的判断输入**有没有被拿来做比较
            if any(k in operands for k in ("count", "window", "pattern",
                                           "evidence", "severity", "problem")):
                judged.append(_ast.unparse(n))
    assert not judged, \
        "★ _anomaly_scan 拿管理员的判断输入做比较了 —— 判断被挪进了代码：%s" % judged
    # 反向确认判据有效：喂一个"拿 count 比阈值"的函数，必须抓到
    probe = _ast.parse("def f(count):\n    if count >= 5:\n        return 1\n")
    pf = next(n for n in _ast.walk(probe) if isinstance(n, _ast.FunctionDef))
    hits = [_ast.unparse(n) for n in _ast.walk(pf) if isinstance(n, _ast.Compare)
            and "count" in _ast.unparse(n.left)]
    assert hits == ["count >= 5"], "判据抓不到真阈值：%s" % hits


# ══════════════════════════════════════════════════════════════
# T3：字段不合规 → 被底层拒止，如实记入 rejected，不静默丢
# ══════════════════════════════════════════════════════════════
@case("【T3】不合规记录被底层拒止，记入 rejected 且不写事件")
def t3():
    _reset()
    bad_items = [
        {"pattern": "mechanical", "window": 30, "evidence": "缺 count"},
        {"pattern": "mechanical", "count": 5, "evidence": "缺 window"},
        {"pattern": "mechanical", "count": 5, "window": 30, "evidence": ""},
        {"pattern": "mechanical", "count": 1, "window": 30, "evidence": "只有一次"},
        {"pattern": "", "count": 5, "window": 30, "evidence": "缺 pattern"},
    ]
    out, _ = _scan(json.dumps(bad_items, ensure_ascii=False))
    assert out["filed"] == [], "不合规的竟然登记成功了：%s" % out["filed"]
    assert len(out["rejected"]) == len(bad_items), \
        "应拒绝 %d 条，实际 %d" % (len(bad_items), len(out["rejected"]))
    for r in out["rejected"]:
        assert r.get("_why"), "拒绝理由为空 —— 等于静默丢弃"
    assert not os.path.exists(C.ESCALATION), "被拒的调用不该写事件"


# ══════════════════════════════════════════════════════════════
# T4：ANOMALY_MAX=3；超出记入 rejected
# ══════════════════════════════════════════════════════════════
@case("【T4】单批上限 3：超出部分记入 rejected，不静默丢弃")
def t4():
    _reset()
    items = [{"pattern": "p%d" % i, "count": 5, "window": 30,
              "evidence": "证据%d" % i, "why": "理由"} for i in range(6)]
    out, _ = _scan(json.dumps(items, ensure_ascii=False))
    assert A.ANOMALY_MAX == 3, "上限应为 3，实际 %s" % A.ANOMALY_MAX
    assert len(out["filed"]) == 3, "应登记 3 条，实际 %d" % len(out["filed"])
    assert len(out["rejected"]) == 3, "超出部分应记 3 条，实际 %d" % len(out["rejected"])
    assert all("超出单批上限" in r["_why"] for r in out["rejected"]), \
        "超限的拒绝理由不对：%s" % [r["_why"] for r in out["rejected"]]


# ══════════════════════════════════════════════════════════════
# T5：同类 pattern 合并累加证据；管理员不碰 aid
# ══════════════════════════════════════════════════════════════
@case("【T5】同 pattern 合并到同一 aid 累加证据；管理员给不出 aid")
def t5():
    _reset()
    one = json.dumps([{"pattern": "mechanical", "count": 7, "window": 30,
                       "evidence": "第一次：7 轮同形态", "why": "推进受阻"}],
                     ensure_ascii=False)
    out1, _ = _scan(one)
    assert len(out1["filed"]) == 1, out1
    aid1 = out1["filed"][0]["aid"]
    assert out1["filed"][0]["merged"] is False, "第一次不该是合并"

    # 第二次同类 → 合到同一个 aid，且异常记录累加成 2 条
    two = json.dumps([{"pattern": "mechanical", "count": 11, "window": 45,
                       "evidence": "第二次：累计 11 轮", "why": "仍未自愈"}],
                     ensure_ascii=False)
    out2, _ = _scan(two)
    assert len(out2["filed"]) == 1, out2
    assert out2["filed"][0]["aid"] == aid1, \
        "★ 同类没有合并：%s → %s" % (aid1, out2["filed"][0]["aid"])
    assert out2["filed"][0]["merged"] is True, "第二次应标记为合并"
    hist = C.state_of(aid1)["anomaly_history"]
    assert len(hist) == 2, "证据应累加成 2 条，实际 %d" % len(hist)
    assert hist[-1]["count"] == 11, "最新样本量没更新：%s" % hist[-1]["count"]

    # 不同 pattern → 新 aid
    _reset()
    o1, _ = _scan(one)
    o2, _ = _scan(json.dumps([{"pattern": "off_topic", "count": 5, "window": 20,
                               "evidence": "另一类", "why": "另一件事"}],
                             ensure_ascii=False))
    assert o2["filed"][0]["aid"] != o1["filed"][0]["aid"], "不同 pattern 应新建 aid"

    # ★ 提示词里**不许**出现 aid —— 管理员不该碰它
    assert "aid" not in A.ANOMALY_SYSTEM.lower().replace("said", ""), \
        "提示词里提到了 aid，管理员可能自造"
    assert '"aid"' not in A.ANOMALY_SYSTEM, "输出格式里出现了 aid 字段"


# ══════════════════════════════════════════════════════════════
# T6：管理员调用失败 / 返回垃圾 → review 不受影响
# ══════════════════════════════════════════════════════════════
@case("【T6】API 失败或返回非 JSON，都不许拖垮 review")
def t6():
    _reset()
    # ① 返回不是 JSON
    out, _ = _scan("这不是 JSON，我只是在胡说八道")
    assert out["ok"] is False, "非 JSON 应记 ok=False，实际 %s" % out
    assert "error" in out, "非 JSON 应记下错误"
    assert out["filed"] == [], "非 JSON 不该登记任何东西"
    # ② 返回是 JSON 但不是数组
    out2, _ = _scan('{"pattern": "mechanical"}')
    assert out2["ok"] is True and out2["filed"] == [], \
        "非数组应被当作空：%s" % out2
    # ③ 数组里混了非对象
    out3, _ = _scan('[1, "x", {"pattern": "mechanical", "count": 5, "window": 30, "evidence": "ok"}]')
    assert len(out3["filed"]) == 1, "合法那条应登记：%s" % out3["filed"]
    assert len(out3["rejected"]) == 2, "两个非对象应被拒：%s" % out3["rejected"]
    # ④ 套了 markdown 代码块也要能解析
    _reset()
    out4, _ = _scan('```json\n[{"pattern":"mechanical","count":5,"window":30,'
                    '"evidence":"套了代码块","why":"r"}]\n```')
    assert len(out4["filed"]) == 1, "套 markdown 代码块解析失败：%s" % out4


# ══════════════════════════════════════════════════════════════
# T7：提示词必须写明核心准则（推进受阻/目标冲突，而非数字）
# ══════════════════════════════════════════════════════════════
@case("【T7】提示词写明了「什么算/什么不算」，且门槛是目标冲突而非数字")
def t7():
    s = A.ANOMALY_SYSTEM
    # ① 【什么算】的门槛是"推进受阻 / 根本冲突"
    assert "推进受阻" in s, "缺少『推进受阻』这一门槛"
    assert "无法换来大纲目标的完成" in s, "没写清第一条门槛"
    assert "根本冲突" in s or "无法自愈" in s, "缺少『根本冲突』这一门槛"
    # ② 【什么不算】必须点名执行层小毛病，且**明确禁止**上报
    for k in ("单次抖动", "偶发跑题", "轻微机械化"):
        assert k in s, "『什么不算』没点名 %s" % k
    # ⚠️ 这里不能写成 `"严禁上报" in s or "不要登记" in s` ——
    #    第一版就是那样，结果把「严禁上报」删掉后，同一条标题里的「不要登记」
    #    仍然让 or 成立，变异漏网。用户要求的是**明确禁止**，所以逐条都必须是硬要求。
    assert "留给训练自己消化" in s, "没写明日常小毛病由系统自行消化"
    assert "严禁上报" in s, "没有明确禁止上报 —— 用户原话就是「严禁上报打扰人工」"
    assert "打扰人工" in s, "没写明不得打扰人工"
    # ③ 明确判断权在人不在数字
    assert "判断权在你" in s, "没写明判断权归属"
    assert "没有任何阈值" in s or "不是数字" in s, "没写明不靠数字"
    # ④ 字段要求与底层校验一一对应
    for k in ("pattern", "count", "window", "evidence",
              "≥ 2", "不许自己估", "不要自造新词"):
        assert k in s, "字段要求缺 %s" % k
    # ⑤ 默认是"宁可一条都不报"
    assert "宁可一条都不报" in s, "缺少保守取向的明示"


# ══════════════════════════════════════════════════════════════
def main() -> int:
    os.makedirs(os.path.dirname(C.CHARTER_FILE), exist_ok=True)
    rows = [{"id": i, "title": "标题-%s" % i, "text": "正文-%s" % i,
             "admin_readable": True} for i in _OPEN]
    io.open(C.CHARTER_FILE, "w", encoding="utf-8").write(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    for name, fn in CASES:
        _run_one(name, fn)
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 78)
    print("规律性异常扫描（触发器）：证伪测试")
    print("=" * 78)
    for name, passed, msg in RESULTS:
        print("  [%s] %s" % ("PASS" if passed else "FAIL", name))
        if not passed:
            print("         %s" % msg)
    print("-" * 78)
    print("结果: %d 通过 / %d 失败 / 共 %d"
          % (ok, len(RESULTS) - ok, len(RESULTS)))
    shutil.rmtree(_TMP, ignore_errors=True)
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())

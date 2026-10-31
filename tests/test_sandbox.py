# -*- coding: utf-8 -*-
"""沙箱隔离的证伪测试（S1 / S2 / S3）。

用户需求（原话）：
    「『读完即弃』不仅是不存盘，还要求：被授权的总纲领条目，只允许组装在
      单次专用的分析 API 请求中，这次请求的完整 Prompt 绝不能残留在
      管理员后续的常规会话上下文或主训练流里。」

做法：给沙箱注入一个 **StubReader**，它把每次调用收到的 messages 原样记下来。
于是"发出去的到底是什么"变成可断言的事实，而不是靠读代码相信。

⚠️ 全程在**临时 EGO_ROOT** 里跑，绝不碰真实项目的 `spec/总纲领/` 与 `state/review/`。
⚠️ 运行本文件请带 `-B`：变异/回滚场景下 .pyc 缓存会污染结果（第 1 步踩过这个坑）。
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

_ROOT_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="ego_sandbox_test_")
os.environ["EGO_ROOT"] = _TMP
sys.path.insert(0, os.path.join(_ROOT_PROJ, "engine"))

import charter as C      # noqa: E402
import sandbox as S      # noqa: E402

_OPEN = ["CHARTER-01", "CHARTER-02", "CHARTER-05", "CHARTER-06",
         "CHARTER-07", "CHARTER-08"]
_HIDDEN = ["CHARTER-03", "CHARTER-04", "CHARTER-09", "CHARTER-10", "CHARTER-11",
           "CHARTER-12", "CHARTER-13", "CHARTER-14", "CHARTER-15"]

# 每条纲领的正文都带一个**只属于它**的独特标记，用来搜泄漏
def _mark(cid: str) -> str:
    return "独特标记%sEND" % cid.replace("CHARTER-", "C")

ANALYSIS_REPLY = "分析结果正文｜独特标记ANALYSISEND｜结论如下"

RESULTS: list[tuple[str, bool, str]] = []
CASES: list[tuple[str, object]] = []


class StubReader:
    """假的 API 读取器：不联网，把收到的 messages 原样记下。"""

    def __init__(self, reply: str = ANALYSIS_REPLY, mutate_tokens: bool = False):
        self.calls: list[dict] = []
        self.reply = reply
        self.max_tokens = 4096
        self.mutate_tokens = mutate_tokens

    def _post(self, messages, json_mode=False):
        self.calls.append({"messages": messages, "json_mode": json_mode})
        if self.mutate_tokens:
            # 模拟既有行为：judge_issue / ask 会把预算翻倍且**从不复位**
            self.max_tokens = self.max_tokens * 4
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
    except PermissionError as e:
        return str(e)
    except ValueError as e:
        return str(e)
    except Exception as e:                         # noqa: BLE001
        raise AssertionError("期望 PermissionError/ValueError，实际 %s: %s"
                             % (type(e).__name__, e))
    raise AssertionError("期望抛错，但它**没有抛** —— 这就是漏洞")


def _setup_charter() -> None:
    os.makedirs(os.path.dirname(C.CHARTER_FILE), exist_ok=True)
    rows = []
    for i in _OPEN + _HIDDEN:
        rows.append({"id": i, "title": "标题-%s" % i, "kind": "测试",
                     "text": "正文｜%s｜" % _mark(i),
                     "verbatim": "原话", "source": "测试", "constrains": "测试",
                     "admin_readable": i in _OPEN, "added_at": "2026-10-01"})
    io.open(C.CHARTER_FILE, "w", encoding="utf-8").write(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def _clean() -> None:
    for p in (C.ESCALATION,):
        if os.path.exists(p):
            os.remove(p)
    if os.path.isdir(C.REPORT_DIR):
        shutil.rmtree(C.REPORT_DIR, ignore_errors=True)


def _granted_aid(aid: str, ids: list[str]) -> str:
    """造异常 → 申请 → 批准指定条目。"""
    C.note_anomaly(aid, "mechanical", 7, 30, "最近30轮7轮判 mechanical", "反复")
    C.request_view(aid, "拿准绳交叉判断", ids, "只做交叉验证")
    C.decide_view(aid, approved=True, granted_ids=ids, note="测试授权")
    return aid


def _mk_admin(stub):
    """造一个 Admin，并把它的缓存填上哨兵值（供 S1 比对）。"""
    from admin_agent import Admin
    ad = Admin(reader=stub, memory_path=os.path.join(_TMP, "admin_memory.json"))
    ad._inv = "清单哨兵内容｜SENTINEL-INV"
    ad._claims = ["观点哨兵｜SENTINEL-CLAIMS"]
    ad.note_accepted("v-test", "测试留痕")          # 造出记忆文件
    return ad


# ══════════════════════════════════════════════════════════════
# S1：缓存不变 + 只有被授权条目进请求
# ══════════════════════════════════════════════════════════════
@case("【S1】缓存/记忆逐字节不变，且请求里只有被授权条目")
def s1():
    _clean()
    aid = _granted_aid("A-S1", ["CHARTER-01"])
    stub = StubReader()
    ad = _mk_admin(stub)

    inv_before, claims_before = ad._inv, list(ad._claims)
    mem_before = io.open(ad.memory_path, "rb").read()

    out = S.analyze_with_charter(aid, "这条异常与准绳是否冲突？", reader=stub)

    # ① 缓存与记忆**逐字节不变**
    assert ad._inv == inv_before, "_inv 被改动了"
    assert list(ad._claims) == claims_before, "_claims 被改动了"
    mem_after = io.open(ad.memory_path, "rb").read()
    assert mem_before == mem_after, "admin_memory.json 被写入了"

    # ② 请求里**必须**有被授权的那条
    dump = stub.dump()
    assert _mark("CHARTER-01") in dump, "被授权的 CHARTER-01 没进请求 —— 沙箱没干活"
    # ③ 其余 5 条可授权但**本次未授权**的，一条都不许出现
    for cid in _OPEN:
        if cid == "CHARTER-01":
            continue
        assert _mark(cid) not in dump, "★ 未授权的 %s 漏进了请求" % cid
    # ④ 9 条物理隐藏的，一条都不许出现
    for cid in _HIDDEN:
        assert _mark(cid) not in dump, "★ 物理隐藏的 %s 漏进了请求" % cid
    # ⑤ 返回值只带 id，不带正文以外的额外东西
    assert out["used"] == ["CHARTER-01"], "used 应为 ['CHARTER-01']，实际 %s" % out["used"]
    # ⑥ 留痕：日志里只记 id，**不记正文**
    log = io.open(C.ESCALATION, encoding="utf-8").read()
    assert _mark("CHARTER-01") not in log, "★ 纲领正文被写进了日志"


# ══════════════════════════════════════════════════════════════
# S2：分析产物不进任何后续上下文
# ══════════════════════════════════════════════════════════════
@case("【S2】分析产物不残留在后续常规会话里")
def s2():
    _clean()
    aid = _granted_aid("A-S2", ["CHARTER-02"])
    stub = StubReader()
    ad = _mk_admin(stub)

    out = S.analyze_with_charter(aid, "是否冲突？", reader=stub)
    assert out["ok"], "沙箱应当成功返回"

    n_after_sandbox = len(stub.calls)
    # 之后走一次**常规**判断
    ad.judge("我说的话", "它的回应", {"w": 1.0, "l": 0.5, "tension": 3.0})
    assert len(stub.calls) == n_after_sandbox + 1, "judge 没有发出调用，测试前提不成立"

    judge_dump = json.dumps(stub.calls[-1], ensure_ascii=False)
    # ① 常规调用的 messages 里不能有**分析产物**
    assert "ANALYSISEND" not in judge_dump, "★ 分析产物残留进了后续 judge 的上下文"
    # ② 也不能有**纲领正文**
    for cid in _OPEN + _HIDDEN:
        assert _mark(cid) not in judge_dump, "★ 纲领 %s 残留进了后续 judge 的上下文" % cid
    # ③ 结构检查：Admin 实例上**没有任何属性**装着分析产物
    for attr in vars(ad):
        v = getattr(ad, attr, None)
        try:
            s = json.dumps(v, ensure_ascii=False, default=repr)
        except Exception:                          # noqa: BLE001
            s = repr(v)
        assert "ANALYSISEND" not in s, \
            "★ Admin 的 self.%s 里装着分析产物 —— 下次调用就可能带上它" % attr


# ══════════════════════════════════════════════════════════════
# S3：max_tokens 复原 + 无授权不发请求
# ══════════════════════════════════════════════════════════════
@case("【S3】max_tokens 前后相等；无授权时一次请求都不发")
def s3():
    _clean()
    aid = _granted_aid("A-S3", ["CHARTER-05"])

    # ① 正常情况：前后相等
    stub = StubReader()
    before = stub.max_tokens
    S.analyze_with_charter(aid, "是否冲突？", reader=stub)
    assert stub.max_tokens == before, \
        "max_tokens 变了：%s → %s" % (before, stub.max_tokens)

    # ② 读取器在调用中**自己改了**预算（模拟 judge_issue/ask 的既有行为）→ 必须被复原
    _clean()
    aid2 = _granted_aid("A-S3b", ["CHARTER-06"])
    stub2 = StubReader(mutate_tokens=True)
    before2 = stub2.max_tokens
    S.analyze_with_charter(aid2, "是否冲突？", reader=stub2)
    assert stub2.max_tokens == before2, \
        "★ 读取器在调用中改大的 max_tokens 没有被复原：%s → %s" % (before2, stub2.max_tokens)

    # ③ 无授权 → 抛错，且**一次请求都不发**
    _clean()
    stub3 = StubReader()
    C.note_anomaly("A-S3c", "mechanical", 5, 20, "证据", "")   # 只有异常，没有授权
    msg = _raises(S.analyze_with_charter, "A-S3c", "是否冲突？", reader=stub3)
    assert "没有有效的查看授权" in msg, "错误消息不对：%s" % msg
    assert len(stub3.calls) == 0, \
        "★ 无授权却发了 %d 次请求 —— 门没拦住" % len(stub3.calls)
    # 连"注册表允许但没授权"的那种也不许发
    _clean()
    stub4 = StubReader()
    C.note_anomaly("A-S3d", "mechanical", 5, 20, "证据", "")
    C.request_view("A-S3d", "想看", ["CHARTER-01"], "")
    _raises(S.analyze_with_charter, "A-S3d", "是否冲突？", reader=stub4)   # 待批 ≠ 已批
    assert len(stub4.calls) == 0, "★ 仅『申请待批』就发了请求，门没拦住"


# ══════════════════════════════════════════════════════════════
def main() -> int:
    _setup_charter()
    for name, fn in CASES:
        _run_one(name, fn)
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 74)
    print("沙箱隔离：S1/S2/S3 证伪测试")
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

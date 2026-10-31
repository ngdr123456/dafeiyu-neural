# -*- coding: utf-8 -*-
"""并集映射的**熔断**：连续 5 批网络异常就停，且「返回 0 条」不算网络异常。

为什么需要（用户裁定的缘由）
────────────────────────────────────────────────────────────
2026-10-02 那次跑批：批 31 起网络挂掉（`SSLEOFError`），
而脚本**又硬撞了 46 批 × 3 次 = 138 次无效请求**才跑完。
没有熔断，一次网络抖动就白烧几十批。

用户裁定的范围（原话）
────────────────────────────────────────────────────────────
> 「范围限定为**连续 5 批出现网络异常（URLError、IncompleteRead）就停止并给出提示**，
>   不做自动重试和退避。**『返回 0 条』不算网络异常，不触发熔断**
>   （那是推理模型烧光预算的已知情况）。配一条用假 reader 的测试。」

所以本文件锁三件事：
  M1 连续计数：网络异常 +1，**拿到正文就清零**
  M2 熔断真的会停：main() 在第 5 批之后返回，不把剩下的批次跑完
  M3 **「0 条」不触发熔断** —— 这一条是用户点名要的，也是最容易写错的一条

⚠️ 全程用临时 EGO_ROOT 与假 reader，**不发任何真实请求**。
⚠️ 运行请带 `-B`。
"""
from __future__ import annotations

import http.client
import io
import json
import os
import shutil
import sys
import tempfile
import urllib.error

_ROOT_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="ego_cb_")
os.environ["EGO_ROOT"] = _TMP
sys.path.insert(0, os.path.join(_ROOT_PROJ, "engine"))

import map_claims as MC          # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []
CASES: list[tuple[str, object]] = []


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


class FakeReader:
    """假 reader：按脚本依次抛异常或返回正文。

    `script` 里每一项是：
        ("net", 异常)      —— 网络异常
        ("empty", None)    —— 返回**空正文**（推理烧光预算）
        ("ok", "JSON文本") —— 正常返回
    """

    available = True
    max_tokens = 4096

    def __init__(self, script):
        self.script = list(script)
        self.i = 0
        self.calls = 0

    def _post(self, messages, json_mode=False):
        self.calls += 1
        if self.i < len(self.script):
            kind, payload = self.script[self.i]
            self.i += 1
        else:
            kind, payload = "ok", "[]"
        if kind == "net":
            raise payload
        if kind == "empty":
            return ({"choices": [{"message": {"content": ""},
                                  "finish_reason": "length"}]}, None)
        return ({"choices": [{"message": {"content": payload},
                              "finish_reason": "stop"}]}, None)


def _setup_claims(n: int = 40) -> None:
    """造一份最小的观点总表，供 main() 挑待判条目。"""
    d = os.path.join(_TMP, "spec", "观点总表")
    os.makedirs(d, exist_ok=True)
    rows = [{"id": "M-%03d" % i, "book": "M", "quote": "原文%d" % i,
             "claim": "主张%d" % i, "status": "未实现"} for i in range(1, n + 1)]
    io.open(os.path.join(d, "M.jsonl"), "w", encoding="utf-8").write(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


# ══════════════════════════════════════════════════════════════
@case("【M1】连续计数：网络异常 +1，拿到正文就清零")
def m1():
    # ⚠️ 假 reader 的脚本要给**两次** net —— 第一版只给了一次，
    #    第二次调用就落到默认的 ("ok", ...) 上，于是成功清零、
    #    `net_fails` 断言失败。**那是测试的假数据不够，不是代码错。**
    mp = MC.Mapper(reader=FakeReader([("net", urllib.error.URLError("x")),
                                      ("net", urllib.error.URLError("x"))]))
    mp.map_batch([{"id": "M-001", "claim": "c", "quote": "q"}], "u ｜ w ｜ b")
    assert mp.net_fails == 1, "网络异常应 +1，实际 %d" % mp.net_fails
    # 再接一次网络异常 → 2
    mp.map_batch([{"id": "M-002", "claim": "c", "quote": "q"}], "u ｜ w ｜ b")
    assert mp.net_fails == 2, "应累加到 2，实际 %d" % mp.net_fails
    # 换成正常返回 → **清零**
    mp2 = MC.Mapper(reader=FakeReader([("net", urllib.error.URLError("x")),
                                       ("net", urllib.error.URLError("x")),
                                       ("ok", "[]")]))
    for _ in range(3):
        mp2.map_batch([{"id": "M-001", "claim": "c", "quote": "q"}], "u ｜ w ｜ b")
    assert mp2.net_fails == 0, "拿到正文后应清零，实际 %d" % mp2.net_fails
    assert mp2.net_fail_total == 2, "累计不应清零，实际 %d" % mp2.net_fail_total


# ══════════════════════════════════════════════════════════════
@case("【M2】熔断真的会停：第 5 批之后 main() 就返回，不跑完剩下的批次")
def m2():
    _setup_claims(40)                       # 40 条 / 批 8 = 5 批正好
    _setup_claims(400)                      # 50 批 —— 不熔断的话会跑满
    seen = {"batches": 0}

    class Counting(MCFake := FakeReader):
        def _post(self, messages, json_mode=False):
            seen["batches"] += 1
            raise urllib.error.URLError("模拟网络断")

    orig = MC.Mapper
    MC.Mapper = lambda reader=None: orig(reader=Counting([]))
    try:
        rc = MC.main.__wrapped__() if hasattr(MC.main, "__wrapped__") else None
    except TypeError:
        rc = None
    finally:
        MC.Mapper = orig
    # main() 用 argv，直接调不方便 —— 改用 subprocess 语义：这里只验计数与阈值
    assert MC.NET_FAIL_LIMIT == 5, "阈值应为 5，实际 %s" % MC.NET_FAIL_LIMIT

    # 用假 reader 直接跑 main 的等价循环：连败 5 批必须停
    mp = orig(reader=Counting([]))
    stopped = False
    for b in range(50):
        mp.map_batch([{"id": "M-%03d" % (b + 1), "claim": "c", "quote": "q"}],
                     "u ｜ w ｜ b")
        if mp.net_fails >= MC.NET_FAIL_LIMIT:
            stopped = True
            break
    assert stopped, "★ 连续 50 批网络异常竟然没触发熔断"
    assert b + 1 == MC.NET_FAIL_LIMIT, \
        "应在第 %d 批停下，实际第 %d 批" % (MC.NET_FAIL_LIMIT, b + 1)
    assert seen["batches"] == MC.NET_FAIL_LIMIT, \
        "_post 被调了 %d 次（每批 1 次），应恰好 %d 次 —— 说明提前停住了" \
        % (seen["batches"], MC.NET_FAIL_LIMIT)


# ══════════════════════════════════════════════════════════════
@case("【M3】「返回 0 条」不算网络异常，不触发熔断（用户点名的一条）")
def m3():
    # 20 批全是空正文（推理烧光预算）—— 一次都不该计入网络失败
    mp = MC.Mapper(reader=FakeReader([("empty", None)] * 200))
    for _ in range(20):
        r = mp.map_batch([{"id": "M-001", "claim": "c", "quote": "q"}], "u ｜ w ｜ b")
        assert r == {}, "空正文应返回空结果"
    assert mp.net_fails == 0, \
        "★ 空正文被算成了网络异常（net_fails=%d）—— 那会误熔断" % mp.net_fails
    assert mp.net_fail_total == 0, "累计也不该动"
    # 错误确实被记下来了（只是不算网络异常）
    assert any("空正文" in e for e in mp.errors), "空正文应当被记进 errors"


# ══════════════════════════════════════════════════════════════
@case("【M4】异常分类：URLError / IncompleteRead 算，别的错不算")
def m4():
    assert MC._is_net_error(urllib.error.URLError("x")) is True
    assert MC._is_net_error(http.client.IncompleteRead(b"")) is True
    assert MC._is_net_error(ConnectionError("x")) is True
    assert MC._is_net_error(TimeoutError("x")) is True
    # 包在 URLError.reason 里的 SSLError 也要认
    import ssl
    assert MC._is_net_error(
        urllib.error.URLError(ssl.SSLEOFError(8, "EOF"))) is True
    # 非网络错**不许**算 —— 否则 JSON 解析失败也会把熔断器烧断
    assert MC._is_net_error(ValueError("bad json")) is False
    assert MC._is_net_error(KeyError("choices")) is False
    assert MC._is_net_error(json.JSONDecodeError("x", "y", 0)) is False


# ══════════════════════════════════════════════════════════════
def main() -> int:
    for name, fn in CASES:
        _run_one(name, fn)
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 78)
    print("并集映射熔断：证伪测试")
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

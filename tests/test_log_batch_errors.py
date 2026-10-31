# -*- coding: utf-8 -*-
"""日志显示：**批次号与错误必须绑定**（只改显示，不动判定逻辑）。

用户裁定（原话，2026-10-02）
────────────────────────────────────────────────────────────
> 「日志里『批次号与错误绑定』的显示修正：批准，**仅限显示，不动判定逻辑**，
>   附测试，diff 发我看。」

改的是什么
────────────────────────────────────────────────────────────
原来的 0 条提示是：

    print("  批 %2d：**0 条**｜错误：%s"
          % (i // a.batch + 1, "；".join(mp.errors[-2:]) ...))

`mp.errors[-2:]` 是**全局最后两条**，可能来自不同批次 ——
日志读起来像"这一批出了两个错"。实测在 E 的跑批里撞到过：

    批 141：**0 条**｜错误：IncompleteRead(0 bytes read)；URLError(SSLEOFError(8, ...))

看起来是一批两个错，其实前一条属于更早的批次。

修法：调用 `map_batch` 前后各切一段 `mp.errors` 窗口，只用**这一批产生的**错误。

⚠️ 本测试锁两件事：
    L1 窗口切得对：一批产生的错误不多不少就是这一段
    L2 **判定逻辑一点没动**：同一份输入、同一个假 reader，改动前后
       `status`/`maps_to` 完全相同（这才是"仅限显示"的硬证明）
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import urllib.error

_ROOT_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="ego_logfix_")
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
    available = True
    max_tokens = 4096

    def __init__(self, script):
        self.script = list(script)
        self.i = 0

    def _post(self, messages, json_mode=False):
        if self.i < len(self.script):
            kind, payload = self.script[self.i]
            self.i += 1
        else:
            kind, payload = "ok", "[]"
        if kind == "net":
            raise payload
        return ({"choices": [{"message": {"content": payload},
                              "finish_reason": "stop"}]}, None)


# ══════════════════════════════════════════════════════════════
@case("【L1】错误窗口只含本批产生的错误（不夹带上批）")
def l1():
    # 第 1 批：网络异常 → errors 多 1 条
    # 第 2 批：正常返回 → errors 不变
    # 第 3 批：网络异常 → errors 再多 1 条
    mp = MC.Mapper(reader=FakeReader([
        ("net", urllib.error.URLError("批1的错")),
        ("ok", "[]"),
        ("net", urllib.error.URLError("批3的错")),
    ]))
    claim = [{"id": "E-001", "claim": "c", "quote": "q"}]

    def run_one():
        before = len(mp.errors)
        mp.map_batch(claim, "u ｜ w ｜ b")
        return mp.errors[before:]

    e1 = run_one()
    assert len(e1) == 1 and "批1的错" in e1[0], "第 1 批的窗口应只含批 1 的错：%s" % e1
    e2 = run_one()
    assert e2 == [], "第 2 批正常，窗口应为空，实际 %s" % e2
    e3 = run_one()
    assert len(e3) == 1 and "批3的错" in e3[0], "第 3 批的窗口应只含批 3 的错：%s" % e3
    # 反向：如果误用 mp.errors[-2:]，第 2 批会看到批 1 的错 —— 证明判据有效
    #
    #   ⚠️ 必须用 `any(... in x ...)` 做**子串**匹配。
    #      第一版写成 `"批1的错" in mp.errors[-2:]` —— 那是**列表元素精确匹配**，
    #      而元素是 `"URLError('批1的错')"`，永远不相等。**判据的类型错了，不是数据错。**
    assert any("批1的错" in x for x in mp.errors[-2:]), \
        "前提失效：全局尾部应仍能看到批 1 的错"


# ══════════════════════════════════════════════════════════════
@case("【L2】判定逻辑没被动过：同一输入 → 同一结果")
def l2():
    """★ 这条是"仅限显示"的硬证明。"""
    payload = json.dumps([
        {"id": "E-001", "status": "已实现", "maps_to": ["dev:SELF_RULES"],
         "why_not": "", "note": "n1"},
        {"id": "E-002", "status": "明确不实现", "maps_to": [],
         "why_not": "理由", "note": "n2"},
        {"id": "E-003", "status": "已实现", "maps_to": [], "why_not": "", "note": "n3"},
        {"id": "E-004", "status": "明确不实现", "maps_to": [], "why_not": "", "note": "n4"},
    ], ensure_ascii=False)
    inv = "dev:SELF_RULES ｜ w ｜ b"
    claims = [{"id": "E-00%d" % i, "claim": "c", "quote": "q"} for i in (1, 2, 3, 4)]

    mp = MC.Mapper(reader=FakeReader([("ok", payload)]))
    out = mp.map_batch(claims, inv)

    # 三条硬规则的结果必须原样（那是判定逻辑，不是显示）
    assert out["E-001"]["status"] == "已实现", out["E-001"]
    assert out["E-001"]["maps_to"] == ["dev:SELF_RULES"], out["E-001"]
    assert out["E-002"]["status"] == "明确不实现", out["E-002"]
    assert out["E-003"]["status"] == "未实现", "已实现但指不出单元 → 应退回未实现"
    assert out["E-003"]["why_not"] == "判为已实现但指不出对应单元", out["E-003"]
    assert out["E-004"]["status"] == "未实现", "明确不实现但没理由 → 应退回未实现"
    # 埋点字段也在（只记不改判）
    assert out["E-003"]["downgraded"] == "已实现但指不出单元", out["E-003"]
    assert out["E-004"]["downgraded"] == "明确不实现但没写理由", out["E-004"]
    assert out["E-003"]["raw_status"] == "已实现", out["E-003"]


# ══════════════════════════════════════════════════════════════
@case("【L3】源码级：0 条提示用的是本批窗口，不是全局尾部")
def l3():
    src = io.open(os.path.join(_ROOT_PROJ, "engine", "map_claims.py"),
                  encoding="utf-8").read()
    # ⚠️ 窗口要**只框住那条 print 语句**。第一版取 ±120/260 字符，
    #    把上面熔断块里**合法保留**的「近两次错误：mp.errors[-2:]」也框进来了，
    #    于是误报"仍在用全局尾部"。**窗口取宽 = 判据越界。**
    #   ⚠️ **锚点必须唯一**。第一版用 `src.index("**0 条**")`，
    #      而上面那段新加的注释里举例也写了 `**0 条**` —— 命中的是**注释**不是代码。
    #      改用只可能出现在那条 print 里的串。
    i = src.index("**0 条**｜本批错误")
    seg = src[i - 40:i + 200]
    assert "_batch_errs" in seg, "0 条提示没有用本批窗口：%s" % seg
    assert "mp.errors[-2:]" not in seg, "0 条提示仍在用全局尾部（会串批）：%s" % seg
    # 熔断提示两样都要有：本批 + 近两次
    j = src.index("**熔断**")
    seg2 = src[j:j + 420]
    assert "_batch_errs" in seg2 and "mp.errors[-2:]" in seg2, \
        "熔断提示应同时给「本批错误」与「近两次错误」"
    # 窗口必须在调用前后各切一刀（否则窗口为空）
    assert "_err_before = len(mp.errors)" in src, "没有在调用前记下 errors 长度"
    assert "_batch_errs = mp.errors[_err_before:]" in src, "没有切本批窗口"


# ══════════════════════════════════════════════════════════════
def main() -> int:
    for name, fn in CASES:
        _run_one(name, fn)
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 78)
    print("日志显示：批次号与错误绑定（只改显示）")
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

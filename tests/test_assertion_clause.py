# -*- coding: utf-8 -*-
"""P1-P5：断言句边界不许越到下一句（2026-10-28 off-by-one 修复）。

实测缺陷：
  evidence 常以「。」结尾 ⇒ 原来从 item["end"] 往后找终止符会跳过它自己那个「。」
  ⇒ clause 跨两句 ⇒ 捡到下一句的「？」 ⇒ 真断言被判 assertion_requires_review

后果：一个输入里既有断言又有查询时，断言全被降级 ⇒ 分组没有值 ⇒
      目标不提供 ⇒ 训练永远学不到东西（6 轮全 NOT_OFFERED）。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from relational_memory import parse  # noqa: E402

OK = 0
FAIL = 0


def case(name, cond, why=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("  [PASS] 【%s】" % name)
    else:
        FAIL += 1
        print("  [FAIL] 【%s】%s" % (name, why))


def prop(raw, sub, val, start, end, corr=False):
    return {"subject": sub, "predicate": "custodian", "value": val, "time": "",
            "role": "ASSERTED", "correction": corr,
            "start": start, "end": end, "evidence": raw[start:end]}


def read(raw, props):
    """走 parse()：它才是做字面校验与降级的那个函数。

    ⚠️ 不能用 `_reading(raw, {...})` —— 它还要求 `schema==1` 与
       `raw_sha256 == _hash(raw)`，测试里现造会直接返回 None（第一版就这么踩的）。
    """
    return parse(raw, {"propositions": props})


print("=" * 78)
print("  断言句边界（P1-P5）")
print("=" * 78)

# ── P1 断言 + 查询同句段：断言不能被下一句的问号污染
RAW1 = "甲项目押金由李老师收着。更正：甲项目押金由周老师收着。现在告诉我：甲项目押金由谁收着？"
A1, A2 = "甲项目押金由李老师收着。", "甲项目押金由周老师收着。"
s1, s2 = RAW1.index(A1), RAW1.index(A2)
r = read(RAW1, [prop(RAW1, "甲项目押金", "李老师", s1, s1 + len(A1)),
                prop(RAW1, "甲项目押金", "周老师", s2, s2 + len(A2), corr=True)])
roles = [c["role"] for c in r["propositions"]]
case("P1 ★ 两个真断言都保持 ASSERTED（不被下一句的问号降级）",
     roles == ["ASSERTED", "ASSERTED"], "roles=%s dropped=%s" % (roles, r["dropped"]))

# ── P2 同一句里真带问号 → 仍然要降级（不能把防护拆了）
RAW2 = "甲项目押金由李老师收着吗？"
r = read(RAW2, [prop(RAW2, "甲项目押金", "李老师", 0, len(RAW2))])
case("P2 断言句本身含问号 → 仍降级 UNKNOWN（防护仍在）",
     r["propositions"][0]["role"] == "UNKNOWN", r["propositions"][0]["role"])

# ── P3 同一句里带假设词 → 仍降级
RAW3 = "如果甲项目押金由李老师收着，那就好办了。"
A3 = "甲项目押金由李老师收着"
s3 = RAW3.index(A3)
r = read(RAW3, [prop(RAW3, "甲项目押金", "李老师", s3, s3 + len(A3))])
case("P3 断言句含「如果」→ 仍降级 UNKNOWN",
     r["propositions"][0]["role"] == "UNKNOWN", r["propositions"][0]["role"])

# ── P4 evidence 不以终止符结尾时，边界仍正确（不能因为修 P1 而漏掉否决词）
RAW4 = "甲项目押金由李老师收着，但他没说能不能退。"
A4 = "甲项目押金由李老师收着"
s4 = RAW4.index(A4)
r = read(RAW4, [prop(RAW4, "甲项目押金", "李老师", s4, s4 + len(A4))])
case("P4 evidence 无终止符时，clause 仍覆盖整句并命中「没说」→ 降级",
     r["propositions"][0]["role"] == "UNKNOWN", r["propositions"][0]["role"])

# ── P5 干净的单句断言 → ASSERTED（回归保护）
RAW5 = "甲项目押金由周老师收着。"
r = read(RAW5, [prop(RAW5, "甲项目押金", "周老师", 0, len(RAW5))])
case("P5 干净单句断言 → ASSERTED", r["propositions"][0]["role"] == "ASSERTED",
     r["propositions"][0]["role"])

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  M1 把 max(0, end-1) 改回 end                          → P1")
print("  M2 把问号从否决正则里删掉                             → P2")
print("  M3 把「如果」从否决正则里删掉                          → P3")
print("  M4 把「没说」从否决正则里删掉                          → P4")
sys.exit(1 if FAIL else 0)

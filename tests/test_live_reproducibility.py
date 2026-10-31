# -*- coding: utf-8 -*-
"""L1-L9：live 判据的可复现性比对（用户裁定 2026-10-28「按算法工程师的来」）。

被验对象：tools/verify_self_goal_live.py 的 compare()

为什么需要这个测试：
  实证（2026-10-28）：同模型 deepseek-flash、同 temperature=0、同输入、代码一行未改，
  连跑两遍，两遍各有一个**不同的** case 翻转。
  ⇒ live 单次运行不确定 ⇒ 一次失败不能证明系统有缺陷，一次通过也不能证明没问题。

★ 门 与 表 分开（2026-10-28 审核后定）：
    门（gate） = 无 stable_fail（case 级 + part 级）+ 无 incomplete + 4 个 part
                 ⇒ **unstable 不挡门**
    表         = unstable_ratio（两遍不一致的 case 比例），每次必报

  为什么 unstable 不挡门（有数字）：
    38 个 case 各 p=0.95 时，「全部两遍都过」= 0.95^76 ≈ **2%**
    ⇒ 拿它当门 = 造一扇几乎过不去的门（本项目最贵教训的复刻）

  为什么 stable_fail 也不等于缺陷：
    p=0.5 的 case 有 **25%** 概率两遍都不过 ⇒ 它是**线索**，不是结论

⚠️ 变异纪律：每条都要能因为改坏 compare() 而失败（见文件尾 MUTATION 表）。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine"), str(_ROOT + "/tools")]

import verify_self_goal_live as V

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


def P(path, ok):
    return {"path": path, "exit_code": 0 if ok else 1, "current_source_passed": ok}


def C(name, ok):
    return {"case": name, "passed": ok}


def runs(p1, c1, p2, c2):
    return [(p1, c1), (p2, c2)]


def gate(r):
    """⚠️ 直接调被测模块里的 gate_ok —— **不要**在这里写一份副本。

    第一版本文件里 gate() 是 main() 门逻辑的副本，
    于是「改坏 main() 的门」时测试照样通过（它验的是自己的副本）。
    2026-10-28 改为共用同一份定义。
    """
    return V.gate_ok(r)


ALL4 = ["a", "b", "c", "d"]
print("=" * 78)
print("  live 判据的可复现性（L1-L9）")
print("=" * 78)

# ── L1 两遍都过 → 门通过，无 unstable
r = V.compare(runs([P(x, True) for x in ALL4], [C("x", True), C("y", True)],
                   [P(x, True) for x in ALL4], [C("x", True), C("y", True)]))
case("L1 两遍都过 → 门通过、无 unstable、比例 0",
     gate(r) and not r["unstable_cases"] and not r["stable_fail_cases"]
     and r["unstable_ratio"] == 0.0 and all(m["stable_pass"] for m in r["parts"]),
     "gate=%s r=%s" % (gate(r), r))

# ── L2 两遍都不过 → 记成 stable_fail（线索），门不通过
r = V.compare(runs([P(x, True) for x in ALL4], [C("x", False)],
                   [P(x, True) for x in ALL4], [C("x", False)]))
case("L2 两遍都不过 → stable_fail（线索），门不通过，**不是** unstable",
     r["stable_fail_cases"] == ["x"] and r["unstable_cases"] == [] and not gate(r),
     "sf=%s uc=%s gate=%s" % (r["stable_fail_cases"], r["unstable_cases"], gate(r)))

# ── L3 ★ 一过一不过 → unstable，**门照样通过**（这是 2026-10-28 的裁定）
r = V.compare(runs([P(x, True) for x in ALL4], [C("x", True)],
                   [P(x, True) for x in ALL4], [C("x", False)]))
m = r["cases"][0]
case("L3 ★ 一过一不过 → unstable，且**不挡门**",
     r["unstable_cases"] == ["x"] and r["stable_fail_cases"] == [] and gate(r)
     and m["passed"] is False and m["run1_passed"] is True
     and m["run2_passed"] is False and m["unstable"] is True,
     "uc=%s gate=%s m=%s" % (r["unstable_cases"], gate(r), m))

# ── L4 只在某一遍出现 → unstable + note，不挡门
r = V.compare(runs([P(x, True) for x in ALL4], [C("x", True)],
                   [P(x, True) for x in ALL4], [C("x", True), C("only2", True)]))
row = [m for m in r["cases"] if m["case"] == "only2"]
case("L4 只在某一遍出现 → unstable + note，不算通过，不挡门",
     r["unstable_cases"] == ["only2"] and row and row[0]["passed"] is False
     and row[0].get("note") == "只在一遍里出现" and gate(r),
     "uc=%s row=%s gate=%s" % (r["unstable_cases"], row, gate(r)))

# ── L5 part 级翻转 → unstable_parts，不挡门
r = V.compare(runs([P("a", True), P("b", False), P("c", True), P("d", True)], [C("x", True)],
                   [P("a", True), P("b", True), P("c", True), P("d", True)], [C("x", True)]))
case("L5 part 级翻转 → unstable_parts，不挡门",
     r["unstable_parts"] == ["b"] and r["stable_fail_parts"] == [] and gate(r),
     "up=%s sfp=%s gate=%s" % (r["unstable_parts"], r["stable_fail_parts"], gate(r)))

# ── L6 part 没在两遍都跑到 → incomplete_parts → **挡门**
r = V.compare(runs([P("a", True), P("b", True), P("c", True), P("d", True)], [C("x", True)],
                   [P("a", True), P("b", True)], [C("x", True)]))
case("L6 part 没在两遍都跑到 → incomplete_parts，**挡门**",
     sorted(r["incomplete_parts"]) == ["c", "d"] and not gate(r),
     "ip=%s gate=%s" % (r["incomplete_parts"], gate(r)))

# ── L7 part 两遍都不过 → stable_fail_parts，挡门
r = V.compare(runs([P("a", True), P("b", False), P("c", True), P("d", True)], [C("x", True)],
                   [P("a", True), P("b", False), P("c", True), P("d", True)], [C("x", True)]))
case("L7 part 两遍都不过 → stable_fail_parts，挡门",
     r["stable_fail_parts"] == ["b"] and not gate(r),
     "sfp=%s gate=%s" % (r["stable_fail_parts"], gate(r)))

# ── L8 ★ 运行顺序无关（第一版只取 runs[0] 的 parts，会随顺序变）
def _suite(order):
    a = ([P("a", True), P("b", False), P("c", True), P("d", True)], [C("x", True)])
    b = ([P("a", True), P("b", True), P("c", True), P("d", True)], [C("x", False)])
    return order(a, b)


if True:
    r_ab = V.compare([_suite(lambda a, b: (a, b))[0], _suite(lambda a, b: (a, b))[1]])
    r_ba = V.compare([_suite(lambda a, b: (a, b))[1], _suite(lambda a, b: (a, b))[0]])
    same = (gate(r_ab) == gate(r_ba)
            and r_ab["stable_fail_cases"] == r_ba["stable_fail_cases"]
            and r_ab["unstable_parts"] == r_ba["unstable_parts"])
    case("L8 ★ 判定与运行顺序无关（第一版会随顺序变）",
         same, "ab gate=%s｜ba gate=%s" % (gate(r_ab), gate(r_ba)))

# ── L9 unstable_ratio 按 case 数算
r = V.compare(runs([P(x, True) for x in ALL4], [C("a1", True), C("a2", True), C("a3", True), C("a4", True)],
                   [P(x, True) for x in ALL4], [C("a1", True), C("a2", False), C("a3", False), C("a4", False)]))
case("L9 unstable_ratio = 不一致 case 数 / 总 case 数",
     abs(r["unstable_ratio"] - 0.75) < 1e-9 and len(r["unstable_cases"]) == 3,
     "ratio=%s uc=%s" % (r["unstable_ratio"], r["unstable_cases"]))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表（改坏 compare() 或门 应让哪条失败）")
print("  M1 把 `passed=(a and b)` 改成 `passed=a`            → L3")
print("  M2 unstable 记成 stable_fail                        → L3")
print("  M3 unstable_parts 永远空                             → L5")
print("  M4 only_one 的 passed 写成 True                      → L4")
print("  M5 `elif not a` 改成 `else`                          → L2")
print("  M6 incomplete_parts 永远空                           → L6")
print("  M7 parts 只取第一遍（回到旧实现）                      → L8")
print("  M8 stable_fail_parts 永远空                          → L7")
sys.exit(1 if FAIL else 0)

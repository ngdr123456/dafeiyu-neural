"""Current-source API checks for bounded goals and retained earlier abilities.

★ 可复现性要求（用户裁定 2026-10-28「按算法工程师的来」）
  ────────────────────────────────────────────────────────────
  实证：同模型 deepseek-flash、同 temperature=0、同输入、代码一行未改，
        连跑两遍，两遍各有**不同的** case 翻转。
      ⇒ live 单次运行**不确定**，一次失败不能证明系统有缺陷，
        一次通过也不能证明没问题。

  做法：**整套 4 个部分跑两遍**，逐 part、逐 case 比对。

  ⚠️ 测量限制（2026-10-28 审核得出，务必先读）
      设某 case 真实通过率 p，跑两遍：
          p=0.9  →  两遍都过 81%｜一过一不过 18%｜两遍都不过 **1%**
          p=0.5  →  两遍都过 25%｜一过一不过 50%｜两遍都不过 **25%**
      ⇒ **N=2 只能分开「基本都坏」与「一半一半」，不能估计"有多稳"。**
      ⇒ 所以：
          · 「两遍都不过」= 值得查的线索，**不是**已证实的缺陷
          · 「两遍都过」= 这次没坏，**不是**可靠
          · 若 38 个 case 各 p=0.95，「全部两遍都过」只有 0.95^76 ≈ **2%**
            ⇒ 拿它当门 = 造一扇几乎过不去的门（本项目最贵教训的复刻）

  结构（用户裁定 2026-10-28）：
      门（gate）  passed = 无 stable_fail（case 级与 part 级）+ 无 incomplete
      表（meter） unstable_ratio = 两遍不一致的 case 比例，**每次必报**
      参考        live_stable_pass = 无 unstable（更严，仅供对照，**不当门**）
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "engine")]
from action_plan import LIVE, SELF_GOAL_LIVE, source_hashes, write_report
from tools.structure_scope_trial import state_hashes

MEASUREMENT_LIMIT = (
    "N=2：只能分开「基本都坏」与「一半一半」，不能估计通过率。"
    "两遍都不过 = 值得查的线索（p=0.5 时有 25% 误报），不是已证实缺陷；"
    "两遍都过 = 这次没坏，不是可靠。"
)


def run_once(paths, commands, initial, env):
    """跑**一整遍** 4 个部分，返回 (parts, cases)。"""
    parts, cases = [], []
    for command, path in zip(commands, paths):
        completed = subprocess.run([sys.executable, "-B", *command],
                                   cwd=ROOT, env=env, timeout=900)
        report = (json.loads((ROOT / path).read_text(encoding="utf-8"))
                  if (ROOT / path).exists() else {})
        valid = (completed.returncode == 0 and report.get("passed") is True
                 and report.get("source_hashes") == initial)
        parts.append({"path": path, "exit_code": completed.returncode,
                      "current_source_passed": valid})
        cases.extend(dict(case, component=path) for case in report.get("cases", []))
        if not valid:
            cases.append({"case": "component_not_passed:" + path, "passed": False})
            # ⚠️ 此处**不再 break**：一个部分失败不该藏起后面三个部分。
            #    2026-10-28 实测：原来 break 时 part ④ 从未被执行到，
            #    于是它里面一个确定性的 UnboundLocalError 藏了 20 天。
    return parts, cases


def compare(runs):
    """逐 part、逐 case 比对两遍结果，返回**合并视图**。

    ⚠️ 第一版 `parts = runs[0][0]`（只取第 1 遍）—— 那会让判定**依赖运行顺序**：
       同一个 case「第 1 遍过、第 2 遍不过」，只因为哪遍在前，结论就相反。
       现在 parts 也是合并视图（stable_pass / unstable / run1_passed / run2_passed）。
    """
    p = [{x["path"]: x for x in r[0]} for r in runs]
    c = [{x["case"]: x for x in r[1]} for r in runs]

    # ── part 级
    parts, unstable_parts, stable_fail_parts = [], [], []
    for k in [x for x in p[0] if x in p[1]]:
        a, b = (bool(p[0][k]["current_source_passed"]),
                bool(p[1][k]["current_source_passed"]))
        parts.append(dict(p[0][k], stable_pass=(a and b), agree=(a == b),
                          run1_passed=a, run2_passed=b, unstable=(a != b)))
        if a != b:
            unstable_parts.append(k)
        elif not a:
            stable_fail_parts.append(k)
    incomplete_parts = [k for k in set(p[0]) | set(p[1])
                        if k not in {x["path"] for x in parts}]

    # ── case 级
    merged, unstable_cases, stable_fail = [], [], []
    for n in [x for x in c[0] if x in c[1]]:
        a, b = bool(c[0][n].get("passed")), bool(c[1][n].get("passed"))
        merged.append(dict(c[0][n], passed=(a and b), agree=(a == b),
                           run1_passed=a, run2_passed=b, unstable=(a != b)))
        if a != b:
            unstable_cases.append(n)
        elif not a:
            stable_fail.append(n)
    for n in [x for x in set(c[0]) | set(c[1]) if x not in {m["case"] for m in merged}]:
        merged.append(dict((c[0].get(n) or c[1].get(n) or {}),
                           passed=False, agree=False, unstable=True,
                           note="只在一遍里出现"))
        unstable_cases.append(n)

    total = len(merged)
    return {"parts": parts, "cases": merged,
            "unstable_parts": unstable_parts,
            "stable_fail_parts": stable_fail_parts,
            "incomplete_parts": incomplete_parts,
            "unstable_cases": unstable_cases,
            "stable_fail_cases": stable_fail,
            "unstable_ratio": round(len(unstable_cases) / total, 4) if total else 0.0}


def gate_ok(cmp):
    """门：无 stable_fail（case 级 + part 级）+ 无 incomplete + 4 个 part。

    ★ 抽成函数是为了**只有一个定义**：main() 和 tests/test_live_reproducibility.py
      都调它。第一版测试里 `gate()` 是 main() 逻辑的**副本**，
      于是改坏 main() 时测试抓不到（测试验的是自己的副本）。
    ★ unstable **不挡门** —— 理由见文件头「为什么 unstable 不挡门」。
    """
    return bool(len(cmp["parts"]) == 4
                and not cmp["incomplete_parts"]
                and not cmp["stable_fail_cases"]
                and not cmp["stable_fail_parts"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    if not parser.parse_args().run:
        print("Use --run for bounded disposable API checks; no calls made.")
        return 0
    before, initial = state_hashes(), source_hashes(ROOT)
    paths = [SELF_GOAL_LIVE, "spec/有界目标承诺作答模型复验_20261008.json",
             "spec/有界目标承诺组织模型复验_20261008.json",
             "spec/有界目标承诺记忆模型复验_20261008.json"]
    commands = [["tools/trial_self_goal.py", "--api", "--report", paths[0]],
                ["tools/trial_self_action.py", "--api", "--report", paths[1]],
                ["tools/trial_organisation_runtime.py", "--api", "--report", paths[2]],
                ["tools/verify_goal_live.py", "--run", "--relations", "--report", paths[3]]]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")

    runs = []
    for i in range(2):
        print("── 第 %d 遍（4 个部分）──" % (i + 1), flush=True)
        runs.append(run_once(paths, commands, initial, env))

    cmp = compare(runs)
    parts = cmp["parts"]

    # ── 门：无 stable_fail（case 级与 part 级）+ 无 incomplete
    gate = gate_ok(cmp)
    # ── 更严的参考值（不当门）
    strict = gate and not cmp["unstable_cases"] and not cmp["unstable_parts"]

    if cmp["unstable_parts"] or cmp["unstable_cases"]:
        print("  ⚠️ unstable（两遍不一致 → 记模型侧不稳，**不当系统缺陷**）"
              "｜parts=%s｜cases=%s｜比例=%.1f%%"
              % (cmp["unstable_parts"], cmp["unstable_cases"],
                 cmp["unstable_ratio"] * 100), flush=True)
    if cmp["stable_fail_cases"] or cmp["stable_fail_parts"]:
        print("  ★ 两遍都不过（值得查的线索，**不是已证实缺陷**）"
              "｜parts=%s｜cases=%s"
              % (cmp["stable_fail_parts"], cmp["stable_fail_cases"]), flush=True)

    if state_hashes() != before or source_hashes(ROOT) != initial:
        raise RuntimeError("Real state/source changed during live verification")
    result = {"schema": 1, "scope": "scripted_declared_goals_memory_and_rule_execution",
              "passed": gate,                    # ← 门
              "live_gate_pass": gate,
              "live_stable_pass": strict,        # ← 参考，不当门
              "unstable_ratio": cmp["unstable_ratio"],
              "measurement_limit": MEASUREMENT_LIMIT,
              "unstable_cases": cmp["unstable_cases"],
              "unstable_parts": cmp["unstable_parts"],
              "incomplete_parts": cmp["incomplete_parts"],
              "stable_fail_cases": cmp["stable_fail_cases"],
              "stable_fail_parts": cmp["stable_fail_parts"],
              "runs": 2,
              "source_hashes": initial, "parts": parts, "cases": cmp["cases"],
              "real_API": True, "formal_training": False, "scripted_inputs": True,
              "independent_semantics_verified": False,
              "real_state_files_unchanged": len(before), "development_credit": 0,
              "claims": "Bounded model goal declarations and literal outcomes; "
                        "candidate and counterfeedback injections remain declared."}
    (ROOT / LIVE).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    write_report(ROOT)
    print(json.dumps({"gate": gate, "stable": strict,
                      "unstable_ratio": cmp["unstable_ratio"],
                      "cases": len(cmp["cases"]),
                      "unstable_cases": cmp["unstable_cases"],
                      "stable_fail_cases": cmp["stable_fail_cases"],
                      "state_unchanged": len(before)}, ensure_ascii=False), flush=True)
    return int(not gate)


if __name__ == "__main__":
    raise SystemExit(main())

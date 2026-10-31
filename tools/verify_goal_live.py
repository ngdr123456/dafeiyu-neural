"""Small real-model diagnostic, entirely disposable memory, no real training.

Inputs are scripted cases, not independently verified human experiences.
"""
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from pipeline import Pipeline
from input_provenance import digest
from content_fidelity import review
from think import Frame
from action_plan import source_hashes, write_report, LIVE


def state_hashes():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "state").rglob("*") if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="实际调用当前API")
    parser.add_argument("--relations", action="store_true", help="增加关系抽取、长间隔、保留、消融与冲突诊断")
    parser.add_argument("--report", default=LIVE)
    args = parser.parse_args()
    if not args.run:
        print("Use --run for the bounded real API diagnostic; no calls made.")
        return 0
    before = state_hashes()
    initial_sources = source_hashes(ROOT)
    results = []
    with tempfile.TemporaryDirectory(prefix="ego-real-goal-check-") as tmp:
        def pipe(directory, live=False):
            return Pipeline(ledger_path=str(directory / "state/ledger.jsonl"),
                            character_path=str(directory / "state/character.json"),
                            devlevel_path=str(directory / "state/devlevel_verified.json"),
                            carry_root=str(directory), gate_perception=True, auto_audit=False,
                            use_api=live, use_think=live)

        def turn(p, text):
            return p.turn(text, input_origin={"schema": 1, "kind": "scripted_diagnostic",
                          "input_sha256": digest(text), "topic_id": None,
                          "independent_human_input_verified": False})

        live_pipe = None
        for name in ("李老师", "周老师"):
            directory = Path(tmp) / name
            p = pipe(directory)
            turn(p, "押金由%s收着，我要先联系%s。" % (name, name))
            p = pipe(directory, live=True)
            if not p.api_enabled or p.thinker is None:
                results.append({"case": "availability", "passed": False, "error": "api_unavailable"})
                break
            live_pipe = p
            try:
                result = turn(p, "那我现在该联系谁？")
                attempts = p.thinker.last_attempts
                passed = (name in result.output and result.api_ok and
                          any(a["accepted"] and (a.get("content_review") or {}).get("verdict") == "PASS"
                              for a in attempts))
                results.append({"case": "contact_after_restart:" + name, "passed": passed,
                                "output": result.output, "behavior": result.behavior,
                                "planned_behavior": result.planned_behavior, "attempts": attempts})
                print(results[-1]["case"], passed, result.output, flush=True)
            except Exception as exc:
                results.append({"case": "contact_after_restart:" + name, "passed": False,
                                "error": type(exc).__name__})
                break
        if live_pipe is not None and all(r["passed"] for r in results):
            directory = Path(tmp) / "周老师"
            turn(pipe(directory), "更正：押金现在由赵老师收着，我要先联系赵老师，前面周老师那句说错了。")
            p = pipe(directory, live=True)
            try:
                result = turn(p, "那我现在该联系谁？")
                attempts = p.thinker.last_attempts
                passed = "赵老师" in result.output and result.api_ok and any(a["accepted"] for a in attempts)
                results.append({"case": "corrected_contact_after_restart", "passed": passed,
                                "output": result.output, "behavior": result.behavior, "attempts": attempts})
                print(results[-1]["case"], passed, result.output, flush=True)
                for raw, candidate, case in (
                        ("我站在那里闻了半小时桂花。", "那半小时里没人在看表。", "fabricated_detail"),
                        ("押金还没有退，那我现在该联系谁？", "模型和架构是别人定的，我左右不了。", "off_topic")):
                    checked = review(p.thinker.reader, Frame(raw=raw), candidate)
                    passed = checked["verdict"] == "REJECT"
                    results.append({"case": case, "passed": passed, "review": checked})
                    print(case, passed, checked["verdict"], flush=True)
            except Exception as exc:
                # ⚠️ 原来只存 type(exc).__name__，于是 2026-10-28 那次
                #    `correction_or_review` 只报了一个 `UnboundLocalError`，
                #    **没有行号、没有变量名** —— 无法定位。
                #    留 traceback 是修复这类"只报异常类名"的正确做法。
                import traceback as _tb
                results.append({"case": "correction_or_review", "passed": False,
                                "error": type(exc).__name__,
                                "traceback": _tb.format_exc()[-2000:]})
        if args.relations and live_pipe is not None and all(r["passed"] for r in results):
            directory = Path(tmp) / "relations"
            seed = pipe(directory, live=True)
            seed.thinker = None  # extraction uses the actual API, no generated seed reply
            for text, subject, value, correction in (
                    ("甲项目押金由李老师收着。", "甲项目押金", "李老师", False),
                    ("乙项目押金由周老师收着。", "乙项目押金", "周老师", False),
                    ("更正：甲项目押金由赵老师收着。", "甲项目押金", "赵老师", True)):
                result = turn(seed, text)
                reading = result.proposition_reading or {}
                passed = any(c["subject"] == subject and c["predicate"] == "custodian"
                             and c["value"] == value and c["role"] == "ASSERTED"
                             and c["correction"] is correction for c in reading.get("propositions", []))
                results.append({"case": "literal_relation_extraction:" + value, "passed": passed, "reading": reading})
                print(results[-1]["case"], passed, flush=True)
            # All subsequent comparison queries see the same source history.
            offline = pipe(directory)
            for i in range(18):
                turn(offline, "甲项目押金现在由谁收着？这问暂放第%d次。" % i)
            ablation_dir = Path(tmp) / "relations_ablation"
            shutil.copytree(directory, ablation_dir)

            def answer(directory, text, *, enabled=True):
                run = pipe(directory, live=True)
                run.use_relational_memory = enabled
                captured = []
                assemble = run._build_frame
                def capture(*a, **kw):
                    frame = assemble(*a, **kw)
                    captured.append(frame)
                    return frame
                run._build_frame = capture
                result = turn(run, text)
                attempts = run.thinker.last_attempts
                accepted = result.api_ok and any(a["accepted"] and
                    (a.get("content_review") or {}).get("verdict") == "PASS" for a in attempts)
                return result, attempts, captured[-1].relational_context if captured else {}, accepted

            for subject, value, case in (("甲项目押金", "赵老师", "long_gap_corrected_relation_after_restart"),
                                          ("乙项目押金", "周老师", "unaffected_object_retained")):
                result, attempts, context, accepted = answer(directory, subject + "现在由谁收着？")
                groups = context.get("groups", [])
                passed = accepted and value in result.output and any(
                    g["subject"] == subject and g["reported_values"] == [value] for g in groups)
                results.append({"case": case, "passed": bool(passed), "output": result.output,
                                "context": context, "attempts": attempts})
                print(case, passed, result.output, flush=True)
            result, attempts, context, accepted = answer(ablation_dir, "甲项目押金现在由谁收着？", enabled=False)
            # Missing selected memory cannot justify a global 'never recorded'.
            passed = accepted and not context and "赵老师" not in result.output and not any(
                word in result.output for word in ("从没", "从未", "没说过", "没有说过", "没有记录过"))
            from memory_scope import check as check_scope
            # ⚠️ 这里原来还有一行 `from think import Frame` —— 模块级（第 18 行）已经有了。
            #    它的存在让 Python 把 `Frame` 当成 **main() 的局部变量**，
            #    于是第 90 行 `Frame(raw=raw)` 在那条 import 执行到之前就报
            #    `UnboundLocalError: cannot access local variable 'Frame'`。
            #    2026-10-28 实测：去掉它之后 `correction_or_review` 才跑起来。
            #    ★ 这个 bug 一直存在，但**从没被执行到** —— 因为原来聚合器
            #      在 part ① 失败时 `break`，part ④ 根本轮不到跑。
            recorded_scope = (result.self_action or {}).get("memory_scope", {})
            scope_errors = check_scope(Frame(raw="甲项目押金现在由谁收着？", memory_scope=recorded_scope), result.output)
            passed = passed and recorded_scope.get("matching_relation_utterance_known") is True and not scope_errors
            results.append({"case": "relation_ablation", "passed": bool(passed), "output": result.output,
                            "context": context, "attempts": attempts,
                            "memory_scope": recorded_scope, "scope_errors": scope_errors,
                            "claim": "known name unavailable when only flat bounded window remains"})
            print("relation_ablation", passed, result.output, flush=True)
            conflicting = "甲项目押金由钱老师收着。"
            seed = pipe(directory, live=True)
            seed.thinker = None
            result = turn(seed, conflicting)
            reading = result.proposition_reading or {}
            passed = any(c["subject"] == "甲项目押金" and c["value"] == "钱老师"
                         and c["role"] == "ASSERTED" and not c["correction"] for c in reading.get("propositions", []))
            results.append({"case": "conflict_extraction", "passed": passed, "reading": reading})
            result, attempts, context, accepted = answer(directory, "甲项目押金现在由谁收着？")
            passed = accepted and any(g["status"] == "conflict" and set(g["reported_values"]) == {"赵老师", "钱老师"}
                                      for g in context.get("groups", [])) and "赵老师" in result.output and "钱老师" in result.output
            results.append({"case": "unresolved_conflict_not_latest_wins", "passed": bool(passed),
                            "output": result.output, "context": context, "attempts": attempts})
            print(results[-1]["case"], passed, result.output, flush=True)
    if before != state_hashes():
        raise RuntimeError("Real state changed; refusing unchanged-state claim")
    if initial_sources != source_hashes(ROOT):
        raise RuntimeError("Code changed during live diagnostic")
    expected_cases = 13 if args.relations else 5
    result = {"schema": 1, "date": "2026-10-08", "passed": len(results) == expected_cases and all(r["passed"] for r in results),
              "source_hashes": initial_sources, "cases": results, "real_state_files_unchanged": len(before),
              "scripted_inputs": True, "real_API": True, "independent_semantic_review_verified": False,
              "development_credit": 0, "learned_rule_change": False,
              "claims": "listed cases only, engineered representation, not general human-likeness"}
    (ROOT / args.report).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("passed:", result["passed"], "state unchanged:", len(before), flush=True)
    write_report(ROOT)
    return int(not result["passed"])


if __name__ == "__main__":
    raise SystemExit(main())

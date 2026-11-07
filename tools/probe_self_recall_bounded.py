"""Synthetic, TEMP-only recall probe. Add --run for at most one DeepSeek call.

Run from the repository root: python -m tools.probe_self_recall_bounded [--run] [--output PATH]
The dry run performs no model calls. The optional live case uses a manual signal,
an invented ledger entry, the normal pipeline and the existing DeepSeek client.
"""
import argparse
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from birth import llm_deepseek, pipeline
from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode
from birth.input_contract import InputSignal
from birth.llm_opencode import brief_to_prompt
from birth.memory import BirthMemoryStore, configure_memory
from birth.types import HerUtterance

QUESTION = "你以前关于白桦叶灯说过什么？"
TARGET = "白桦叶灯"
HISTORY = "白桦叶灯在雨夜像一小片安静的云。"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="allow one live DeepSeek request")
    parser.add_argument("--output", type=Path, help="write JSON directly to this UTF-8 file instead of stdout")
    args = parser.parse_args()
    os.environ["BIRTH_DEEPSEEK_MODEL"] = "deepseek-flash"
    if args.run and llm_deepseek.resolve_base() != llm_deepseek.DEFAULT_BASE:
        raise SystemExit("Live probe requires the existing default DeepSeek endpoint.")

    calls = 0
    raw_output = None
    error = None
    signal = InputSignal("ask", "other", "probe", "manual", recall_self=True, recall_target=TARGET)
    cases = {}
    with tempfile.TemporaryDirectory(prefix="ego-recall-probe-") as directory:
        for case, texts in (("unique", [HISTORY]), ("no_match", []),
                            ("multiple", [HISTORY, "白桦叶灯在桌边。英文字也只是合成数据。" ])):
            path = Path(directory) / (case + ".json")
            memory = BirthMemoryStore(path)
            memory.append_session(her_utterances=[asdict(HerUtterance(t, "", "", "", "synthetic", True)) for t in texts])
            configure_memory(enabled=True, path=path)
            pipeline.active_store().new_session()
            result = pipeline.turn(QUESTION, input_signal=signal, sense=False, stub=True)
            if result.brief.recall_status != case:
                raise AssertionError(f"{case}: unexpected status {result.brief.recall_status}")
            cases[case] = {"status": result.brief.recall_status,
                           "evidence": asdict(result.brief.recall_evidence) if result.brief.recall_evidence else None,
                           "prompt": brief_to_prompt(result.brief)}

        if args.run:
            configure_memory(enabled=True, path=Path(directory) / "unique.json")
            pipeline.active_store().new_session()
            set_stub_mode(False)

            def once(brief):
                nonlocal calls, raw_output, error
                if calls:
                    return None  # Existing output validation may retry; never send twice.
                calls += 1
                try:
                    raw_output = llm_deepseek.generate_utterance(brief, strict=True)
                    return raw_output
                except llm_deepseek.DeepSeekUnavailable as exc:
                    error = str(exc)  # fixed non-secret error code
                    return None

            set_llm_hook(once)
            result = pipeline.turn(QUESTION, input_signal=signal, sense=False, stub=False)
            cases["live"] = {"raw_model_output": raw_output, "delivered": result.utterance,
                             "source": result.articulate_source, "failure_code": error,
                             "status": result.brief.recall_status,
                             "evidence": asdict(result.brief.recall_evidence) if result.brief.recall_evidence else None}
        clear_llm_hook()
        configure_memory(enabled=False)
        pipeline.active_store().new_session()
    output = json.dumps({"model": "deepseek-flash", "model_calls_attempted": calls,
                      "input_signal": "manual; no model perception", "question": QUESTION,
                      "history_origin": "invented for this test; not lived experience",
                      "synthetic_history": HISTORY, "cases": cases}, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()

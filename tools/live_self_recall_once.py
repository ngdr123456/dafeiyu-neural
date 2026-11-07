"""One independent-ledger live cross-session probe; never prints credentials."""
import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from birth import llm_deepseek, pipeline
from birth.articulate import set_llm_hook, set_stub_mode
from birth.memory import configure_memory

path = Path('.test-live-self-recall') / (uuid4().hex + '.json')
configure_memory(enabled=True, path=path)
pipeline.active_store().new_session()
set_stub_mode(False)
set_llm_hook(lambda brief: llm_deepseek.generate_utterance(brief, strict=True))
inputs = ["请说一句关于蓝色纸船停在窗边的话。", "你之前关于蓝色纸船停在窗边说过什么？"]
out = {"ledger": str(path), "inputs": inputs, "turns": []}
try:
    first = pipeline.turn(inputs[0], sense=True, stub=False)
    out["turns"].append({"output": first.utterance, "source": first.articulate_source,
                          "signal": asdict(first.input_signal) if first.input_signal else None})
    pipeline.end_session()
    pipeline.active_store().new_session()
    configure_memory(enabled=True, path=path)
    second = pipeline.turn(inputs[1], sense=True, stub=False)
    out["turns"].append({"output": second.utterance, "source": second.articulate_source,
                          "signal": asdict(second.input_signal) if second.input_signal else None,
                          "evidence": asdict(second.brief.recall_evidence) if second.brief.recall_evidence else None})
    out["persisted_voice"] = [asdict(e) for s in configure_memory(enabled=True, path=path).list_sessions()
                              for e in s.her_utterances]
except Exception as exc:
    out["error_type"] = type(exc).__name__
print(json.dumps(out, ensure_ascii=False, indent=2))

"""Compare deterministic pipeline structures with the specified Git baseline."""
import os
from pathlib import Path
import subprocess
import sys
import tarfile


SCRIPT = r'''
import dataclasses, json
from birth import pipeline
from birth.input_contract import InputSignal
from birth.memory import configure_memory
configure_memory(enabled=False)
pipeline.active_store().new_session()
scenarios = [
    ("我们聊星空", InputSignal("tell", "other", "test", "test", topic="星空")),
    ("为什么呢？", InputSignal("ask", "other", "test", "test", topic="星空")),
    ("接着说", InputSignal("tell", "other", "test", "test", degraded=True, topic="猜测的主题")),
    ("换个话题", InputSignal("tell", "other", "test", "test", topic="月亮")),
    ("停下", InputSignal("stop", "other", "test", "test", scope="conversation")),
]
out = []
for text, signal in scenarios:
    result = pipeline.turn(text, input_signal=signal, stub=True)
    trace = pipeline.active_store().export_session_trace()
    trace.pop("record_metadata", None)
    out.append({"result": dataclasses.asdict(result), "context": dataclasses.asdict(pipeline.active_store().snapshot()), "trace": trace})
print(json.dumps(out, sort_keys=True, ensure_ascii=True, default=lambda obj: dataclasses.asdict(obj)))
'''


def test_five_layer_structures_match_baseline(tmp_path):
    root = Path(__file__).resolve().parents[1]
    archive = tmp_path / "baseline.tar"
    subprocess.run(["git", "archive", "--format=tar", "-o", str(archive),
                    "316dba33c226dd17b8953bbf731a9decd8f2c06e", "birth"], cwd=root, check=True)
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(baseline, filter="data")
    def run(directory):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(directory)
        env["BIRTH_INPUT_SENSE"] = "0"
        return subprocess.check_output([sys.executable, "-c", SCRIPT], cwd=directory, env=env, text=True)
    assert run(baseline) == run(root)

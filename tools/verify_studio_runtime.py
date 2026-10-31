"""Verify the built exe on a disposable root; no training or real API."""
import hashlib
import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]


def hashes():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "state").rglob("*") if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="spec/目标修正桌面启动验收_20261007.json")
    args = parser.parse_args()
    before = hashes()
    exe = ROOT / "启动训练台.exe"
    archive = CArchiveReader(str(exe)).open_embedded_archive("PYZ.pyz")
    assert not any(n in archive.toc for n in ("training_studio", "pipeline", "relation_learning")), "Project code frozen"
    with tempfile.TemporaryDirectory(prefix="ego-studio-") as tmp:
        root = Path(tmp) / "软件验收副本"
        root.mkdir()
        for name in ("engine", "rules", "corpus", "spec", "state"):
            shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for md in ROOT.glob("*.md"):
            shutil.copy2(md, root / md.name)
        executable = root / "启动训练台.exe"
        shutil.copy2(exe, executable)
        result_path = root / "diagnosis.json"
        def run(smoke=False):
            cmd = [str(executable), "--diagnose", str(result_path)]
            if smoke:
                cmd += ["--smoke-ui"]
            env = dict(os.environ)
            env.pop("EGO_ROOT", None)
            result = subprocess.run(cmd, timeout=60, capture_output=True, env=env)
            data = json.loads(result_path.read_text(encoding="utf-8"))
            assert result.returncode == 0, data
            return data
        first = run(True)
        assert first["ui"]["created"]
        # Same exe, changed external source: exact new hash must be observed.
        source = root / "engine/relation_bridge.py"
        source.write_bytes(source.read_bytes() + b"\nRUNTIME_UPDATE_PROBE = 'executed-new-source'\n")
        second = run()
        assert first["source_modules"]["relation_bridge"]["sha256"] != second["source_modules"]["relation_bridge"]["sha256"]
        assert second["source_modules"]["relation_bridge"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
        assert second["source_modules"]["relation_bridge"]["executed_update_probe"] == "executed-new-source"
        (root / "engine/training_studio.py").unlink()
        failure = subprocess.run([str(executable), "--root", str(root), "--diagnose", str(result_path)], timeout=60)
        assert failure.returncode != 0
        missing = json.loads(result_path.read_text(encoding="utf-8"))
        assert "缺失" in missing["error"]
    assert before == hashes(), "Real state changed"
    report = {"exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(), "project_code_not_frozen": True,
              "same_exe_source_update_verified": True, "missing_source_fails_explicitly": True,
              "state_files_unchanged": len(before), "first_launch": first, "updated_launch": second,
              "missing_source": missing}
    (ROOT / args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Desktop runtime verified; real state unchanged:", len(before))


if __name__ == "__main__":
    main()

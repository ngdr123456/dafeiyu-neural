"""Explicit authorized baseline migration; no Pipeline, API or training invocation."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from development_baseline import initialize


def hashes():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "state").rglob("*") if p.is_file()}


if __name__ == "__main__":
    before = hashes()
    baseline = initialize(ROOT)
    after = hashes()
    allowed = {"state/devlevel.json", "state/devlevel_verified.json",
               "state/development_legacy_20261006/devlevel.json"}
    changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
    if changed - allowed:
        raise RuntimeError("Unexpected state mutation: " + repr(changed - allowed))
    report = {"authorized_by": "D-020", "baseline": baseline,
              "changed_files": sorted(changed),
              "unchanged_existing_state_files": sum(before[k] == after.get(k) for k in before),
              "before_sha256": before, "after_sha256": after}
    (ROOT / "spec/基线迁移_20261006.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"level": baseline["level"], "equilibration": baseline["equilibration"],
                      "changed_files": sorted(changed)}, ensure_ascii=False))

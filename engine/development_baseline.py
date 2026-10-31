"""Authorized migration: immutable legacy evidence + separate verified baseline.

The existing devlevel.json becomes a display projection so the packaged read-only
UI remains usable. The canonical source for future perception is the verified file.
"""
import hashlib
import json
from pathlib import Path
from behavior_learning import atomic_json


def initialize(root, start_level="I-3"):
    root = Path(root)
    state = root / "state"
    canonical = state / "devlevel_verified.json"
    display = state / "devlevel.json"
    if canonical.exists():
        data = json.loads(canonical.read_text(encoding="utf-8"))
        if data.get("baseline_schema") != 1:
            raise ValueError("Invalid verified development baseline")
        return data
    legacy = display.read_bytes() if display.exists() else None
    old = json.loads(legacy) if legacy else {}
    if old.get("display_projection"):
        raise ValueError("Canonical baseline missing; refusing to initialize from display projection")
    archive = state / "development_legacy_20261006" / "devlevel.json"
    if legacy is not None:
        archive.parent.mkdir(parents=True, exist_ok=True)
        if archive.exists() and archive.read_bytes() != legacy:
            raise RuntimeError("Legacy archive differs; refusing to overwrite evidence")
        if not archive.exists():
            with archive.open("xb") as stream:
                stream.write(legacy)
        if archive.read_bytes() != legacy:
            raise RuntimeError("Legacy archive verification failed")
    data = {"baseline_schema": 1, "baseline_id": "verified-20261006",
            "level": start_level, "equilibration": 0, "failed": False,
            "pending": 0, "fail_tension": 0.0, "not_grown": 0, "history": [],
            "evidence_policy": "independent_structure_evidence_required",
            "legacy": {"archive": str(archive.relative_to(root)) if legacy else None,
                       "sha256": hashlib.sha256(legacy).hexdigest() if legacy else None,
                       "level": old.get("level"), "equilibration": old.get("equilibration")},
            "note": "I-3 is the existing engineering starting level, not an inferred human stage.",
            "updated": "2026-10-06 baseline migration"}
    atomic_json(canonical, data)
    atomic_json(display, dict(data, canonical="state/devlevel_verified.json",
                              display_projection=True))
    return data

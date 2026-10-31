"""Offline handoff audit. Reads evidence; DevLevel writes only in a temporary directory.

Runs the actual structure layer and DevLevel, never the API or training pipeline.
Historical channel sequences are held fixed: this is not an end-to-end retraining.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import constants as C
import session_split as SS
from devlevel import DevLevel
from mechanism import Mechanism


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recovery_certificate():
    """Inductive lower bounds by streak bucket, after a real high-error observation."""
    memory = Fraction(str(C.ERROR_MEMORY))
    full = Fraction(str(C.STREAK_FULL))
    flip = 1 - memory
    one = memory * flip + (1 - memory) / full
    two = memory * one + (1 - memory) * 2 / full
    successor = memory * two + (1 - memory) * min(Fraction(1), 3 / full)
    valid = (full >= 3 and flip >= two and one >= two and successor >= two
             and Fraction(str(C.ERROR_HIGH)) >= max(flip, one, two))
    return {"valid": valid, "streak_0_bound": str(flip),
            "streak_1_bound": str(one), "streak_2_or_more_bound": str(two),
            "lower_bound": float(two) if valid else None,
            "error_low": C.ERROR_LOW,
            "recovery_unreachable_without_reset": valid and two > Fraction(str(C.ERROR_LOW))}


def audit(ledger):
    watched = [p for p in (ROOT / "state").rglob("*") if p.is_file()]
    before = {str(p): digest(p) for p in watched}
    rows = SS.load(str(ledger))
    # Preserve pure META sessions so event IDs match the handoff's raw 63-session numbering.
    sessions = SS.split_sessions(rows)
    results = {}
    for mode in ("session_reset", "carry_e_only", "continuous_structure"):
        events, mismatches, compared = [], [], 0
        with tempfile.TemporaryDirectory(prefix="ego-handoff-") as temporary:
            dev = DevLevel(str(Path(temporary) / "devlevel.json"))
            previous = None
            for sid, session in enumerate(sessions, 1):
                # Match Pipeline construction: a new DevLevel reads persistent state each session.
                dev = DevLevel(str(Path(temporary) / "devlevel.json"))
                mechanism = Mechanism()
                if previous is not None:
                    if mode == "carry_e_only":
                        mechanism.e = previous.e
                    elif mode == "continuous_structure":
                        mechanism = previous
                index = 0
                for row in SS.session_turns(session):
                    index += 1
                    recorded = row.get("mech") or {}
                    if recorded.get("e_version") != C.E_VERSION:
                        continue
                    e = mechanism._layer2(row["channel"])["e"]
                    if mode == "session_reset" and recorded.get("e") is not None:
                        compared += 1
                        if round(e, 3) != recorded["e"]:
                            mismatches.append({"session": sid, "turn": index,
                                               "expected": recorded["e"], "actual": e})
                    # Pipeline passes the rounded MechanismState to DevLevel.
                    outcome = dev.update({"e": round(e, 3),
                                          "tension": recorded.get("tension"),
                                          "tension_measured": recorded.get("tension_measured")})
                    if outcome.get("event"):
                        events.append({"session": sid, "mechanism_turn": index,
                                       "turn_id": row.get("turn_id"), "e": e,
                                       "event": outcome["event"]})
                previous = mechanism
            results[mode] = {"failures": dev.pending, "equilibration": dev.equilibration,
                             "level": dev.level, "compared": compared,
                             "mismatches": mismatches, "events": events}
    after = {str(p): digest(p) for p in (ROOT / "state").rglob("*") if p.is_file()}
    if before != after:
        raise RuntimeError("state/ changed during read-only audit")
    if results["session_reset"]["mismatches"]:
        raise RuntimeError("Recorded e does not match actual structure layer")
    return {"ledger": str(ledger), "ledger_sha256": digest(ledger), "rows": len(rows),
            "formula_version": C.E_VERSION, "window": SS.count(rows),
            "recovery_certificate": recovery_certificate(),
            "state_files_unchanged": len(before), "modes": results,
            "limitations": "Fixed historical channels and tensions; no API, no causal retraining, "
                            "carry_e_only has no decay; continuous_structure carries e/streak/previous channel."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=ROOT / "state/train/ledger.jsonl")
    args = parser.parse_args()
    print(json.dumps(audit(args.ledger), ensure_ascii=False, indent=2))

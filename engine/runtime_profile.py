"""Default interactive identity follows the desktop training identity.

No ledger merging. Generated personas stay excluded from human fact retrieval.
The legacy root ledger remains selectable, not deleted or migrated by guessing.
"""
from pathlib import Path


def paths(root, profile="trained", ledger=None):
    if profile not in {"trained", "legacy"}:
        raise ValueError("Unknown runtime profile")
    directory = Path(root) / "state" / ("train" if profile == "trained" else "")
    chosen = Path(ledger) if ledger else directory / "ledger.jsonl"
    return {"profile": "custom" if ledger else profile,
            "ledger": str(chosen), "character": str(chosen.parent / "character.json"),
            "memory_directory": str(chosen.parent)}

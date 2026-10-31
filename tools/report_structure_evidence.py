"""Read-only evidence report from actual persisted relation memories."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from structure_evidence import report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths = [args.memory] if args.memory else [ROOT / "state/relation_rules.json", ROOT / "state/train/relation_rules.json"]
    result = {}
    for path in paths:
        if not path.exists():
            result[str(path)] = {"verdict": "no_memory", "development_credit": 0}
            continue
        result[str(path)] = report(json.loads(path.read_text(encoding="utf-8")))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()

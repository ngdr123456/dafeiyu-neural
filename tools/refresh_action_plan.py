"""Recompute the next action from current code, regression and actual feedback."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from action_plan import write_report

if __name__ == "__main__":
    result = write_report(ROOT)
    print(json.dumps({"objective": result["objective"], "next_action": result["next_action"],
                      "signals": result["signals"], "goal_achieved": result["goal_achieved"]},
                     ensure_ascii=False, indent=2))

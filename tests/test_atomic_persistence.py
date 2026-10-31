"""Transient sharing locks do not corrupt state; permanent denial stays visible."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import behavior_learning as module


class Persistence(unittest.TestCase):
    def test_transient_file_lock_commits_once_and_permanent_lock_preserves_old_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "baseline.json"
            module.atomic_json(path, {"old": True})
            original = module.os.replace
            calls = []
            def locked_twice(source, target):
                calls.append((source, target))
                if len(calls) < 3:
                    raise PermissionError("synthetic sharing lock")
                return original(source, target)
            with patch.object(module, "_windows_sharing_violation", return_value=True), \
                    patch.object(module.os, "replace", side_effect=locked_twice), patch.object(module.time, "sleep"):
                module.atomic_json(path, {"new": True})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"new": True})
            self.assertEqual(len(calls), 3)
            before = path.read_bytes()
            with patch.object(module, "_windows_sharing_violation", return_value=True), \
                    patch.object(module.os, "replace", side_effect=PermissionError("permanent")) as replace, \
                    patch.object(module.time, "sleep"):
                with self.assertRaises(PermissionError):
                    module.atomic_json(path, {"bad": True})
                self.assertEqual(replace.call_count, 4)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_other_permission_errors_are_not_retried_or_swallowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(module, "_windows_sharing_violation", return_value=False), \
                    patch.object(module.os, "replace", side_effect=PermissionError("other")) as replace:
                with self.assertRaises(PermissionError):
                    module.atomic_json(Path(tmp) / "state.json", {"x": 1})
                self.assertEqual(replace.call_count, 1)


if __name__ == "__main__":
    unittest.main()

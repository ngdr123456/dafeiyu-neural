"""Stable desktop entry: embedded standard library, project source on disk."""
import argparse
import hashlib
import importlib
import importlib.abc
import importlib.util
import importlib.machinery
import json
import os
from pathlib import Path
import sys


class SourceOnlyLoader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname):
        # Cached .pyc timestamp/size collisions must not conceal an update.
        return compile(Path(self.path).read_bytes(), self.path, "exec", dont_inherit=True)


class ProjectSources(importlib.abc.MetaPathFinder):
    def __init__(self, directory):
        self.directory = directory
        self.names = {p.stem for p in directory.glob("*.py")}

    def find_spec(self, fullname, path=None, target=None):
        name = fullname[7:] if fullname.startswith("engine.") else fullname
        if name in self.names:
            source = self.directory / (name + ".py")
            return importlib.util.spec_from_file_location(fullname, source,
                       loader=SourceOnlyLoader(fullname, str(source)))
        return None


def configure(root):
    root = Path(root).resolve()
    for name in ("engine/training_studio.py", "engine/pipeline.py", "rules/markers.json"):
        if not (root / name).is_file():
            raise FileNotFoundError("项目文件缺失：" + str(root / name))
    os.environ["EGO_ROOT"] = str(root)
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(root / "engine"), str(root)]
    sys.meta_path.insert(0, ProjectSources(root / "engine"))
    return root


def diagnose(root, smoke=False):
    names = ("training_studio", "pipeline", "understand", "relation_learning", "relation_bridge", "studio_status")
    paths = {}
    for name in names:
        module = importlib.import_module(name)
        path = Path(module.__file__).resolve()
        if path.parent != root / "engine":
            raise RuntimeError("未从当前项目加载：" + name)
        paths[name] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        if hasattr(module, "RUNTIME_UPDATE_PROBE"):
            paths[name]["executed_update_probe"] = module.RUNTIME_UPDATE_PROBE
    result = {"root": str(root), "source_modules": paths, "frozen": bool(getattr(sys, "frozen", False))}
    if smoke:
        studio = sys.modules["training_studio"]
        window = studio.tk.Tk()
        window.withdraw()
        try:
            app = studio.Studio(window)
            window.update_idletasks()
            result["ui"] = {"created": True, "level": app.lbl_level.cget("text"),
                            "status": app.lbl_devsub.cget("text")}
        finally:
            window.destroy()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--diagnose")
    parser.add_argument("--smoke-ui", action="store_true")
    args = parser.parse_args()
    default = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    root = configure(args.root or os.environ.get("EGO_ROOT") or default)
    if args.diagnose:
        result = diagnose(root, args.smoke_ui)
        Path(args.diagnose).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    import training_studio
    return training_studio.main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        if "--diagnose" in sys.argv:
            destination = sys.argv[sys.argv.index("--diagnose") + 1]
            Path(destination).write_text(json.dumps({"error": str(error)}, ensure_ascii=False), encoding="utf-8")
            raise SystemExit(1)
        if getattr(sys, "frozen", False):
            import tkinter.messagebox
            tkinter.messagebox.showerror("启动失败", str(error))
        else:
            raise

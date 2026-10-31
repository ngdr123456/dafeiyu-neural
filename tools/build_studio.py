"""Build only the stable desktop bootstrap; never freeze project engine code."""
import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    libraries = {"tkinter", "tkinter.ttk", "tkinter.messagebox"}
    for source in (ROOT / "engine").glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            libraries.update(n for n in names if n.split(".")[0] in sys.stdlib_module_names)
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
            "--name", "启动训练台", "--distpath", str(ROOT / "build/studio/dist"),
            "--workpath", str(ROOT / "build/studio/work"), "--specpath", str(ROOT / "build/studio")]
    for name in sorted(libraries):
        args += ["--hidden-import", name]
    args.append(str(ROOT / "studio_bootstrap.py"))
    return subprocess.call(args, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())

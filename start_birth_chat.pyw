"""Double-click entry; also used by the bundled isolated Python runtime."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    try:
        from birth.windows_chat import main
        raise SystemExit(main())
    except Exception:
        # Do not print exceptions: backend errors may contain private information.
        import tkinter.messagebox
        tkinter.messagebox.showerror("第一期聊天", "启动失败。请检查完整的程序目录和 Python/Tk 运行时，参阅使用说明。")
        raise SystemExit(1)

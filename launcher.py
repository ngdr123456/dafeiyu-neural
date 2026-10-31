# -*- coding: utf-8 -*-
"""中文启动器：由 .bat 调用

为什么需要这个文件（这是一处真缺陷的修法）
  Windows 的 cmd.exe 用**系统 ANSI 代码页（中文系统是 GBK）**解析 .bat 文件，
  而我的 .bat 是用 UTF-8 无 BOM 写的 —— 于是中文字节被错误切分，
  连 `set PY=...` 这种命令行本身都被吃掉一个字，双击后报：

      'et' 不是内部或外部命令
      '覆鏌撳眰**锛氬畠浼氱敤鑷繁鐨勮瘽鎺ヤ綘鐨勮瘽...' 不是内部或外部命令

  **根因不是编码没设对，是"中文根本不该放在 .bat 里"。**
  修法：.bat 只做一件事 —— 调这个 py 文件；所有中文由 Python 打印（UTF-8 无问题）。

用法（由 .bat 调用，也可直接跑）：
    python launcher.py            # 继续用 state/ledger.jsonl
    python launcher.py --offline  # 不接 API
"""
from __future__ import annotations

import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SHELL = os.path.join(_HERE, "engine", "shell.py")


def _enable_utf8_console() -> None:
    """让 cmd 窗口能正确显示 UTF-8。

    cmd 默认代码页是 GBK；Python 输出 UTF-8 会花屏。
    这里在 Windows 上切到 65001，并在退出时切回来。
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:                                             # noqa: BLE001
        pass


def main() -> int:
    args = [a for a in sys.argv[1:]]
    offline = "--offline" in args
    args = [a for a in args if a != "--offline"]

    py = sys.executable
    cmd = [py, _SHELL]
    if not offline:
        cmd.append("--api")
    # ★ 默认用**思考层（乙案·大脑模式）**：模型当大脑，系统决定它该想什么。
    #   这是用户的明确指示（「大语言模型当大脑，而我们的系统则决定这个大脑该想什么」）。
    #   离线时不给任何模型开关，退回纯模板。
    #   旧的渲染层（--render）仍然可用，加参数即可：
    #       launcher.py --render      → 我们定一句话、模型换种说法
    if not offline:
        cmd.append("--think")
    cmd += args

    _enable_utf8_console()
    os.system("chcp 65001 >nul" if os.name == "nt" else "")

    print("─" * 74)
    print("  演示：开了【渲染层】—— 它会用自己的话接你的话，不再只复述模板。")
    print("  三道闸门任一不过会自动退回模板（退回原因写在 [ ] 里）。")
    print("  想退出：输入 /quit　　想看它长成什么样：输入 /character")
    print("─" * 74)
    print()

    rc = subprocess.call(cmd, cwd=_HERE)
    print()
    print("─" * 74)
    print("  已退出。台账、经历账、关联矩阵、性格核都已保存。")
    print("  下次打开会接着用同一份数据 —— 它会记得。")
    print("─" * 74)
    try:
        input("  按回车关闭这个窗口。")
    except EOFError:
        # 非交互调用（管道、自动化）时没有 stdin 可读 —— 直接退出。
        # 双击时不会有这个问题，但脚本被别的程序调用时会。
        pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

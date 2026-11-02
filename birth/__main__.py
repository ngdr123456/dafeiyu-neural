"""CLI demo：一期旁路闭环在命令行上跑。

用法：
    python -m birth                 # REPL 多轮（首轮清场；/new 新场）
    python -m birth "你好"          # 单句；默认 DeepSeek，失败再 OpenCode
    python -m birth --stub          # REPL + 强制模板 stub
    python -m birth "你好" --stub   # 单句 stub
    python -m birth --debug         # REPL + 工程师通道（开口来源＋Brief）

REPL 内：空行 / exit / quit / q / EOF 退出；/new 开新场。
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .articulate import set_stub_mode
from .pipeline import turn


_EXIT_WORDS = frozenset({"exit", "quit", "q"})


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="birth",
        description="第一期旁路模块：感知/动力/立场/组织/仲裁/开口最小闭环",
    )
    parser.add_argument(
        "user_text",
        nargs="?",
        default=None,
        help="用户这一轮说的话；省略则进入多轮 REPL",
    )
    parser.add_argument("--debug", action="store_true", help="打印台下 Brief（工程师通道）")
    parser.add_argument("--stub", action="store_true", help="强制模板开口，不调 DeepSeek/OpenCode")
    parser.add_argument("--new-session", action="store_true", help="显式开新场，清空同场积累")
    return parser


def _print_result(result, *, debug: bool) -> None:
    """台上只印 utterance；debug 另开工程师通道。"""
    print(result.utterance)

    if not debug:
        return

    print()
    src = result.articulate_source
    labels = {
        "deepseek": "deepseek（Mark DeepSeek API）",
        "opencode": "opencode（免费兜底）",
        "hook": "hook",
        "stub": "stub（强制模板）",
        "stub_fallback": "stub_fallback（LLM 失败，已回退模板——不当默默绿灯）",
        "reject_self_id": "reject_self_id（自述模型/代码被拒，已回退模板）",
        "llm": "llm",
    }
    print(f"[debug] 开口来源：{labels.get(src, src)}")
    print("[debug] 台下 ThoughtBrief（工程师通道）")
    print(json.dumps(asdict(result.brief), ensure_ascii=False, indent=2))


def _run_repl(args: argparse.Namespace) -> int:
    """多轮 REPL：首轮清场，之后同场；/new 再清。"""
    first = True
    force_new = False

    while True:
        try:
            line = input("> ")
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 0

        text = line.strip()
        if not text or text in _EXIT_WORDS:
            return 0
        if text == "/new":
            force_new = True
            print("[新场]")
            continue

        new_session = first or force_new
        first = False
        force_new = False

        result = turn(
            text,
            new_session=new_session,
            debug=args.debug,
            stub=True if args.stub else None,
        )
        _print_result(result, debug=args.debug)

    return 0  # pragma: no cover


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.stub:
        set_stub_mode(True)

    if args.user_text is None:
        return _run_repl(args)

    result = turn(
        args.user_text,
        new_session=args.new_session,
        debug=args.debug,
        stub=True if args.stub else None,
    )
    _print_result(result, debug=args.debug)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

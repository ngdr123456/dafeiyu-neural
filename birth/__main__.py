"""CLI demo：一期旁路闭环在命令行上跑。

用法：
    python -m birth                 # REPL 多轮（首轮清场；/new 新场；默认开跨场薄记忆）
    python -m birth --no-memory     # REPL 但关掉跨场持久
    python -m birth "你好"          # 单句；默认 DeepSeek，失败再 OpenCode；默认关记忆
    python -m birth --stub          # REPL + 强制模板 stub
    python -m birth "你好" --stub   # 单句 stub
    python -m birth --debug         # REPL + 工程师通道（开口来源＋Brief）
    python -m birth --no-sense      # 关闭默认开启的输入感知；--stub 自动关闭

REPL 内：空行 / exit / quit / q / EOF 退出；/new 开新场（先落盘本场再清）。
环境变量 BIRTH_MEMORY_PATH 可改持久文件路径（默认 ~/.dafeiyu/birth_memory.json）。
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .articulate import set_stub_mode
from .memory import PendingCommitmentCapacityError, configure_memory
from .pipeline import end_session, turn


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
    parser.add_argument("--no-sense", action="store_true", help="关掉输入感知（默认开；--stub 时自动关）")
    parser.add_argument("--new-session", action="store_true", help="显式开新场，清空同场积累")
    parser.add_argument(
        "--no-memory",
        action="store_true",
        help="关掉跨场薄记忆（REPL 默认开；单轮默认关）",
    )
    parser.add_argument(
        "--memory-path",
        default=None,
        help="跨场薄记忆 JSON 路径（默认 ~/.dafeiyu/birth_memory.json 或 BIRTH_MEMORY_PATH）",
    )
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
    signal = result.input_signal
    if signal is not None:
        suffix = f"（降级：{signal.reason}）" if signal.degraded else ""
        print(f"[debug] 输入信号：{signal.act}/{signal.addressee}/{signal.source}{suffix}")
    if result.brief.dominant_why:
        print(f"[debug] 仲裁取舍：{result.brief.dominant_why}")
    print("[debug] 台下 ThoughtBrief（工程师通道）")
    print(json.dumps(asdict(result.brief), ensure_ascii=False, indent=2))


def _run_repl(args: argparse.Namespace) -> int:
    """多轮 REPL：首轮清场，之后同场；/new 再清。"""
    first = True
    force_new = False

    def finish() -> int:
        try:
            end_session()
        except PendingCommitmentCapacityError:
            print("[记忆容量不足] 未结承诺超限，未写盘、未清场；仍在原场，可核对销账后再 /new。")
        return 0

    while True:
        try:
            line = input("> ")
        except EOFError:
            print()
            return finish()
        except KeyboardInterrupt:
            print()
            return finish()

        text = line.strip()
        if not text or text in _EXIT_WORDS:
            return finish()
        if text == "/new":
            force_new = True
            print("[新场]")
            continue

        new_session = first or force_new
        first = False
        force_new = False

        try:
            result = turn(
                text,
                new_session=new_session,
                debug=args.debug,
                stub=True if args.stub else None,
                sense=(not args.stub and not args.no_sense),
            )
        except PendingCommitmentCapacityError:
            print("[记忆容量不足] 未结承诺超限，未写盘、未清场；仍在原场，可核对销账后再 /new。")
            continue
        except KeyboardInterrupt:
            print()
            return finish()
        _print_result(result, debug=args.debug)

    return 0  # pragma: no cover


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.stub:
        set_stub_mode(True)

    if args.user_text is None:
        # REPL：默认开跨场薄记忆；--no-memory 关
        configure_memory(
            enabled=not args.no_memory,
            path=args.memory_path,
        )
        return _run_repl(args)

    # 单轮：默认关记忆（除非显式要开——当前无 --memory 开旗，保持关）
    configure_memory(enabled=False, path=args.memory_path)
    result = turn(
        args.user_text,
        new_session=args.new_session,
        debug=args.debug,
        stub=True if args.stub else None,
        sense=(not args.stub and not args.no_sense),
    )
    _print_result(result, debug=args.debug)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

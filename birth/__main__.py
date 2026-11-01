"""CLI demo：一期旁路闭环在命令行上跑一句。

用法：
    python -m birth "你好"              # 默认 DeepSeek API，失败再 OpenCode
    python -m birth "你好" --stub       # 强制模板 stub
    python -m birth "你好" --debug      # 额外打印台下 Brief（工程师通道）
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .articulate import set_stub_mode
from .pipeline import turn


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="birth",
        description="第一期旁路模块：感知/动力/立场/组织/仲裁/开口最小闭环",
    )
    parser.add_argument("user_text", nargs="?", default="你好", help="用户这一轮说的话（默认「你好」）")
    parser.add_argument("--debug", action="store_true", help="打印台下 Brief（工程师通道）")
    parser.add_argument("--stub", action="store_true", help="强制模板开口，不调 DeepSeek/OpenCode")
    parser.add_argument("--new-session", action="store_true", help="显式开新场，清空同场积累")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.stub:
        set_stub_mode(True)
    result = turn(
        args.user_text,
        new_session=args.new_session,
        debug=args.debug,
        stub=True if args.stub else None,
    )

    print(result.utterance)

    if args.debug:
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
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

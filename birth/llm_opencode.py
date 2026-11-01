"""用本机 OpenCode 免费模型做 ThoughtBrief → 台上人话。

失败（无二进制、超时、空输出、校验不过）由调用方回退 stub；这里不抛业务异常。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Optional

from .types import ThoughtBrief

DEFAULT_MODEL = os.environ.get("BIRTH_OPENCODE_MODEL", "opencode/deepseek-v4.1-flash-free")
DEFAULT_TIMEOUT_S = float(os.environ.get("BIRTH_OPENCODE_TIMEOUT", "90"))


def brief_to_prompt(brief: ThoughtBrief) -> str:
    """say_intent + 同场薄痕迹 + 不可装作；不把 Brief 字段名说出口。"""
    must_not = "、".join(brief.must_not_pretend) or "无"
    ctx = brief.context
    facts = list(ctx.facts_this_session or [])[-5:]
    if facts:
        fact_block = "\n".join(f"- {f}" for f in facts)
    else:
        fact_block = "- （本场尚无记下的痕迹）"
    extras: list[str] = []
    if ctx.open_questions:
        extras.append(f"同场悬着：{ctx.open_questions[0]}")
    if ctx.last_commitments:
        extras.append(f"同场说过要做的：{ctx.last_commitments[0]}")
    extra_block = ("\n".join(extras) + "\n") if extras else ""
    posture_zh = {
        "yieldable": "可退让",
        "non_negotiable": "不可交",
        "needs_clarify": "先澄清",
    }.get(brief.stance.posture, "可退让")
    stake = brief.stance.stake or "接住这一轮"
    return (
        "你在对话里开口。只输出这一轮要说的中文人话（一两句），"
        "不要解释、不要列点、不要加引号，不要写内部字段名。\n"
        f"这一轮要传达的意思：{brief.say_intent}\n"
        f"这一轮怎么站：{posture_zh}——{stake}\n"
        "本场已知（薄，仅供接话，勿当性格/自传）：\n"
        f"{fact_block}\n"
        f"{extra_block}"
        f"绝不能装作：{must_not}\n"
        "硬禁止：不要说自己是模型/代码/程序/语言模型；"
        "不要说「对，我是…」「本质上就是…」；"
        "不要说「这些话是程序生成的／代码算出来的／语言模型在生成」；"
        "招呼里也不要自报底层。"
        "身份问：不认死成说明书，也不装另一头；可以说从自己这边看不着、说不清。"
        "接同场回指时，用上面的本场痕迹点一下话题，不装没发生过，也不编场外经历。"
        "紧贴上面的意思，只输出台上那句话。"
    )


def _parse_json_lines(stdout: str) -> str:
    chunks: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "text":
            continue
        part = obj.get("part") or {}
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            chunks.append(text.strip())
    return "\n".join(chunks).strip()


def generate_utterance(brief: ThoughtBrief) -> Optional[str]:
    """调用 OpenCode 免费模型；成功返回人话，否则 None。"""
    binary = shutil.which("opencode")
    if not binary:
        return None

    prompt = brief_to_prompt(brief)
    cmd = [
        binary,
        "run",
        "--standalone",
        "--model",
        DEFAULT_MODEL,
        "--format",
        "json",
        prompt,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT_S,
            cwd="/tmp",
            env={**os.environ, "NO_COLOR": "1"},
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if proc.returncode != 0 and not proc.stdout.strip():
        return None

    text = _parse_json_lines(proc.stdout)
    if not text:
        lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        text = lines[-1] if lines else ""
    return text or None

"""birth 专用 DeepSeek 薄客户端（ThoughtBrief → 台上人话）。

形态可对照 engine/understand 的 urllib POST，但**禁止** import engine.*。
密钥：DEEPSEEK_API_KEY 或 ~/.dsh/.credentials.yaml；永不写入仓库/日志。
"""

from __future__ import annotations

import io
import json
import os
import re
import urllib.error
import urllib.request
from typing import Optional

from .types import ThoughtBrief

DEFAULT_BASE = "https://api.deepseek.com"
# 官方：deepseek-flash = DeepSeek-V4.1-Flash；旧习惯 DEEPSEEK_MODEL 亦可用
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_TIMEOUT_S = float(os.environ.get("BIRTH_DEEPSEEK_TIMEOUT", "60"))


def load_api_key() -> Optional[str]:
    """优先环境变量，其次 ~/.dsh/.credentials.yaml 的 DEEPSEEK_API_KEY 行。"""
    k = os.environ.get("DEEPSEEK_API_KEY")
    if k and k.strip():
        return k.strip()
    path = os.path.join(os.path.expanduser("~"), ".dsh", ".credentials.yaml")
    if not os.path.exists(path):
        return None
    try:
        with io.open(path, encoding="utf-8", errors="ignore") as handle:
            raw = handle.read()
    except OSError:
        return None
    m = re.search(r"DEEPSEEK_API_KEY:\s*(\S+)", raw)
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'") or None


def available() -> bool:
    return bool(load_api_key())


def resolve_model() -> str:
    return (
        os.environ.get("BIRTH_DEEPSEEK_MODEL")
        or os.environ.get("DEEPSEEK_MODEL")
        or DEFAULT_MODEL
    )


def resolve_base() -> str:
    return (
        os.environ.get("BIRTH_DEEPSEEK_BASE_URL")
        or os.environ.get("DEEPSEEK_BASE_URL")
        or DEFAULT_BASE
    ).rstrip("/")


def _brief_prompt(brief: ThoughtBrief) -> str:
    from .llm_opencode import brief_to_prompt

    return brief_to_prompt(brief)


def _extract_content(payload: dict) -> Optional[str]:
    try:
        choices = payload.get("choices") or []
        if not choices:
            return None
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    except (AttributeError, IndexError, KeyError, TypeError):
        return None
    return None


def generate_utterance(brief: ThoughtBrief) -> Optional[str]:
    """有密钥则 POST /chat/completions；失败返回 None（由调用方兜底）。"""
    key = load_api_key()
    if not key:
        return None

    body = {
        "model": resolve_model(),
        "messages": [
            {"role": "user", "content": _brief_prompt(brief)},
        ],
        "max_tokens": 256,
        # 开口不是填表：略高于理解层 temperature=0；thinking 关掉省预算
        "temperature": float(os.environ.get("BIRTH_DEEPSEEK_TEMPERATURE", "0.7")),
        "thinking": {"type": "disabled"},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        resolve_base() + "/chat/completions",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    except Exception:
        return None

    return _extract_content(payload)

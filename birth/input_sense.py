"""这是感知不是仲裁：只看本轮这一句，不带上下文，也不产 direction。

模型不可用时明确降级，而不是沉默造假。
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request

from . import llm_deepseek
from .input_contract import InputSignal


def _post_json(url: str, body: dict, key: str, timeout: float) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def sense_input(user_text: str, *, timeout: float | None = None) -> InputSignal | None:
    if not user_text.strip():
        return None
    model = llm_deepseek.resolve_model()
    source = f"model:{model}"
    provenance = "birth/input_sense.py:sense_input"

    def degraded(reason: str) -> InputSignal:
        return InputSignal("unknown", "unclear", source, provenance, True, reason)

    key = llm_deepseek.load_api_key()
    if not key:
        return degraded("no_key")
    prompt = (
        '判断下面本轮话语的言语行为和对象。只输出一个 JSON 对象：'
        '{"act":"ask|request|ack|tell|unknown","addressee":"other|self|unclear",'
        '"confidence":"high|medium|low"}。\n'
        'act：ask 是询问；request 是请求做事；ack 是回应或确认；tell 是陈述；unknown 是无法判断。'
        'addressee：other 是直接对正在回应的对方说；self 是对说话者自己说；unclear 是对象不明。'
        'confidence：high 是高置信，medium 是中置信，low 是低置信。'
        '按整句意思判断，不要猜关键词；不确定就用 unknown/unclear/low。'
        '不要解释、不要 markdown、不要多余文字。\n话语：' + user_text
    )
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 120, "temperature": 0, "thinking": {"type": "disabled"}}
    if timeout is None:
        timeout = float(os.environ.get("BIRTH_SENSE_TIMEOUT", "12"))
    try:
        payload = _post_json(llm_deepseek.resolve_base() + "/chat/completions", body, key, timeout)
    except urllib.error.HTTPError as exc:
        return degraded(f"http_{exc.code}")
    except urllib.error.URLError as exc:
        return degraded("timeout" if isinstance(exc.reason, (TimeoutError, socket.timeout)) else "network")
    except (TimeoutError, socket.timeout):
        return degraded("timeout")
    except OSError:
        return degraded("network")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return degraded("invalid_json")
    except Exception:
        return degraded("network")

    try:
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            return degraded("invalid_output")
    except (KeyError, IndexError, TypeError):
        return degraded("invalid_output")
    content = content.replace("```", "")
    start, end = content.find("{"), content.rfind("}")
    try:
        value = json.loads(content[start:end + 1] if start >= 0 and end >= start else content)
    except (json.JSONDecodeError, ValueError):
        return degraded("invalid_json")
    if not isinstance(value, dict) or any(
        not isinstance(value.get(field), str) or value[field] not in allowed
        for field, allowed in (
            ("act", ("ask", "request", "ack", "tell", "unknown")),
            ("addressee", ("other", "self", "unclear")),
            ("confidence", ("high", "medium", "low")),
        )
    ):
        return degraded("invalid_output")
    low = value["confidence"] == "low"
    return InputSignal(value["act"], value["addressee"], source, provenance,
                       low, "low_confidence" if low else "")

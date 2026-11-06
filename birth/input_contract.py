"""上游结构化信号的契约，不是感知器；本模块不判断原始文本。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .types import DriveSignal


@dataclass(frozen=True)
class InputSignal:
    act: Literal["ask", "request", "pause", "stop", "ack", "tell", "unknown"]
    addressee: Literal["other", "self", "unclear"]
    source: str
    provenance: str
    degraded: bool = False
    reason: str = ""
    scope: Literal["conversation", "task", "unclear"] = "unclear"

    def __post_init__(self) -> None:
        if self.scope not in ("conversation", "task", "unclear"):
            raise ValueError("invalid scope")
        if self.act not in ("ask", "request", "pause", "stop", "ack", "tell", "unknown"):
            raise ValueError("invalid act")
        if self.addressee not in ("other", "self", "unclear"):
            raise ValueError("invalid addressee")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must not be blank")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("provenance must not be blank")


def drive_signal_from_input(signal: InputSignal | None) -> DriveSignal | None:
    if signal is None or signal.degraded:
        return None
    # 对象感：只把对我说的话当缺口。
    if signal.addressee != "other":
        return None
    if signal.act == "ask":
        return DriveSignal(direction="pursue", salience="mid",
                           why=f"输入信号｜问句｜{signal.source}｜缺口在外，顺着答")
    if signal.act == "request":
        return DriveSignal(direction="pursue", salience="mid",
                           why=f"输入信号｜请求｜{signal.source}｜缺口在外，顺着接")
    if signal.act in ("pause", "stop") and signal.scope == "task":
        return DriveSignal(direction="pursue", salience="mid",
                           why=f"输入信号｜请求｜{signal.source}｜接住具体任务")
    if signal.act == "pause" and signal.scope == "conversation":
        return DriveSignal(direction="hold", salience="low",
                           why=f"输入信号｜暂停｜{signal.source}｜对方要我暂停")
    if signal.act == "stop" and signal.scope == "conversation":
        return DriveSignal(direction="hold", salience="low",
                           why=f"输入信号｜终止｜{signal.source}｜对方要终止")
    return None

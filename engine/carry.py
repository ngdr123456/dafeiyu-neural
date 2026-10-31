# -*- coding: utf-8 -*-
"""跨场累积：**未解张力**的持久化与衰减注入（D-011）。

用户裁定（2026-10-02，第 5 步）
────────────────────────────────────────────────────────────
> 「1. **落盘格式与文件隔离**：严格落地为 `state/mechanism_carry.json`
>    （**独立于 `devlevel.json`**，守住"张力衰减"与"心智只升不降"的物理隔离）；
>    字段锁定为：`tension`、`unfinished`、`at`（ISO-8601 带时区）、`schema: 1`；
>    衰减系数严格按**自然时间**计算：
>        `dt_h = (now - at).total_seconds() / 3600.0`
>        `decay = 0.5 ** (dt_h / C.HALF_LIFE_H)`
>  2. **写入时机、注入点与判据**：
>    注入点：`Pipeline.__init__` 时检测并读取 `mechanism_carry.json`，
>            计算衰减后显式传参 `Mechanism(..., initial_tension=tension_0)`；
>    写盘时机：`Pipeline.turn()` 每轮产出快照后，
>            若 `unfinished == True` 且 `tension > 0` 则**原子覆写**；
>            若 `unfinished == False` 则调用 `clear_carry()` 清空；
>    判据：**严格复用机制层原生的 `unfinished` 信号**，不新造外层主观逻辑。」

为什么与 `devlevel.json` 分开
────────────────────────────────────────────────────────────
    一个**会衰减**（张力），一个**只升不降**（发展水平）。
    混在一个文件里会让"只升不降"那条不变量失效 —— 那是整个箭头 A1 的地基。
"""
from __future__ import annotations

import io
import json
import os
import time
from datetime import datetime, timezone

import constants as C          # noqa: E402  —— SSOT

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)

SCHEMA = 1
DEFAULT_PATH = os.path.join(_ROOT, "state", "mechanism_carry.json")


def path(root: str | None = None) -> str:
    """carry 文件的路径。传 `root` 便于测试隔离。"""
    if root:
        return os.path.join(root, "state", "mechanism_carry.json")
    return os.path.join(os.environ.get("EGO_ROOT") or _ROOT,
                        "state", "mechanism_carry.json")


def read(root: str | None = None) -> dict | None:
    """读上一场的未解张力。**读不到/坏了都返回 None**（不抛，不猜）。"""
    p = path(root)
    if not os.path.exists(p):
        return None
    try:
        with io.open(p, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict) or d.get("schema") != SCHEMA:
            return None                      # 版本对不上 → 当没有，**不猜**
        if d.get("tension") is None or not d.get("at"):
            return None
        return d
    except Exception:                        # noqa: BLE001
        return None


def decayed_tension(root: str | None = None, now: datetime | None = None) -> float:
    """读上一场的张力并按**自然时间**衰减。没有就返回 0.0。

    用户裁定的公式（原样落地）：
        dt_h  = (now - at).total_seconds() / 3600.0
        decay = 0.5 ** (dt_h / C.HALF_LIFE_H)
    """
    d = read(root)
    if not d:
        return 0.0
    try:
        at = datetime.fromisoformat(d["at"])
    except Exception:                        # noqa: BLE001
        return 0.0
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)  # 老数据没带时区 → 按 UTC 当
    n = now or datetime.now(timezone.utc)
    dt_h = (n - at).total_seconds() / 3600.0
    if dt_h < 0:
        # 时钟回拨：**不放大**，按"刚存下"处理（宁可少衰减，不可凭空增张力）
        dt_h = 0.0
    decay = 0.5 ** (dt_h / C.HALF_LIFE_H)
    return float(d["tension"]) * decay


def write(tension: float, unfinished: bool, root: str | None = None) -> None:
    """**原子覆写**（写临时文件 + os.replace）。"""
    p = path(root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    d = {"_note": "上一场未解的张力，跨会话携带。衰减后注入下一场。",
         "tension": round(float(tension), 4),
         "unfinished": bool(unfinished),
         "at": datetime.now(timezone.utc).astimezone().isoformat(),
         "schema": SCHEMA}
    tmp = p + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False, indent=1) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def clear(root: str | None = None) -> None:
    """解决了就清掉 —— 留着会让下一场凭空带上一个已经解决的张力。"""
    p = path(root)
    try:
        if os.path.exists(p):
            os.remove(p)
    except Exception:                        # noqa: BLE001
        pass


def update_from_snapshot(snap: dict, root: str | None = None) -> str:
    """按用户裁定的判据处理一轮快照。返回做了什么（便于测试与日志）。

    判据**严格复用机制层原生的 `unfinished`**，不新造外层逻辑。
    """
    u = bool(snap.get("unfinished"))
    t = float(snap.get("tension") or 0.0)
    if not u:
        clear(root)
        return "cleared"
    if t > 0:
        write(t, True, root)
        return "written"
    return "kept"                            # 未解但张力为 0 → 什么都不做

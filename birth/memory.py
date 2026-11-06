"""跨场薄记忆：本地 JSON 持久层（非长期人格、非意识海）。

默认路径 ~/.dafeiyu/birth_memory.json；可用 BIRTH_MEMORY_PATH 或
BirthMemoryStore(path=...) 覆盖。测试必须传 tmp_path，绝不写真实 home。

场结束／new_session 时由 pipeline 写入本场薄痕迹；新场开局读入为
ThinContext.prior_session（结构字段，不拼进 say_intent）。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, TypeVar

from .types import CommitmentCandidate, PriorSessionTrace, StanceTrace

# 环境变量：覆盖默认路径
ENV_MEMORY_PATH = "BIRTH_MEMORY_PATH"

DEFAULT_MAX_SESSIONS = 5
DEFAULT_MAX_FACTS = 40
DEFAULT_MAX_COMMITS = 20
DEFAULT_MAX_PENDING_COMMITS = 1000
DEFAULT_MAX_OPENQ = 10
DEFAULT_MAX_TRACES = 20


def default_memory_path() -> Path:
    """生产默认路径；测试勿用，应显式传 tmp。"""
    override = os.environ.get(ENV_MEMORY_PATH, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".dafeiyu" / "birth_memory.json"


@dataclass
class SessionTraceRecord:
    """一场结束时落盘的薄痕迹。"""

    facts: List[str] = field(default_factory=list)
    commitments_pending: List[str] = field(default_factory=list)
    commitments_resolved: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    ended_at: str = ""
    stance_traces: List[StanceTrace] = field(default_factory=list)
    her_questions: List[str] = field(default_factory=list)

    commitment_candidates: List[CommitmentCandidate] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.facts
            or self.commitments_pending
            or self.commitments_resolved
            or self.open_questions
            or self.her_questions
            or self.stance_traces
            or self.commitment_candidates
        )

    def to_prior(self) -> PriorSessionTrace:
        return PriorSessionTrace(
            commitment_candidates=[replace(c) for c in self.commitment_candidates],
            facts=list(self.facts),
            commitments_pending=list(self.commitments_pending),
            commitments_resolved=list(self.commitments_resolved),
            open_questions=list(self.open_questions),
            her_questions=list(self.her_questions),
            ended_at=self.ended_at,
            stance_traces=[StanceTrace(t.kind, t.point, t.why) for t in self.stance_traces],
        )


_T = TypeVar("_T")


class PendingCommitmentCapacityError(OverflowError):
    """未结债容量不足；不得写盘或清场，调用方可保留当前场后重试。"""


def _clip_list(items: List[_T], limit: int) -> List[_T]:
    if limit <= 0:
        return []
    if len(items) <= limit:
        return list(items)
    return list(items[-limit:])


class BirthMemoryStore:
    """最小持久层：最近 N 场 JSON；容量上限＋老化。"""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        max_facts: int = DEFAULT_MAX_FACTS,
        max_commits: int = DEFAULT_MAX_COMMITS,
        max_openq: int = DEFAULT_MAX_OPENQ,
        max_traces: int = DEFAULT_MAX_TRACES,
        max_pending_commits: int = DEFAULT_MAX_PENDING_COMMITS,
    ) -> None:
        self.path = Path(path) if path is not None else default_memory_path()
        self.max_sessions = max(1, int(max_sessions))
        self.max_facts = max(0, int(max_facts))
        self.max_commits = max(0, int(max_commits))
        self.max_pending_commits = max(1, int(max_pending_commits))
        self.max_openq = max(0, int(max_openq))
        self.max_traces = max(0, int(max_traces))

    def _read_raw(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if isinstance(data, dict) and "sessions" in data:
            sessions = data.get("sessions") or []
        elif isinstance(data, list):
            sessions = data
        else:
            sessions = []
        return [s for s in sessions if isinstance(s, dict)]

    def _write_raw(self, sessions: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "sessions": sessions}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_sessions(self) -> list[SessionTraceRecord]:
        out: list[SessionTraceRecord] = []
        for raw in self._read_raw():
            raw_traces = raw.get("stance_traces")
            traces = []
            if isinstance(raw_traces, list):
                for item in raw_traces:
                    if (isinstance(item, dict) and item.get("kind") == "kept"
                            and isinstance(item.get("point"), str) and item["point"].strip()):
                        why = item.get("why")
                        traces.append(StanceTrace(item["kind"], item["point"].strip(),
                                                  why.strip() if isinstance(why, str) else ""))
            candidates = []
            raw_candidates = raw.get("commitment_candidates")
            if isinstance(raw_candidates, list):
                for item in raw_candidates:
                    if not isinstance(item, dict):
                        continue
                    text, target = item.get("text"), item.get("target")
                    frame, source = item.get("frame"), item.get("source", "")
                    if (isinstance(text, str) and text.strip() and isinstance(target, str)
                            and target.strip() and frame in ("prior_press", "same_session_press")
                            and isinstance(source, str)):
                        candidates.append(CommitmentCandidate(text, target, frame, source))
            out.append(
                SessionTraceRecord(
                    commitment_candidates=[c for c in candidates if c.target in (raw.get("commitments_pending") or [])],
                    facts=list(raw.get("facts") or []),
                    commitments_pending=list(raw.get("commitments_pending") or []),
                    commitments_resolved=list(raw.get("commitments_resolved") or []),
                    open_questions=list(raw.get("open_questions") or []),
                    her_questions=list(raw.get("her_questions") or []),
                    ended_at=str(raw.get("ended_at") or ""),
                    stance_traces=traces,
                )
            )
        return out

    def latest(self) -> SessionTraceRecord | None:
        sessions = self.list_sessions()
        return sessions[-1] if sessions else None

    def latest_prior(self) -> PriorSessionTrace | None:
        rec = self.latest()
        return rec.to_prior() if rec is not None else None

    def append_session(
        self,
        *,
        facts: List[str] | None = None,
        commitments_pending: List[str] | None = None,
        commitments_resolved: List[str] | None = None,
        open_questions: List[str] | None = None,
        her_questions: List[str] | None = None,
        ended_at: str | None = None,
        stance_traces: List[StanceTrace] | None = None,
        commitment_candidates: List[CommitmentCandidate] | None = None,
    ) -> SessionTraceRecord | None:
        """写入一场痕迹；历史有界，未结债超限拒绝写入并保留现场。"""
        unique_traces = []
        pending = list(dict.fromkeys(commitments_pending or []))
        if len(pending) > self.max_pending_commits:
            # 先拒绝、再写盘；pipeline 尚未清场，调用者可提高容量后重试。
            raise PendingCommitmentCapacityError(
                f"pending commitments exceed capacity {self.max_pending_commits}; session retained"
            )
        candidates = []
        for c in commitment_candidates or []:
            if c.target in pending and c not in candidates:
                candidates.append(replace(c))
        seen = set()
        for trace in stance_traces or []:
            key = (trace.kind, trace.point)
            if key not in seen:
                seen.add(key)
                unique_traces.append(trace)
        rec = SessionTraceRecord(
            commitment_candidates=_clip_list(candidates, self.max_commits),
            facts=_clip_list(list(facts or []), self.max_facts),
            commitments_pending=pending,
            commitments_resolved=_clip_list(
                list(commitments_resolved or []), self.max_commits
            ),
            open_questions=_clip_list(list(open_questions or []), self.max_openq),
            her_questions=_clip_list(list(her_questions or []), self.max_openq),
            stance_traces=_clip_list(unique_traces, self.max_traces),
            ended_at=ended_at
            or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        if rec.is_empty():
            return None
        sessions = self._read_raw()
        sessions.append(asdict(rec))
        if len(sessions) > self.max_sessions:
            sessions = sessions[-self.max_sessions :]
        self._write_raw(sessions)
        return rec


# 模块级：pipeline／CLI 配置（默认关，避免单测写 home）
_ENABLED: bool = False
_STORE: Optional[BirthMemoryStore] = None


def memory_enabled() -> bool:
    return _ENABLED


def active_memory() -> BirthMemoryStore | None:
    return _STORE if _ENABLED else None


def configure_memory(
    *,
    enabled: bool,
    path: str | Path | None = None,
    max_sessions: int = DEFAULT_MAX_SESSIONS,
    max_facts: int = DEFAULT_MAX_FACTS,
    max_commits: int = DEFAULT_MAX_COMMITS,
    max_openq: int = DEFAULT_MAX_OPENQ,
    max_pending_commits: int = DEFAULT_MAX_PENDING_COMMITS,
) -> BirthMemoryStore | None:
    """开／关跨场薄记忆。enabled=False 时不碰磁盘。"""
    global _ENABLED, _STORE
    _ENABLED = bool(enabled)
    if not _ENABLED:
        _STORE = None
        return None
    _STORE = BirthMemoryStore(
        path=path,
        max_sessions=max_sessions,
        max_facts=max_facts,
        max_commits=max_commits,
        max_openq=max_openq,
        max_pending_commits=max_pending_commits,
    )
    return _STORE

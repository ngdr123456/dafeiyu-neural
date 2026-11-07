"""跨场薄记忆：本地 JSON 持久层（非长期人格、非意识海）。

默认路径 ~/.dafeiyu/birth_memory.json；可用 BIRTH_MEMORY_PATH 或
BirthMemoryStore(path=...) 覆盖。测试必须传 tmp_path，绝不写真实 home。

场结束／new_session 时由 pipeline 写入本场薄痕迹；新场开局读入为
ThinContext.prior_session（结构字段，不拼进 say_intent）。
"""

from __future__ import annotations

import json
import os
import secrets
import stat
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, TypeVar

from .types import CommitmentCandidate, HerUtterance, PriorSessionTrace, StanceTrace

# 环境变量：覆盖默认路径
ENV_MEMORY_PATH = "BIRTH_MEMORY_PATH"

DEFAULT_MAX_SESSIONS = 5
DEFAULT_MAX_FACTS = 40
DEFAULT_MAX_COMMITS = 20
DEFAULT_MAX_PENDING_COMMITS = 1000
DEFAULT_MAX_OPENQ = 10
DEFAULT_MAX_TRACES = 20
DEFAULT_MAX_UTTERANCES = 200


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
    her_utterances: List[HerUtterance] = field(default_factory=list)
    record_metadata: dict | None = None

    def is_empty(self) -> bool:
        return not (
            self.facts
            or self.commitments_pending
            or self.commitments_resolved
            or self.open_questions
            or self.her_questions
            or self.stance_traces
            or self.commitment_candidates
            or self.her_utterances
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
        max_utterances: int = DEFAULT_MAX_UTTERANCES,
    ) -> None:
        self.path = Path(path) if path is not None else default_memory_path()
        self.max_sessions = max(1, int(max_sessions))
        self.max_facts = max(0, int(max_facts))
        self.max_commits = max(0, int(max_commits))
        self.max_pending_commits = max(1, int(max_pending_commits))
        self.max_openq = max(0, int(max_openq))
        self.max_traces = max(0, int(max_traces))
        self.max_utterances = max(0, int(max_utterances))

    def _read_raw(self) -> list[dict]:
        # Import lazily: retrieval uses BirthMemoryStore to load validated records.
        from .retrieval import _preflight_ledger

        return _preflight_ledger(self.path)

    def _write_raw(self, sessions: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "sessions": sessions}
        contents = json.dumps(payload, ensure_ascii=False, indent=2)
        try:
            mode = stat.S_IMODE(self.path.stat().st_mode)
        except FileNotFoundError:
            mode = None
        while True:
            temp_path = self.path.parent / f".{self.path.name}.{secrets.token_hex(8)}.tmp"
            try:
                fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
                break
            except FileExistsError:
                continue
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(contents)
            if mode is not None:
                os.chmod(temp_path, mode)
            os.replace(temp_path, self.path)
        finally:
            if temp_path.exists():
                if os.name == "nt":
                    os.chmod(temp_path, stat.S_IWRITE | stat.S_IREAD)
                temp_path.unlink()

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
            utterances = []
            raw_utterances = raw.get("her_utterances")
            if isinstance(raw_utterances, list):
                fields = ("text", "drive_direction", "stance_posture", "org_grain", "source")
                for item in raw_utterances:
                    if isinstance(item, dict) and all(isinstance(item.get(key), str) for key in fields):
                        utterances.append(HerUtterance(**{key: item[key] for key in fields},
                                                       complete=item.get("complete") is True))
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
                    her_utterances=utterances,
                    record_metadata=raw.get("record_metadata"),
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
        her_utterances: List[dict] | None = None,
        record_metadata: dict | None = None,
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
            her_utterances=_clip_list(
                [HerUtterance(**entry) for entry in (her_utterances or [])], self.max_utterances
            ),
            ended_at=ended_at
            or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        if rec.is_empty():
            return None
        if record_metadata is not None:
            # Align after the same capacity limits and trace deduplication as the records.
            def aligned(name, original, retained, key=lambda x: x):
                values = record_metadata.get(name)
                if not isinstance(values, list) or len(values) != len(original):
                    return [None] * len(retained)
                lookup = {}
                originals = {}
                for item, meta in zip(original, values):
                    k = key(item)
                    if k not in lookup:
                        lookup[k], originals[k] = meta, item
                    elif (lookup[k] != meta or originals[k] != item
                          or (isinstance(meta, dict) and (meta.get("truncated") or meta.get("subject_truncated")))):
                        lookup[k] = None
                return [lookup.get(key(item)) for item in retained]
            rec.record_metadata = {
                "facts": aligned("facts", list(facts or []), rec.facts),
                "open_questions": aligned("open_questions", list(open_questions or []), rec.open_questions),
                "her_questions": aligned("her_questions", list(her_questions or []), rec.her_questions),
                "stance_traces": aligned("stance_traces", list(stance_traces or []), rec.stance_traces, lambda t: (t.kind, t.point)),
            }
        sessions = self._read_raw()
        serialized = asdict(rec)
        if rec.record_metadata is None:
            serialized.pop("record_metadata")
        sessions.append(serialized)
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
    max_utterances: int = DEFAULT_MAX_UTTERANCES,
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
        max_utterances=max_utterances,
    )
    return _STORE

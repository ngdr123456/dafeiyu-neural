"""birth —— 旁路包的最小闭环公开 API。

对齐 PHASE1_BRIEF.md：无禁词闸门、无 boldness、无意识海新层、无「我是代码」自述；
OrgConstraint 只约束表达粒度，不永久否决动力。
"""

from .arbitrate import arbitrate
from .articulate import articulate, clear_llm_hook, set_llm_hook, validate
from .context import ThinContextStore
from .drive import infer_drive
from .pipeline import TurnResult, active_store, turn
from .stance_org import (
    MUST_NOT_PRETEND_CORE,
    default_org,
    default_stance,
    detect_org_conflict,
)
from .types import (
    DriveSignal,
    OrgConstraint,
    StanceSignal,
    ThoughtBrief,
    ThinContext,
)

__all__ = [
    # 类型
    "DriveSignal",
    "StanceSignal",
    "OrgConstraint",
    "ThinContext",
    "ThoughtBrief",
    # 组件
    "ThinContextStore",
    "infer_drive",
    "default_stance",
    "default_org",
    "detect_org_conflict",
    "MUST_NOT_PRETEND_CORE",
    "arbitrate",
    "articulate",
    "set_llm_hook",
    "clear_llm_hook",
    "validate",
    # 管线
    "turn",
    "active_store",
    "TurnResult",
]

__version__ = "0.1.0-phase1"

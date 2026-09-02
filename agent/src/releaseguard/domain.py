"""Agent 领域模型（CP0 种子版）。

定义 Investigation / Evidence / Finding / ActionProposal / IncidentReport 五类
核心对象。它们与 `contracts.py` 里的“线上契约报文”不同：contracts 描述 Agent 与
Ops Gateway 之间传输的原始报文；domain 描述 Agent 自身调查与推理得到的结构化结果。

CP1 的完整引擎将在此模型之上扩展状态机、持久化与报告；CP0 阶段只落基础 schema，
并用确定性 mock 调查把它们串成一次可复现的冒烟结果。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from releaseguard.contracts import SERVICE_PATTERN


def _require_tz(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("时间戳必须携带时区（RFC3339），例如 2026-09-02T14:36:00Z")
    return value


TzDateTime = Annotated[datetime, AfterValidator(_require_tz)]


class EvidenceType(str, Enum):
    """调查证据的来源种类，决定根因结论能引用哪些事实。"""

    DEPLOYMENT = "deployment"
    METRIC = "metric"
    LOG = "log"
    TRACE = "trace"
    GIT = "git"
    EVENT = "event"
    CONFIG = "config"


class InvestigationStatus(str, Enum):
    """调查状态机（与 docs 执行手册 §6 一致）。"""

    DETECTED = "DETECTED"
    COLLECTING = "COLLECTING"
    CORRELATING = "CORRELATING"
    DIAGNOSED = "DIAGNOSED"
    PROPOSED = "PROPOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    INCONCLUSIVE = "INCONCLUSIVE"


class Disposition(str, Enum):
    """单次调查对处置方向的结论。

    - INCONCLUSIVE：证据缺失或不可比较，不足以形成判断；
    - HOLD：已形成判断但尚不建议变更运行状态，等待补充证据或人工决策；
    - ROLLBACK_RELEASE / PROMOTE / ABORT：需要 Gateway 执行的处置建议。
    """

    INCONCLUSIVE = "INCONCLUSIVE"
    HOLD = "HOLD"
    ROLLBACK_RELEASE = "ROLLBACK_RELEASE"
    PROMOTE = "PROMOTE"
    ABORT = "ABORT"


class RiskLevel(str, Enum):
    """风险矩阵等级（与 docs 执行手册 §11 一致）。"""

    READ_ONLY = "READ_ONLY"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ActionKind(str, Enum):
    """可提交给 Gateway 的结构化动作（HOLD/INCONCLUSIVE 不是动作）。"""

    ROLLBACK_RELEASE = "ROLLBACK_RELEASE"
    PROMOTE = "PROMOTE"
    ABORT = "ABORT"


class Investigation(BaseModel):
    """一次针对发布回归的调查。"""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    environment: Literal["demo", "staging"]
    service: str = Field(pattern=SERVICE_PATTERN)
    baseline_version: str
    candidate_version: str
    deployment_id: str | None = None
    started_at: TzDateTime
    symptom: str
    status: InvestigationStatus = InvestigationStatus.DETECTED


class EvidenceQuality(BaseModel):
    """证据质量：新鲜、完整、可比较，缺一不可才值得被引用。"""

    model_config = ConfigDict(extra="forbid")

    fresh: bool = True
    complete: bool = True
    comparable: bool = True


class Evidence(BaseModel):
    """一条结构化证据。工具返回值必须转换为 Evidence，而不是把原始文本塞给模型。"""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    type: EvidenceType
    source: str
    service: str
    version: str | None = None
    observed_at: TzDateTime
    summary: str
    quality: EvidenceQuality = Field(default_factory=EvidenceQuality)
    value: float | None = None
    unit: str | None = None
    refs: list[str] = Field(default_factory=list)


class AlternativeHypothesis(BaseModel):
    """一个替代假设。若能被某条证据排除，则记录在 excluded_by 中。"""

    model_config = ConfigDict(extra="forbid")

    hypothesis: str
    confidence: float = Field(ge=0.0, le=1.0)
    excluded_by: list[str] = Field(default_factory=list)
    note: str | None = None


class Finding(BaseModel):
    """带证据引用的根因判断。

    规则（docs 执行手册 §10）：主要根因至少引用 2 种来源的证据；置信度高于 0.8 时
    至少说明一个被排除的替代原因；缺失的证据种类显式列出，绝不把“无数据”当作正常。
    """

    model_config = ConfigDict(extra="forbid")

    affected_service: str
    root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(min_length=2)
    alternative_hypotheses: list[AlternativeHypothesis] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class ActionTarget(BaseModel):
    """动作目标：environment、service、from_version、to_version 必须显式。"""

    model_config = ConfigDict(extra="forbid")

    environment: Literal["demo", "staging"]
    service: str = Field(pattern=SERVICE_PATTERN)
    from_version: str
    to_version: str


class ActionProposal(BaseModel):
    """可执行的结构化动作建议（对应写契约 RollbackRequest 的语义来源）。"""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    investigation_id: str
    action: ActionKind
    target: ActionTarget
    reason: str
    evidence_ids: list[str] = Field(min_length=1)
    risk: RiskLevel
    requires_approval: bool = True
    expires_at: TzDateTime | None = None


class IncidentReport(BaseModel):
    """一次冒烟调查的最终报告：区分事实（evidence）、推断（finding）与建议（proposal）。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    report_kind: Literal["INCIDENT"] = "INCIDENT"
    generated_at: TzDateTime
    investigation: Investigation
    decision: Disposition
    evidence: list[Evidence] = Field(default_factory=list)
    finding: Finding | None = None
    proposal: ActionProposal | None = None
    note: str | None = None


# ---------------------------------------------------------------------------
# 证据 grounding 常量与判定规则（确定性逻辑，不由 LLM 自评）
# ---------------------------------------------------------------------------

# 指标判定为“回归”的最小上升倍数与最小样本量。
REGRESSION_RATIO = 1.2
MIN_SAMPLE_COUNT = 100

# 推荐 ROLLBACK_RELEASE 至少要覆盖的来源（docs 执行手册 §10）：
# 部署证据 + 回归证据（metric）+ 变更证据（git）。
ROLLBACK_REQUIRED_TYPES: frozenset[EvidenceType] = frozenset(
    {EvidenceType.DEPLOYMENT, EvidenceType.METRIC, EvidenceType.GIT}
)

# 不同来源证据的展示顺序。
EVIDENCE_ORDER: dict[EvidenceType, int] = {
    EvidenceType.DEPLOYMENT: 0,
    EvidenceType.METRIC: 1,
    EvidenceType.GIT: 2,
    EvidenceType.LOG: 3,
    EvidenceType.TRACE: 4,
    EvidenceType.EVENT: 5,
    EvidenceType.CONFIG: 6,
}

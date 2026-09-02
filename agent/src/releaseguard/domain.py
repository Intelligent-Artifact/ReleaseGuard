"""ReleaseGuard 的核心领域模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    """返回带时区的 UTC 时间。"""
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    """拒绝未知字段的领域模型基类。"""

    model_config = ConfigDict(extra="forbid")


class InvestigationStatus(StrEnum):
    """调查图对外暴露的稳定状态。"""

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


class EvidenceQuality(StrictModel):
    """证据质量标记。"""

    fresh: bool
    complete: bool
    comparable: bool


class Evidence(StrictModel):
    """由 Ops Gateway 工具结果归一化而来的证据。"""

    evidence_id: str
    type: Literal["deployment", "metric"]
    source: str
    service: str
    version: str
    observed_at: datetime
    summary: str
    value: str | float | int | None = None
    unit: str | None = None
    query_ref: str
    raw_ref: str | None = None
    quality: EvidenceQuality


class AlternativeHypothesis(StrictModel):
    """待排除或已降权的替代假设。"""

    hypothesis: str
    confidence: float = Field(ge=0, le=1)
    rejected_by: list[str] = Field(default_factory=list)


class RootCauseFinding(StrictModel):
    """证据约束下的根因结论。"""

    root_cause: str
    affected_service: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(min_length=2)
    alternative_hypotheses: list[AlternativeHypothesis] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ActionTarget(StrictModel):
    """动作的不可歧义目标。"""

    environment: Literal["demo", "staging"]
    service: str
    from_version: str
    to_version: str


class ActionProposal(StrictModel):
    """受策略约束的动作建议。"""

    proposal_id: str
    investigation_id: str
    action: Literal["ROLLBACK_RELEASE", "HOLD"]
    target: ActionTarget
    reason: str
    evidence_ids: list[str]
    risk: Literal["READ_ONLY", "MEDIUM"]
    requires_approval: bool
    expires_at: datetime
    policy_rule_ids: list[str]


class ApprovalDecision(StrictModel):
    """用于恢复暂停图的人工审批输入。"""

    approved: bool
    approved_by: str = Field(min_length=1, max_length=128)
    token: str | None = Field(default=None, min_length=8, max_length=512)
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def require_approval_material(self) -> ApprovalDecision:
        """批准时必须同时提供 token 与过期时间。"""
        if self.approved and (not self.token or not self.expires_at):
            raise ValueError("批准 rollback 时必须提供 token 和 expires_at")
        return self


class StartInvestigation(StrictModel):
    """启动一次调查的 API 输入。"""

    environment: Literal["demo", "staging"] = "demo"
    service: str = Field(pattern=r"^[a-z][a-z0-9-]{1,62}$")
    symptom: str = Field(min_length=3, max_length=500)
    investigation_id: str | None = Field(default=None, pattern=r"^inv_[a-zA-Z0-9_-]+$")


class TransitionRecord(StrictModel):
    """一次可审计的状态转换。"""

    from_status: InvestigationStatus
    to_status: InvestigationStatus
    actor: Literal["agent", "user", "policy", "gateway"]
    occurred_at: datetime
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)


class ToolCallRecord(StrictModel):
    """模型工具调用的安全摘要。"""

    tool: str
    call_id: str
    succeeded: bool
    occurred_at: datetime
    error_code: str | None = None


class RunView(StrictModel):
    """图运行状态的稳定 API 投影。"""

    investigation_id: str
    status: InvestigationStatus
    environment: str
    service: str
    symptom: str
    baseline_version: str | None = None
    candidate_version: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    finding: RootCauseFinding | None = None
    proposal: ActionProposal | None = None
    action: dict[str, Any] | None = None
    transitions: list[TransitionRecord] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    interrupt: dict[str, Any] | None = None
    report_markdown: str | None = None


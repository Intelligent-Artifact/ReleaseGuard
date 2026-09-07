"""调查 harness 的运行输入、模型边界与执行记录。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from releaseguard.contracts import (
    SERVICE_PATTERN,
    DeploymentResponse,
    MetricsCompareResponse,
    TzDateTime,
)
from releaseguard.domain import Evidence, Finding, IncidentReport, Investigation


class InvestigationRequest(BaseModel):
    """由调用者确定调查范围，模型不能改写服务或环境。"""

    model_config = ConfigDict(extra="forbid")

    investigation_id: str = Field(
        default_factory=lambda: f"inv_{uuid4().hex}", pattern=r"^[a-zA-Z0-9_-]{1,80}$"
    )
    environment: Literal["demo", "staging"] = "demo"
    service: str = Field(default="payment-service", pattern=SERVICE_PATTERN)
    started_at: TzDateTime = Field(default_factory=lambda: datetime.now(timezone.utc))
    window: Literal["1m", "5m", "10m", "15m"] = "5m"
    symptom: str = "调查新版本是否引入指标回归"


class RunLimits(BaseModel):
    """异步适配器必须支持取消；超时或超限后停止调查。"""

    model_config = ConfigDict(extra="forbid")

    max_model_calls: int = Field(default=4, ge=1, le=100)
    max_tool_calls: int = Field(default=3, ge=1, le=100)
    call_timeout_seconds: float = Field(default=10, gt=0, le=300, allow_inf_nan=False)


class DeploymentQuery(BaseModel):
    """部署查询工具的受限参数。"""

    model_config = ConfigDict(extra="forbid")

    environment: Literal["demo", "staging"]
    service: str = Field(pattern=SERVICE_PATTERN)


class MetricsQuery(DeploymentQuery):
    """指标查询必须绑定部署返回的两个明确版本。"""

    baseline: str = Field(min_length=1)
    candidate: str = Field(min_length=1)
    window: Literal["1m", "5m", "10m", "15m"]


class ToolCall(BaseModel):
    """最小 harness 只注册两个只读工具。"""

    model_config = ConfigDict(extra="forbid")

    name: Literal["get_deployment", "compare_metrics"]
    arguments: dict[str, str]


class ModelTurn(BaseModel):
    """模型一次只请求一个工具，或提交最终判断。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["tool", "finish"]
    tool_call: ToolCall | None = None
    finding: Finding | None = None

    @model_validator(mode="after")
    def validate_turn(self) -> ModelTurn:
        """禁止同时调用工具并宣布最终结论。"""
        if self.kind == "tool" and (self.tool_call is None or self.finding is not None):
            raise ValueError("工具轮次必须包含工具请求且不能包含结论")
        if self.kind == "finish" and self.tool_call is not None:
            raise ValueError("结束轮次不能包含工具请求")
        return self


class ModelContext(BaseModel):
    """传给模型的调查快照，不含 fixture 路径、动作凭据或标准答案。"""

    model_config = ConfigDict(extra="forbid")

    request: InvestigationRequest
    investigation: Investigation
    deployment: DeploymentResponse | None = None
    metrics: MetricsCompareResponse | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    draft_finding: Finding | None = None


class ModelAdapter(Protocol):
    """真实模型和离线替身共用的异步入口。"""

    async def next_turn(self, context: ModelContext) -> ModelTurn:
        """根据只读快照选择下一步。"""
        ...


class DeterministicModel:
    """离线测试替身：按部署、指标、结束的顺序运行，不调用 LLM。"""

    async def next_turn(self, context: ModelContext) -> ModelTurn:
        """以现有确定性规则生成的草稿作为最终判断。"""
        scope = {
            "environment": context.request.environment,
            "service": context.request.service,
        }
        if context.deployment is None:
            return ModelTurn(
                kind="tool", tool_call=ToolCall(name="get_deployment", arguments=scope)
            )
        if context.metrics is None and context.deployment.previous is not None:
            return ModelTurn(
                kind="tool",
                tool_call=ToolCall(
                    name="compare_metrics",
                    arguments={
                        **scope,
                        "baseline": context.deployment.previous.version,
                        "candidate": context.deployment.current.version,
                        "window": context.request.window,
                    },
                ),
            )
        return ModelTurn(kind="finish", finding=context.draft_finding)


class RunEvent(BaseModel):
    """按执行顺序保存节点与工具结果，不保存原始异常或凭据。"""

    node: str
    outcome: str
    detail: str = ""


class HarnessResult(BaseModel):
    """调查报告与运行记录；成功结束不等于已经定位根因。"""

    report: IncidentReport
    events: list[RunEvent]
    model_calls: int
    tool_calls: int
    error: str | None = None

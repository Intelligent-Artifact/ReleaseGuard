"""只读 LangChain tools 及其证据归一化逻辑。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from releaseguard.domain import Evidence, EvidenceQuality
from releaseguard.gateway import OpsGateway


class ToolArgs(BaseModel):
    """拒绝模型传入未声明字段。"""

    model_config = ConfigDict(extra="forbid")


class GetDeploymentArgs(ToolArgs):
    """部署查询参数。"""

    environment: Literal["demo", "staging"]
    service: str = Field(pattern=r"^[a-z][a-z0-9-]{1,62}$")


class CompareMetricsArgs(GetDeploymentArgs):
    """受限指标模板参数。"""

    baseline: str = Field(min_length=1, max_length=128)
    candidate: str = Field(min_length=1, max_length=128)
    window: Literal["1m", "5m", "10m", "15m"] = "5m"


def build_read_tools(gateway: OpsGateway) -> list[StructuredTool]:
    """创建模型唯一可见的只读工具集合。"""

    def get_deployment(environment: str, service: str) -> dict[str, Any]:
        return gateway.get_deployment(environment, service)

    def compare_metrics(
        environment: str,
        service: str,
        baseline: str,
        candidate: str,
        window: str = "5m",
    ) -> dict[str, Any]:
        return gateway.compare_metrics(environment, service, baseline, candidate, window)

    return [
        StructuredTool.from_function(
            func=get_deployment,
            name="get_deployment",
            description="通过 Ops Gateway 获取服务当前版本、上一版本、commit 与 rollout 状态。只读。",
            args_schema=GetDeploymentArgs,
        ),
        StructuredTool.from_function(
            func=compare_metrics,
            name="compare_metrics",
            description="通过固定指标模板比较 baseline 与 candidate。不得传入 PromQL。只读。",
            args_schema=CompareMetricsArgs,
        ),
    ]


def deployment_evidence(payload: dict[str, Any]) -> list[Evidence]:
    """将部署响应转成统一 Evidence。"""
    current = payload["current"]
    source_refs = payload.get("source_refs") or []
    return [
        Evidence(
            evidence_id=f"deployment:{payload['service']}:{current['commit_sha']}",
            type="deployment",
            source="ops_gateway",
            service=payload["service"],
            version=current["version"],
            observed_at=datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00")),
            summary=(
                f"{payload['service']} 当前版本 {current['version']}，commit {current['commit_sha']}，"
                f"rollout 状态 {payload['rollout']['status']}"
            ),
            value=payload["rollout"]["candidate_weight"],
            unit="percent",
            query_ref=payload["request_id"],
            raw_ref=source_refs[0] if source_refs else None,
            quality=EvidenceQuality(fresh=True, complete=True, comparable=True),
        )
    ]


def metrics_evidence(payload: dict[str, Any]) -> list[Evidence]:
    """将每个聚合指标转成独立 Evidence。"""
    observed_at = datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00"))
    source_refs = payload.get("source_refs") or []
    output: list[Evidence] = []
    for metric in payload.get("metrics", []):
        output.append(
            Evidence(
                evidence_id=(
                    f"metric:{payload['service']}:{metric['name']}:"
                    f"{payload['candidate']}:{payload['request_id']}"
                ),
                type="metric",
                source="prometheus",
                service=payload["service"],
                version=payload["candidate"],
                observed_at=observed_at,
                summary=(
                    f"{metric['name']}：candidate={metric['candidate_value']}，"
                    f"baseline={metric['baseline_value']}，样本数={metric['sample_count']}"
                ),
                value=metric["candidate_value"],
                unit=metric["unit"],
                query_ref=payload["request_id"],
                raw_ref=source_refs[0] if source_refs else None,
                quality=EvidenceQuality(
                    fresh=True,
                    complete=metric["sample_count"] > 0,
                    comparable=metric["comparable"],
                ),
            )
        )
    return output


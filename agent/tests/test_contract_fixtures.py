"""共享契约 fixture 的符合性测试（Agent 消费方视角）。

验证 contracts/examples/*.json 满足 OpenAPI v0.1 的结构与语义约束，例如：
必填字段、枚举、service 命名、带时区的时间格式、稳定错误码与 additionalProperties=false。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from releaseguard.contracts import (
    DeploymentResponse,
    ErrorCode,
    ErrorResponse,
    MetricsCompareResponse,
    RollbackRequest,
    load_shared_fixtures,
)


@pytest.fixture(scope="module")
def bundle():
    """一次加载仓库共享契约 fixture。"""
    loaded = load_shared_fixtures()
    assert loaded.ok, f"共享 fixture 加载失败：{loaded.errors}"
    return loaded


class TestFixture加载与结构:
    def test_三个共享fixture全部加载(self, bundle):
        assert bundle.deployment is not None
        assert bundle.metrics is not None
        assert bundle.rollback_request is not None

    def test_响应包含request_id与生成时间(self, bundle):
        for resp in (bundle.deployment, bundle.metrics):
            assert resp.request_id
            assert resp.generated_at.tzinfo is not None  # RFC3339 带时区


class TestDeployment契约语义:
    def test_部署环境与服务命名(self, bundle):
        assert bundle.deployment.environment == "demo"
        assert bundle.deployment.service == "payment-service"

    def test_当前候选与上一基线版本(self, bundle):
        current = bundle.deployment.current
        assert current.version == "v2"
        assert current.commit_sha  # 可追溯到 commit
        assert bundle.deployment.previous is not None
        assert bundle.deployment.previous.version == "v1"

    def test_rollout权重在合法范围(self, bundle):
        rollout = bundle.deployment.rollout
        assert rollout.status.value == "PROGRESSING"
        assert 0 <= rollout.candidate_weight <= 100


class TestMetrics契约语义:
    def test_指标比较字段完整(self, bundle):
        names = {m.name.value for m in bundle.metrics.metrics}
        assert {"p95_latency", "error_rate"}.issubset(names)

    def test_示例展示candidate回归(self, bundle):
        p95 = next(m for m in bundle.metrics.metrics if m.name.value == "p95_latency")
        assert p95.comparable is True
        assert p95.sample_count >= 100
        assert p95.candidate_value > p95.baseline_value  # 用于演示候选回归


class TestRollback请求契约语义:
    def test_风险仅MEDIUM且需审批(self, bundle):
        request = bundle.rollback_request
        assert request.risk == "MEDIUM"
        assert request.from_version == "v2"
        assert request.to_version == "v1"
        assert request.approval.token
        assert request.approval.expires_at > request.approval.approved_at

    def test_额外字段被禁止(self, bundle):
        """additionalProperties=false：契约之外的新字段应被拒绝，防止静默漂移。"""
        payload = bundle.rollback_request.model_dump()
        payload["mystery_field"] = "x"
        with pytest.raises(ValidationError):
            RollbackRequest.model_validate(payload)

    def test_风险超出枚举被拒绝(self, bundle):
        payload = bundle.rollback_request.model_dump()
        payload["risk"] = "HIGH"  # OpenAPI 当前只允许 MEDIUM
        with pytest.raises(ValidationError):
            RollbackRequest.model_validate(payload)


class Test契约底层语义约束:
    def test_无时区时间被拒绝(self, bundle):
        """CP0 明确时间格式：比较时间必须带时区。"""
        payload = bundle.metrics.model_dump()
        payload["generated_at"] = "2026-09-02T14:36:30"  # 去掉 Z，变成 naive
        with pytest.raises(ValidationError):
            MetricsCompareResponse.model_validate(payload)

    def test_稳定错误码全覆盖(self):
        """Agent 只依据稳定 code 判断：全部十个错误码都能被模型解析。"""
        for code in ErrorCode:
            parsed = ErrorResponse(
                request_id="req_1",
                code=code,
                message="仅供人读的错误说明，不参与 Agent 逻辑判断",
            )
            assert parsed.code == code

    def test_service命名约束(self, bundle):
        payload = bundle.deployment.model_dump()
        payload["service"] = "Payment-Service_1"  # 违反 ^[a-z][a-z0-9-]{1,62}$
        with pytest.raises(ValidationError):
            DeploymentResponse.model_validate(payload)


class Test契约必填字段漂移:
    """openapi.yaml 里 DeploymentResponse/MetricsCompareResponse 的 warnings 与
    source_refs 均为 required（可为空数组但字段必须存在），模型必须拦截缺失，
    防止对契约的静默漂移。"""

    def _drift_payload(self, model, resp, drop: str) -> dict:
        payload = resp.model_dump()
        payload.pop(drop)
        return payload

    def test_缺warnings的部署响应被拒绝(self, bundle):
        with pytest.raises(ValidationError):
            DeploymentResponse.model_validate(
                self._drift_payload(DeploymentResponse, bundle.deployment, "warnings")
            )

    def test_缺source_refs的部署响应被拒绝(self, bundle):
        with pytest.raises(ValidationError):
            DeploymentResponse.model_validate(
                self._drift_payload(DeploymentResponse, bundle.deployment, "source_refs")
            )

    def test_缺warnings的指标比较响应被拒绝(self, bundle):
        with pytest.raises(ValidationError):
            MetricsCompareResponse.model_validate(
                self._drift_payload(MetricsCompareResponse, bundle.metrics, "warnings")
            )

    def test_缺source_refs的指标比较响应被拒绝(self, bundle):
        with pytest.raises(ValidationError):
            MetricsCompareResponse.model_validate(
                self._drift_payload(MetricsCompareResponse, bundle.metrics, "source_refs")
            )

    def test_必填数组字段未退化回默认值(self, bundle):
        """护栏：warnings/source_refs 必须是 required（无默认值）。
        若有人重新加回 default_factory，此测试会失败，提示与 openapi.yaml 重新对齐。"""
        for resp in (bundle.deployment, bundle.metrics):
            fields = type(resp).model_fields
            for field in ("warnings", "source_refs"):
                assert fields[field].is_required(), (
                    f"{type(resp).__name__}.{field} 不应有默认值（openapi 中为 required）"
                )

"""确定性 mock 调查（CP0）流水线测试。

覆盖：正常回归→HOLD、数据缺失→INCONCLUSIVE、证据齐备→ROLLBACK_RELEASE、
非可比指标不误判、证据全可溯源、输出确定可复现、Markdown 区分事实/推断/建议。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from releaseguard.contracts import (
    Approval,
    MetricsCompareResponse,
    RollbackRequest,
    load_shared_fixtures,
)
from releaseguard.domain import (
    Disposition,
    Evidence,
    EvidenceType,
    Finding,
    IncidentReport,
    Investigation,
    InvestigationStatus,
    RiskLevel,
)
from releaseguard.report import render_markdown, to_json
from releaseguard.smoke import decide, evidence_from_metrics, run_smoke

# 固定的演示时间与 commit，保持与 contracts/examples 语义一致。
T0 = datetime(2026, 9, 2, 14, 36, 30, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def shared_bundle():
    """仓库共享契约 fixture。"""
    loaded = load_shared_fixtures()
    assert loaded.ok
    return loaded


@pytest.fixture(scope="module")
def shared_report(shared_bundle) -> IncidentReport:
    return run_smoke(shared_bundle)


def _metric(name: str, baseline: float, candidate: float, *, comparable: bool = True, sample: int = 840):
    return {
        "name": name,
        "unit": "ms" if name == "p95_latency" else "ratio",
        "baseline_value": baseline,
        "candidate_value": candidate,
        "sample_count": sample,
        "comparable": comparable,
    }


def _metrics_response(*rows) -> MetricsCompareResponse:
    payload = {
        "request_id": "req_metrics_test",
        "generated_at": "2026-09-02T14:36:30Z",
        "environment": "demo",
        "service": "payment-service",
        "baseline": "v1",
        "candidate": "v2",
        "window": "5m",
        "metrics": list(rows),
        "warnings": [],
        "source_refs": ["prometheus:query/test"],
    }
    return MetricsCompareResponse.model_validate(payload)


class Test确定性调查:
    def test_正常回归输出HOLD且不越权(self, shared_report):
        """候选回归已确认，但缺变更证据 → 保守 HOLD，不自动回滚。"""
        assert shared_report.decision == Disposition.HOLD
        assert shared_report.proposal is None  # 未触发任何执行动作
        assert shared_report.finding is not None
        assert shared_report.investigation.status == InvestigationStatus.DIAGNOSED

    def test_证据覆盖两种来源(self, shared_report):
        types = {item.type for item in shared_report.evidence}
        assert EvidenceType.DEPLOYMENT in types
        assert EvidenceType.METRIC in types
        # 缺失的证据被如实记录，不把“无数据”当正常。
        assert shared_report.finding.missing_evidence == ["git", "log", "trace"]

    def test_引用证据全部可溯源(self, shared_report):
        """Grounding 规则：finding 只引用真实存在、确实落入本调查的证据 ID。"""
        known_ids = {item.evidence_id for item in shared_report.evidence}
        assert set(shared_report.finding.evidence_ids) == known_ids
        # 结论必须引用 >=2 种来源。
        referenced = {
            next(item.type for item in shared_report.evidence if item.evidence_id == eid)
            for eid in shared_report.finding.evidence_ids
        }
        assert len(referenced) >= 2

    def test_不编造SQL级结论(self, shared_report):
        limitations = shared_report.finding.limitations
        assert any("未声称定位到具体 SQL" in text for text in limitations)

    def test_重复运行结果一致(self, shared_bundle):
        """确定性：不依赖随机数与当前时间，重复运行得到相同报告。"""
        first = run_smoke(shared_bundle).model_dump(mode="json")
        second = run_smoke(shared_bundle).model_dump(mode="json")
        assert first == second


class Test回归判定与降级:
    def test_fixture标记p95与错误率回归(self, shared_bundle):
        _, regressed = evidence_from_metrics(shared_bundle)
        assert "p95_latency" in regressed
        assert "error_rate" in regressed

    def test_不可比指标不判定为回归(self):
        bundle = load_shared_fixtures()
        # candidate 数值更高但 comparable=False：属于数据不可比，不当作回归。
        bundle.metrics = _metrics_response(
            _metric("p95_latency", 100, 900, comparable=False)
        )
        evidence, regressed = evidence_from_metrics(bundle)
        assert regressed == []
        assert evidence and evidence[0].quality.comparable is False

    def test_指标缺失降级为INCONCLUSIVE(self):
        bundle = load_shared_fixtures()
        bundle.metrics = None
        report = run_smoke(bundle)
        assert report.decision == Disposition.INCONCLUSIVE
        assert report.finding is None
        assert report.proposal is None


class Test处置裁决:
    def _investigation(self) -> Investigation:
        return Investigation(
            investigation_id="inv_test_001",
            environment="demo",
            service="payment-service",
            baseline_version="v1",
            candidate_version="v2",
            started_at=T0,
            symptom="p95 延迟回归",
        )

    def _evidence_of(self, *types: EvidenceType) -> list[Evidence]:
        """按类型构造最小证据（用于裁决规则的白盒测试）。"""
        out: list[Evidence] = []
        for kind in types:
            out.append(
                Evidence(
                    evidence_id=f"test:{kind.value}:001",
                    type=kind,
                    source=f"source-{kind.value}",
                    service="payment-service",
                    version="v2",
                    observed_at=T0,
                    summary=f"{kind.value} 证据",
                )
            )
        return out

    def test_部署加指标加变更证据齐备则建议回滚(self):
        investigation = self._investigation()
        evidence = self._evidence_of(
            EvidenceType.DEPLOYMENT, EvidenceType.METRIC, EvidenceType.GIT
        )
        finding = Finding(
            affected_service="payment-service",
            root_cause="candidate v2 引入变更导致 p95 回归",
            confidence=0.7,
            evidence_ids=[item.evidence_id for item in evidence],
            missing_evidence=["log", "trace"],
        )
        decision, proposal, _ = decide(investigation, evidence, finding)
        assert decision == Disposition.ROLLBACK_RELEASE
        assert proposal is not None
        assert proposal.risk == RiskLevel.MEDIUM
        assert proposal.requires_approval is True
        assert proposal.target.from_version == "v2"
        assert proposal.target.to_version == "v1"

    def test_回滚建议符合写契约RollbackRequest形状(self):
        """Agent 产出的建议能无损映射到 OpenAPI 的 RollbackRequest，双方形状一致。"""
        investigation = self._investigation()
        evidence = self._evidence_of(
            EvidenceType.DEPLOYMENT, EvidenceType.METRIC, EvidenceType.GIT
        )
        finding = Finding(
            affected_service="payment-service",
            root_cause="candidate v2 引入变更导致 p95 回归",
            confidence=0.8,
            evidence_ids=[item.evidence_id for item in evidence],
        )
        _, proposal, _ = decide(investigation, evidence, finding)
        # 用契约模型校验：若字段不符，此处会抛 ValidationError。
        request = RollbackRequest.model_validate(
            {
                "proposal_id": proposal.proposal_id,
                "investigation_id": proposal.investigation_id,
                "environment": proposal.target.environment,
                "service": proposal.target.service,
                "from_version": proposal.target.from_version,
                "to_version": proposal.target.to_version,
                "risk": proposal.risk.value,
                "approval": Approval(
                    token="test-token",
                    approved_by="test-operator",
                    approved_at="2026-09-02T14:37:00Z",
                    expires_at="2026-09-02T14:42:00Z",
                ).model_dump(mode="json"),
            }
        )
        assert request.risk == "MEDIUM"
        assert request.from_version == "v2"
        assert request.to_version == "v1"

    def test_部署加指标但缺变更证据时HOLD(self):
        investigation = self._investigation()
        evidence = self._evidence_of(EvidenceType.DEPLOYMENT, EvidenceType.METRIC)
        finding = Finding(
            affected_service="payment-service",
            root_cause="candidate 方向回归",
            confidence=0.65,
            evidence_ids=[item.evidence_id for item in evidence],
            missing_evidence=["git", "log", "trace"],
        )
        decision, proposal, _ = decide(investigation, evidence, finding)
        assert decision == Disposition.HOLD
        assert proposal is None

    def test_未形成判断时INCONCLUSIVE(self):
        """finding 为空（未检测到回归或数据不可比）→ 保守 INCONCLUSIVE，无动作。"""
        investigation = self._investigation()
        evidence = self._evidence_of(EvidenceType.DEPLOYMENT)
        decision, proposal, message = decide(investigation, evidence, None)
        assert decision == Disposition.INCONCLUSIVE
        assert proposal is None
        assert "不触发任何执行动作" in message


class Test报告输出:
    def test_markdown区分事实推断建议(self, shared_report):
        md = render_markdown(shared_report)
        for section in ("## 摘要", "## 事实", "## 推断", "## 缺失证据", "## 建议"):
            assert section in md

    def test_json可解析且字段完整(self, shared_report):
        payload = to_json(shared_report)
        assert '"report_kind": "INCIDENT"' in payload
        assert '"evidence"' in payload
        assert '"finding"' in payload
        assert '"note"' in payload

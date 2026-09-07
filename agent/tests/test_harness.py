"""通过实际 LangGraph 运行验证调查结果、隔离边界和失败出口。"""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from releaseguard.contracts import load_shared_fixtures
from releaseguard.domain import Disposition, InvestigationStatus
from releaseguard.harness import InvestigationHarness, main
from releaseguard.harness_models import (
    DeterministicModel,
    InvestigationRequest,
    ModelTurn,
    RunLimits,
    ToolCall,
)
from releaseguard.smoke import run_smoke


class MemoryGateway:
    """替换数据源，无文件读取或 HTTP，验证图只依赖客户端接口。"""

    def __init__(self):
        bundle = load_shared_fixtures()
        self.deployment = bundle.deployment.model_dump(mode="json")
        self.metrics = bundle.metrics.model_dump(mode="json")
        self.calls = []

    async def get_deployment(self, query):
        self.calls.append("get_deployment")
        return deepcopy(self.deployment)

    async def compare_metrics(self, query):
        self.calls.append("compare_metrics")
        return deepcopy(self.metrics)


@pytest.fixture
def request_input():
    return InvestigationRequest(
        investigation_id="inv_harness_test",
        started_at=datetime(2026, 9, 2, 14, 36, 30, tzinfo=timezone.utc),
    )


def run(gateway, request, model=None, limits=None):
    """同步测试驱动实际异步图，不替换 LangGraph 实现。"""
    return asyncio.run(InvestigationHarness(gateway, model, limits).run(request))


def test_正常调查复用种子结论并保留运行轨迹(request_input):
    result = run(MemoryGateway(), request_input)
    original = run_smoke(load_shared_fixtures())
    assert result.report.decision == Disposition.HOLD
    assert result.report.finding == original.finding
    assert result.report.evidence == original.evidence
    assert result.report.proposal is None
    assert (
        result.report.investigation.investigation_id == request_input.investigation_id
    )
    assert result.error is None
    assert result.model_calls == 3 and result.tool_calls == 2
    assert [event.detail for event in result.events if event.node == "tool"] == [
        "get_deployment",
        "compare_metrics",
    ]
    assert result.events[-1].outcome == "HOLD"


@pytest.mark.parametrize("field,value", [("comparable", False), ("sample_count", 0)])
def test_不可比或样本不足时不产生结论(request_input, field, value):
    gateway = MemoryGateway()
    for metric in gateway.metrics["metrics"]:
        metric[field] = value
    result = run(gateway, request_input)
    assert result.report.decision == Disposition.INCONCLUSIVE
    assert result.report.finding is None and result.report.proposal is None
    assert all(not e.quality.comparable for e in result.report.evidence[1:])
    assert result.error is None


def test_未回归时保留事实并结束(request_input):
    gateway = MemoryGateway()
    for metric in gateway.metrics["metrics"]:
        metric["candidate_value"] = metric["baseline_value"]
    result = run(gateway, request_input)
    assert result.report.decision == Disposition.INCONCLUSIVE
    assert result.report.finding is None
    assert len(result.report.evidence) == 3


def test_未约定方向的指标不能触发回归(request_input):
    gateway = MemoryGateway()
    gateway.metrics["metrics"] = [
        {
            "name": "request_rate",
            "unit": "rps",
            "baseline_value": 100,
            "candidate_value": 900,
            "sample_count": 1000,
            "comparable": True,
        }
    ]
    result = run(gateway, request_input)
    assert result.report.decision == Disposition.INCONCLUSIVE
    assert result.report.finding is None


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("deployment", "service", "other-service"),
        ("deployment", "environment", "staging"),
        ("metrics", "service", "other-service"),
        ("metrics", "environment", "staging"),
        ("metrics", "baseline", "v0"),
        ("metrics", "candidate", "v3"),
        ("metrics", "window", "15m"),
    ],
)
def test_错误上下文的响应被拒绝(request_input, section, field, value):
    gateway = MemoryGateway()
    getattr(gateway, section)[field] = value
    result = run(gateway, request_input)
    assert result.error == "CONTEXT_MISMATCH"
    assert result.report.decision == Disposition.INCONCLUSIVE
    assert result.report.finding is None
    assert len(result.report.evidence) == (0 if section == "deployment" else 1)


def test_缺少上一版本时不查询指标(request_input):
    gateway = MemoryGateway()
    gateway.deployment.pop("previous")
    result = run(gateway, request_input)
    assert gateway.calls == ["get_deployment"]
    assert result.report.decision == Disposition.INCONCLUSIVE
    assert result.report.proposal is None


def test_无效响应保留此前已验证的证据(request_input):
    gateway = MemoryGateway()
    gateway.metrics.pop("warnings")
    result = run(gateway, request_input)
    assert result.error == "INVALID_RESPONSE"
    assert len(result.report.evidence) == 1
    assert result.report.investigation.status == InvestigationStatus.INCONCLUSIVE


class RepeatingModel:
    """反复请求同一工具，用于检验框架能否主动结束循环。"""

    async def next_turn(self, context):
        return ModelTurn(
            kind="tool",
            tool_call=ToolCall(
                name="get_deployment",
                arguments={
                    "environment": context.request.environment,
                    "service": context.request.service,
                },
            ),
        )


@pytest.mark.parametrize(
    "limits,expected_calls",
    [
        (RunLimits(max_model_calls=2, max_tool_calls=10), (2, 2)),
        (RunLimits(max_model_calls=10, max_tool_calls=1), (2, 1)),
    ],
)
def test_模型和工具预算都能终止循环(request_input, limits, expected_calls):
    gateway = MemoryGateway()
    result = run(gateway, request_input, RepeatingModel(), limits)
    assert result.error == "BUDGET_EXHAUSTED"
    assert (result.model_calls, result.tool_calls) == expected_calls
    assert len(gateway.calls) == result.tool_calls
    assert len(result.report.evidence) == 1
    assert result.report.decision == Disposition.INCONCLUSIVE
    assert result.events[-1].node == "report"


@pytest.mark.parametrize(
    "tool,args,error",
    [
        ("rollback", {}, "INVALID_MODEL_OUTPUT"),
        (
            "get_deployment",
            {"service": "other-service", "environment": "demo"},
            "INVALID_TOOL_CALL",
        ),
        (
            "get_deployment",
            {"service": "payment-service", "environment": "staging"},
            "INVALID_TOOL_CALL",
        ),
        (
            "get_deployment",
            {"service": "payment-service", "environment": "demo", "command": "x"},
            "INVALID_TOOL_CALL",
        ),
        (
            "compare_metrics",
            {
                "service": "payment-service",
                "environment": "demo",
                "baseline": "v1",
                "candidate": "v2",
                "window": "5m",
            },
            "INVALID_TOOL_CALL",
        ),
    ],
)
def test_非法工具或目标在数据源调用前被拦截(request_input, tool, args, error):
    class InvalidModel:
        async def next_turn(self, context):
            return {"kind": "tool", "tool_call": {"name": tool, "arguments": args}}

    gateway = MemoryGateway()
    result = run(gateway, request_input, InvalidModel())
    assert result.error == error
    assert gateway.calls == []
    assert result.report.proposal is None


@pytest.mark.parametrize(
    "corruption",
    ["unknown_id", "duplicate_id", "service", "confidence", "alternative_id"],
)
def test_模型结论必须通过证据校验(request_input, corruption):
    class InvalidFindingModel(DeterministicModel):
        async def next_turn(self, context):
            turn = await super().next_turn(context)
            if turn.finding is not None:
                if corruption == "unknown_id":
                    turn.finding.evidence_ids[0] = "invented"
                elif corruption == "duplicate_id":
                    turn.finding.evidence_ids.append(turn.finding.evidence_ids[0])
                elif corruption == "service":
                    turn.finding.affected_service = "other-service"
                elif corruption == "confidence":
                    turn.finding.confidence = 0.99
                else:
                    turn.finding.alternative_hypotheses[0].excluded_by = ["invented"]
            return turn

    result = run(MemoryGateway(), request_input, InvalidFindingModel())
    assert result.error == "INVALID_FINDING"
    assert result.report.finding is None and result.report.proposal is None
    assert len(result.report.evidence) == 3


@pytest.mark.parametrize("component", ["model", "gateway"])
def test_异步调用超时会取消并生成失败报告(request_input, component):
    cancelled = []

    async def stall():
        try:
            await asyncio.sleep(5)
        finally:
            cancelled.append(True)

    class SlowModel:
        async def next_turn(self, context):
            await stall()

    class SlowGateway(MemoryGateway):
        async def get_deployment(self, query):
            await stall()

    result = run(
        SlowGateway() if component == "gateway" else MemoryGateway(),
        request_input,
        SlowModel() if component == "model" else None,
        RunLimits(call_timeout_seconds=0.01),
    )
    assert result.error == ("MODEL_TIMEOUT" if component == "model" else "TOOL_TIMEOUT")
    assert cancelled == [True]
    assert result.report.decision == Disposition.INCONCLUSIVE


def test_模型修改快照不会污染调查(request_input):
    class MutatingModel(DeterministicModel):
        async def next_turn(self, context):
            turn = await super().next_turn(context)
            context.investigation.service = "other-service"
            context.request.service = "other-service"
            context.evidence.clear()
            return turn

    result = run(MemoryGateway(), request_input, MutatingModel())
    assert result.error is None
    assert result.report.investigation.service == "payment-service"
    assert request_input.service == "payment-service"
    assert len(result.report.evidence) == 3


def test_重复和并发运行不共享状态(request_input):
    harness = InvestigationHarness(MemoryGateway())

    async def both():
        return await asyncio.gather(
            harness.run(request_input), harness.run(request_input)
        )

    first, second = asyncio.run(both())
    assert first == second
    assert first == asyncio.run(harness.run(request_input))
    first.report.evidence.clear()
    assert len(second.report.evidence) == 3


def test_fixture替身不需要回滚凭据且CLI保存轨迹(tmp_path, capsys):
    gateway = MemoryGateway()
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    for filename, data in [
        ("deployment-response.json", gateway.deployment),
        ("metrics-compare-response.json", gateway.metrics),
    ]:
        (fixtures / filename).write_text(json.dumps(data), encoding="utf-8")
    output = tmp_path / "reports"
    code = main(["--fixtures-dir", str(fixtures), "--output-dir", str(output)])
    assert code == 0
    assert "HOLD" in capsys.readouterr().out
    payload = json.loads(next(output.glob("run-*.json")).read_text(encoding="utf-8"))
    assert payload["report"]["decision"] == "HOLD"
    assert payload["tool_calls"] == 2
    assert len(list(output.glob("incident-*"))) == 2


def test_缺失fixture仍保存失败报告(tmp_path, capsys):
    output = tmp_path / "reports"
    assert main(["--fixtures-dir", str(tmp_path), "--output-dir", str(output)]) == 1
    assert "INCONCLUSIVE" in capsys.readouterr().out
    payload = json.loads(next(output.glob("run-*.json")).read_text(encoding="utf-8"))
    assert payload["error"] == "DATA_UNAVAILABLE"
    assert payload["report"]["evidence"] == []

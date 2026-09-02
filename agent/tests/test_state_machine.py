"""Investigation 领域状态机单元测试。"""

import pytest

from releaseguard.domain import InvestigationStatus
from releaseguard.state_machine import (
    PROMPT_VERSION,
    TERMINAL_STATUSES,
    InvalidInvestigationTransition,
    InvestigationStateMachine,
)


def make_machine() -> InvestigationStateMachine:
    """创建带固定版本信息的测试状态机。"""
    return InvestigationStateMachine(model_version="fixture-model")


def test_documented_happy_path_is_accepted():
    """手册定义的批准并恢复路径必须完整可达。"""
    machine = make_machine()
    path = [
        InvestigationStatus.DETECTED,
        InvestigationStatus.COLLECTING,
        InvestigationStatus.CORRELATING,
        InvestigationStatus.DIAGNOSED,
        InvestigationStatus.PROPOSED,
        InvestigationStatus.AWAITING_APPROVAL,
        InvestigationStatus.EXECUTING,
        InvestigationStatus.VERIFYING,
        InvestigationStatus.RESOLVED,
    ]

    records = [
        machine.transition(source, target, "agent", "测试合法转换")
        for source, target in zip(path, path[1:])
    ]

    assert [record.to_status for record in records] == path[1:]
    assert all(record.model_version == "fixture-model" for record in records)
    assert all(record.prompt_version == PROMPT_VERSION for record in records)


def test_skipping_required_states_is_rejected():
    """不能绕过证据收集、策略或审批直接执行。"""
    machine = make_machine()

    with pytest.raises(InvalidInvestigationTransition, match="DETECTED -> EXECUTING"):
        machine.transition(
            InvestigationStatus.DETECTED,
            InvestigationStatus.EXECUTING,
            "agent",
            "尝试绕过调查与审批",
        )

    with pytest.raises(InvalidInvestigationTransition, match="PROPOSED -> EXECUTING"):
        machine.transition(
            InvestigationStatus.PROPOSED,
            InvestigationStatus.EXECUTING,
            "policy",
            "尝试绕过人工审批",
        )


@pytest.mark.parametrize("terminal_status", sorted(TERMINAL_STATUSES, key=str))
def test_terminal_states_cannot_be_resumed(terminal_status):
    """所有终态都禁止继续转换，避免重复动作。"""
    machine = make_machine()

    with pytest.raises(InvalidInvestigationTransition):
        machine.transition(
            terminal_status,
            InvestigationStatus.COLLECTING,
            "agent",
            "尝试恢复终态调查",
        )


def test_transition_persists_required_audit_metadata():
    """转换记录包含手册要求的版本、工具、错误与重试信息。"""
    machine = make_machine()

    record = machine.transition(
        InvestigationStatus.COLLECTING,
        InvestigationStatus.INCONCLUSIVE,
        "agent",
        "遥测查询连续失败，停止重试",
        evidence_ids=["metric:1", "metric:1"],
        tool_calls=[
            {"tool": "compare_metrics", "succeeded": False, "error_code": "TIMEOUT"}
        ],
        error={"code": "TIMEOUT", "phase": "collect", "message": "指标查询超时"},
        retry_count=2,
    )

    assert record.evidence_ids == ["metric:1"]
    assert record.tool_calls[0].tool == "compare_metrics"
    assert record.error.code == "TIMEOUT"
    assert record.retry_count == 2

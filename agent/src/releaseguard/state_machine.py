"""Investigation 领域状态机及审计记录构造。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

from releaseguard.domain import (
    InvestigationStatus,
    TransitionError,
    TransitionRecord,
    TransitionToolSummary,
    utc_now,
)

TransitionActor = Literal["agent", "user", "policy", "gateway"]

PROMPT_VERSION = "releaseguard-investigation-v1"


class InvalidInvestigationTransition(ValueError):
    """请求的 Investigation 状态转换不符合领域规则。"""


_ALLOWED_TRANSITIONS = MappingProxyType(
    {
        InvestigationStatus.DETECTED: frozenset({InvestigationStatus.COLLECTING}),
        InvestigationStatus.COLLECTING: frozenset(
            {InvestigationStatus.CORRELATING, InvestigationStatus.INCONCLUSIVE}
        ),
        InvestigationStatus.CORRELATING: frozenset(
            {InvestigationStatus.DIAGNOSED, InvestigationStatus.INCONCLUSIVE}
        ),
        InvestigationStatus.DIAGNOSED: frozenset(
            {InvestigationStatus.PROPOSED, InvestigationStatus.INCONCLUSIVE}
        ),
        InvestigationStatus.PROPOSED: frozenset(
            {InvestigationStatus.AWAITING_APPROVAL}
        ),
        InvestigationStatus.AWAITING_APPROVAL: frozenset(
            {
                InvestigationStatus.EXECUTING,
                InvestigationStatus.REJECTED,
                InvestigationStatus.EXPIRED,
            }
        ),
        InvestigationStatus.EXECUTING: frozenset(
            {InvestigationStatus.VERIFYING, InvestigationStatus.RECOVERY_FAILED}
        ),
        InvestigationStatus.VERIFYING: frozenset(
            {InvestigationStatus.RESOLVED, InvestigationStatus.RECOVERY_FAILED}
        ),
        InvestigationStatus.RESOLVED: frozenset(),
        InvestigationStatus.RECOVERY_FAILED: frozenset(),
        InvestigationStatus.REJECTED: frozenset(),
        InvestigationStatus.EXPIRED: frozenset(),
        InvestigationStatus.INCONCLUSIVE: frozenset(),
    }
)

TERMINAL_STATUSES = frozenset(
    status for status, targets in _ALLOWED_TRANSITIONS.items() if not targets
)


@dataclass(frozen=True, slots=True)
class InvestigationStateMachine:
    """校验领域转换并生成完整、可持久化的审计记录。"""

    model_version: str
    prompt_version: str = PROMPT_VERSION

    @staticmethod
    def allowed_targets(status: InvestigationStatus | str) -> frozenset[InvestigationStatus]:
        """返回指定状态允许到达的下一状态。"""
        return _ALLOWED_TRANSITIONS[InvestigationStatus(status)]

    @classmethod
    def is_terminal(cls, status: InvestigationStatus | str) -> bool:
        """判断状态是否为不可继续转换的终态。"""
        return InvestigationStatus(status) in TERMINAL_STATUSES

    @classmethod
    def can_transition(
        cls,
        from_status: InvestigationStatus | str,
        to_status: InvestigationStatus | str,
    ) -> bool:
        """判断一个状态转换是否符合领域规则。"""
        source = InvestigationStatus(from_status)
        target = InvestigationStatus(to_status)
        return target in _ALLOWED_TRANSITIONS[source]

    def transition(
        self,
        from_status: InvestigationStatus | str,
        to_status: InvestigationStatus | str,
        actor: TransitionActor,
        reason: str,
        *,
        evidence_ids: Iterable[str] = (),
        tool_calls: Iterable[Mapping[str, Any]] = (),
        error: Mapping[str, Any] | TransitionError | None = None,
        retry_count: int = 0,
    ) -> TransitionRecord:
        """校验并创建一次状态转换，非法转换立即失败。"""
        source = InvestigationStatus(from_status)
        target = InvestigationStatus(to_status)
        if not self.can_transition(source, target):
            allowed = ", ".join(item.value for item in self.allowed_targets(source)) or "无"
            raise InvalidInvestigationTransition(
                f"非法调查状态转换：{source.value} -> {target.value}；允许目标：{allowed}"
            )
        summaries = [
            TransitionToolSummary(
                tool=str(item["tool"]),
                succeeded=bool(item["succeeded"]),
                error_code=item.get("error_code"),
            )
            for item in tool_calls
        ]
        transition_error = (
            error
            if isinstance(error, TransitionError)
            else TransitionError.model_validate(error) if error is not None else None
        )
        return TransitionRecord(
            from_status=source,
            to_status=target,
            actor=actor,
            occurred_at=utc_now(),
            reason=reason,
            evidence_ids=list(dict.fromkeys(evidence_ids)),
            model_version=self.model_version,
            prompt_version=self.prompt_version,
            tool_calls=summaries,
            error=transition_error,
            retry_count=retry_count,
        )

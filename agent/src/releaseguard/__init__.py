"""ReleaseGuard Agent —— Developer Preview 契约冒烟测试。

Developer Preview 目标（参见 docs/PROJECT_DIRECTION_AND_CHECKPOINTS.md §8）：

- Agent 在没有任何真实基础设施时，也能读取共享契约 fixture，
  完成一次确定性的 mock 调查，并输出区分事实/推断/建议的事故报告。

原有 smoke 入口保留确定性调查；harness 入口使用 LangGraph 编排同类调查，
当前均无需真实模型或基础设施。
"""

from __future__ import annotations

__version__ = "0.1.0"

from releaseguard.domain import (
    ActionProposal,
    Evidence,
    Finding,
    IncidentReport,
    Investigation,
)

__all__ = [
    "__version__",
    "Investigation",
    "Evidence",
    "Finding",
    "ActionProposal",
    "IncidentReport",
]

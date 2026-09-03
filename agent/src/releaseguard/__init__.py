"""ReleaseGuard Agent —— CP0 契约冒烟测试。

CP0 目标（参见 docs/PROJECT_DIRECTION_AND_CHECKPOINTS.md §8）：

- Agent 在没有任何真实基础设施时，也能读取共享契约 fixture，
  完成一次确定性的 mock 调查，并输出区分事实/推断/建议的事故报告。

本包不依赖 langgraph / langchain / LLM，只依赖 pydantic，便于在任何干净
环境里快速复现“测试夹具 → Finding → 报告”的最小闭环。
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

"""离线 slow SQL 调查演示。"""

from __future__ import annotations

import json
from datetime import timedelta
from uuid import uuid4

from releaseguard.domain import ApprovalDecision, StartInvestigation, utc_now
from releaseguard.runtime import AgentRuntime


def main() -> None:
    """运行一次暂停、批准、恢复和验证闭环。"""
    runtime = AgentRuntime()
    investigation_id = f"inv_demo_{uuid4().hex[:8]}"
    try:
        paused = runtime.start(
            StartInvestigation(
                investigation_id=investigation_id,
                environment="demo",
                service="payment-service",
                symptom="canary p95 延迟违反 SLO，怀疑 slow SQL 发布回归",
            )
        )
        print("=== 图已持久化并暂停 ===")
        print(paused.model_dump_json(indent=2))
        completed = runtime.resume(
            investigation_id,
            ApprovalDecision(
                approved=True,
                approved_by="demo-operator",
                token="demo-short-lived-token",
                expires_at=utc_now() + timedelta(minutes=5),
            ),
        )
        print("=== 使用同一 thread_id 恢复后的结果 ===")
        print(json.dumps(completed.model_dump(mode="json"), ensure_ascii=False, indent=2))
    finally:
        runtime.close()


if __name__ == "__main__":
    main()

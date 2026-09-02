"""LangGraph checkpoint 生命周期与对外运行接口。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from releaseguard.config import Settings
from releaseguard.domain import (
    ApprovalDecision,
    InvestigationStatus,
    RunView,
    StartInvestigation,
    utc_now,
)
from releaseguard.gateway import FixtureOpsGateway, HttpOpsGateway, OpsGateway
from releaseguard.graph import ReleaseGuardGraph
from releaseguard.model_adapter import build_model
from releaseguard.report import render_report


class AgentRuntime:
    """用 investigation_id 作为 LangGraph thread_id 管理暂停与恢复。"""

    def __init__(
        self,
        settings: Settings | None = None,
        gateway: OpsGateway | None = None,
        model: BaseChatModel | None = None,
    ) -> None:
        self.settings = settings or Settings()
        checkpoint_path = Path(self.settings.checkpoint_path)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
        self._checkpointer = SqliteSaver(self._connection)
        if gateway is None:
            gateway = (
                FixtureOpsGateway()
                if self.settings.gateway_mode == "fixture"
                else HttpOpsGateway(
                    self.settings.gateway_base_url,
                    self.settings.gateway_token,
                    self.settings.gateway_timeout_seconds,
                )
            )
        self.gateway = gateway
        self.model = model or build_model(self.settings.model)
        self.graph = ReleaseGuardGraph(
            gateway=self.gateway,
            model=self.model,
            settings=self.settings,
            checkpointer=self._checkpointer,
        ).compiled

    @staticmethod
    def _config(investigation_id: str) -> dict[str, Any]:
        """生成稳定的 LangGraph checkpoint 游标。"""
        return {
            "configurable": {"thread_id": investigation_id},
            "recursion_limit": 30,
        }

    def start(self, request: StartInvestigation) -> RunView:
        """启动图，通常运行到人工审批 interrupt。"""
        if request.service not in self.settings.allowed_services:
            raise ValueError(f"服务 {request.service} 不在 Agent 白名单中")
        investigation_id = request.investigation_id or f"inv_{uuid4().hex[:16]}"
        config = self._config(investigation_id)
        existing = self.graph.get_state(config)
        if existing.values:
            raise ValueError(f"调查 {investigation_id} 已存在")
        initial = {
            "investigation_id": investigation_id,
            "environment": request.environment,
            "service": request.service,
            "symptom": request.symptom,
            "status": InvestigationStatus.DETECTED.value,
            "started_at": utc_now().isoformat(),
            "baseline_version": None,
            "candidate_version": None,
            "messages": [],
            "evidence": [],
            "finding": None,
            "proposal": None,
            "approval": None,
            "action": None,
            "transitions": [],
            "tool_calls": [],
            "errors": [],
            "model_calls": 0,
            "report_markdown": None,
        }
        self.graph.invoke(initial, config=config)
        return self.get(investigation_id)

    def resume(self, investigation_id: str, decision: ApprovalDecision) -> RunView:
        """用同一 thread_id 和 Command(resume=...) 恢复暂停图。"""
        current = self.get(investigation_id)
        if current.status != InvestigationStatus.AWAITING_APPROVAL:
            raise ValueError(f"调查当前状态 {current.status} 不接受审批恢复")
        self.graph.invoke(
            Command(resume=decision.model_dump(mode="json")),
            config=self._config(investigation_id),
        )
        return self.get(investigation_id)

    def get(self, investigation_id: str) -> RunView:
        """从最新 checkpoint 投影调查状态。"""
        snapshot = self.graph.get_state(self._config(investigation_id))
        if not snapshot.values:
            raise KeyError(investigation_id)
        state = dict(snapshot.values)
        interrupt_payload: dict[str, Any] | None = None
        for task in snapshot.tasks:
            if task.interrupts:
                value = task.interrupts[0].value
                interrupt_payload = value if isinstance(value, dict) else {"value": value}
                break
        report = state.get("report_markdown") or render_report(state)
        return RunView(
            investigation_id=state["investigation_id"],
            status=state["status"],
            environment=state["environment"],
            service=state["service"],
            symptom=state["symptom"],
            baseline_version=state.get("baseline_version"),
            candidate_version=state.get("candidate_version"),
            evidence=state.get("evidence", []),
            finding=state.get("finding"),
            proposal=state.get("proposal"),
            action=state.get("action"),
            transitions=state.get("transitions", []),
            tool_calls=state.get("tool_calls", []),
            errors=state.get("errors", []),
            interrupt=interrupt_payload,
            report_markdown=report,
        )

    def close(self) -> None:
        """关闭 checkpoint 与 Gateway 连接。"""
        close = getattr(self.gateway, "close", None)
        if callable(close):
            close()
        self._connection.close()


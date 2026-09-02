"""ReleaseGuard Agent HTTP API。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import PlainTextResponse

from releaseguard.config import Settings
from releaseguard.domain import ApprovalDecision, RunView, StartInvestigation
from releaseguard.gateway import OpsGateway
from releaseguard.runtime import AgentRuntime


def create_app(
    settings: Settings | None = None,
    gateway: OpsGateway | None = None,
    runtime: AgentRuntime | None = None,
) -> FastAPI:
    """创建可注入依赖的 FastAPI 应用。"""
    owned_runtime = runtime is None
    agent_runtime = runtime or AgentRuntime(settings=settings, gateway=gateway)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if owned_runtime:
            agent_runtime.close()

    app = FastAPI(
        title="ReleaseGuard Agent API",
        version="0.1.0",
        description="基于 LangGraph checkpoint 与 LangChain tool calling 的发布回归 Agent。",
        lifespan=lifespan,
    )
    app.state.runtime = agent_runtime

    @app.get("/healthz")
    def health() -> dict[str, str]:
        """提供进程存活检查。"""
        return {"status": "ok"}

    @app.post(
        "/api/v1/investigations",
        response_model=RunView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def start_investigation(request: StartInvestigation) -> RunView:
        """启动调查并返回当前 checkpoint。"""
        try:
            return agent_runtime.start(request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v1/investigations/{investigation_id}", response_model=RunView)
    def get_investigation(investigation_id: str) -> RunView:
        """读取最新 checkpoint，不触发图执行。"""
        try:
            return agent_runtime.get(investigation_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="调查不存在") from exc

    @app.post(
        "/api/v1/investigations/{investigation_id}/resume",
        response_model=RunView,
    )
    def resume_investigation(
        investigation_id: str, decision: ApprovalDecision
    ) -> RunView:
        """提交人工审批并恢复暂停图。"""
        try:
            return agent_runtime.resume(investigation_id, decision)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="调查不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get(
        "/api/v1/investigations/{investigation_id}/report",
        response_class=PlainTextResponse,
    )
    def get_report(investigation_id: str) -> str:
        """返回区分事实、推断和建议的 Markdown 报告。"""
        try:
            return agent_runtime.get(investigation_id).report_markdown or ""
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="调查不存在") from exc

    return app


app = create_app()


def run() -> None:
    """启动本地 Agent API。"""
    import uvicorn

    uvicorn.run("releaseguard.api:app", host="0.0.0.0", port=8080, reload=False)


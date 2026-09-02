"""Agent HTTP API 冒烟测试。"""

from datetime import timedelta

from fastapi.testclient import TestClient

from releaseguard.api import create_app
from releaseguard.config import Settings
from releaseguard.domain import utc_now
from releaseguard.runtime import AgentRuntime


def test_api_exposes_pause_resume_and_report(tmp_path):
    """API 能启动调查、恢复 checkpoint 并读取 Markdown 报告。"""
    settings = Settings(
        checkpoint_path=tmp_path / "api.sqlite",
        gateway_mode="fixture",
        model="fixture",
        allowed_services=("payment-service",),
    )
    runtime = AgentRuntime(settings=settings)
    app = create_app(runtime=runtime)

    with TestClient(app) as client:
        started = client.post(
            "/api/v1/investigations",
            json={
                "investigation_id": "inv_api_test",
                "environment": "demo",
                "service": "payment-service",
                "symptom": "p95 延迟违反 SLO",
            },
        )
        assert started.status_code == 202
        assert started.json()["status"] == "AWAITING_APPROVAL"

        resumed = client.post(
            "/api/v1/investigations/inv_api_test/resume",
            json={
                "approved": True,
                "approved_by": "api-reviewer",
                "token": "api-valid-token",
                "expires_at": (utc_now() + timedelta(minutes=5)).isoformat(),
            },
        )
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "RESOLVED"

        report = client.get("/api/v1/investigations/inv_api_test/report")
        assert report.status_code == 200
        assert "## 事实" in report.text
        assert "## 推断" in report.text
        assert "## 建议" in report.text

    runtime.close()


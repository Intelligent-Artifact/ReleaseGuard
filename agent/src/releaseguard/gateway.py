"""Ops Gateway 的契约客户端与本地测试夹具。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from threading import Lock
from typing import Any, Protocol
from uuid import uuid4

import httpx


class GatewayError(RuntimeError):
    """携带稳定错误码的 Gateway 异常。"""

    def __init__(self, code: str, message: str, request_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id


class OpsGateway(Protocol):
    """Agent 所依赖的最小 Gateway 能力。"""

    def get_deployment(self, environment: str, service: str) -> dict[str, Any]: ...

    def compare_metrics(
        self,
        environment: str,
        service: str,
        baseline: str,
        candidate: str,
        window: str,
    ) -> dict[str, Any]: ...

    def submit_rollback(
        self,
        proposal: dict[str, Any],
        approval: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]: ...

    def get_action(self, action_id: str) -> dict[str, Any]: ...


class HttpOpsGateway:
    """严格通过版本化 HTTP 契约访问 Ops Gateway。"""

    def __init__(self, base_url: str, token: str, timeout_seconds: float = 5.0) -> None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client = httpx.Client(base_url=base_url, headers=headers, timeout=timeout_seconds)

    def close(self) -> None:
        """释放 HTTP 连接池。"""
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """调用 Gateway，并仅根据稳定错误码分类失败。"""
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise GatewayError("GATEWAY_TIMEOUT", "Ops Gateway 请求超时") from exc
        except httpx.HTTPError as exc:
            raise GatewayError("GATEWAY_UNAVAILABLE", "Ops Gateway 不可用") from exc
        if response.is_success:
            return response.json()
        try:
            payload = response.json()
        except ValueError as exc:
            raise GatewayError("INVALID_GATEWAY_RESPONSE", "Gateway 返回了非 JSON 错误") from exc
        raise GatewayError(
            str(payload.get("code", "GATEWAY_ERROR")),
            str(payload.get("message", "Gateway 请求失败")),
            payload.get("request_id"),
        )

    def get_deployment(self, environment: str, service: str) -> dict[str, Any]:
        return self._request(
            "GET", f"/api/v1/deployments/{service}", params={"environment": environment}
        )

    def compare_metrics(
        self,
        environment: str,
        service: str,
        baseline: str,
        candidate: str,
        window: str,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/metrics/compare",
            params={
                "environment": environment,
                "service": service,
                "baseline": baseline,
                "candidate": candidate,
                "window": window,
            },
        )

    def submit_rollback(
        self,
        proposal: dict[str, Any],
        approval: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        target = proposal["target"]
        body = {
            "proposal_id": proposal["proposal_id"],
            "investigation_id": proposal["investigation_id"],
            **target,
            "risk": proposal["risk"],
            "approval": approval,
        }
        return self._request(
            "POST",
            "/api/v1/actions/rollback",
            headers={"Idempotency-Key": idempotency_key},
            json=body,
        )

    def get_action(self, action_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/actions/{action_id}")


class FixtureOpsGateway:
    """使用仓库契约夹具模拟可重复的 slow SQL 发布回归。"""

    def __init__(self, fixture_dir: Path | None = None) -> None:
        if fixture_dir is None:
            fixture_dir = Path(__file__).resolve().parents[3] / "contracts" / "examples"
        self._deployment = self._load(fixture_dir / "deployment-response.json")
        self._metrics = self._load(fixture_dir / "metrics-compare-response.json")
        self._actions: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[str, str] = {}
        self._lock = Lock()

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        """读取固定契约夹具。"""
        return json.loads(path.read_text(encoding="utf-8"))

    def get_deployment(self, environment: str, service: str) -> dict[str, Any]:
        if environment != self._deployment["environment"] or service != self._deployment["service"]:
            raise GatewayError("NOT_FOUND", "夹具中不存在目标部署")
        return copy.deepcopy(self._deployment)

    def compare_metrics(
        self,
        environment: str,
        service: str,
        baseline: str,
        candidate: str,
        window: str,
    ) -> dict[str, Any]:
        expected = self._metrics
        if (
            environment != expected["environment"]
            or service != expected["service"]
            or baseline != expected["baseline"]
            or candidate != expected["candidate"]
        ):
            raise GatewayError("INVALID_ARGUMENT", "指标比较参数与夹具不匹配")
        payload = copy.deepcopy(expected)
        payload["window"] = window
        return payload

    def submit_rollback(
        self,
        proposal: dict[str, Any],
        approval: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        with self._lock:
            if idempotency_key in self._idempotency:
                return copy.deepcopy(self._actions[self._idempotency[idempotency_key]])
            action_id = f"act_{uuid4().hex[:12]}"
            target = copy.deepcopy(proposal["target"])
            action = {
                "request_id": f"req_{uuid4().hex[:12]}",
                "action_id": action_id,
                "proposal_id": proposal["proposal_id"],
                "status": "SUCCEEDED",
                "target": target,
                "steps": [
                    {"name": "policy_check", "status": "SUCCEEDED"},
                    {"name": "rollback", "status": "SUCCEEDED"},
                    {"name": "verify", "status": "SUCCEEDED"},
                ],
                "audit_ref": f"audit:{action_id}",
                "updated_at": approval["approved_at"],
            }
            self._actions[action_id] = action
            self._idempotency[idempotency_key] = action_id
            current = self._deployment["current"]
            self._deployment["current"] = self._deployment["previous"]
            self._deployment["previous"] = current
            self._deployment["rollout"] = {"status": "STABLE", "candidate_weight": 0}
            return copy.deepcopy(action)

    def get_action(self, action_id: str) -> dict[str, Any]:
        try:
            return copy.deepcopy(self._actions[action_id])
        except KeyError as exc:
            raise GatewayError("NOT_FOUND", "夹具中不存在目标动作") from exc

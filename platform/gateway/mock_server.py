"""CP0 Platform Mock Gateway。

本模块按 ``contracts/openapi.yaml`` v0.1 提供最小 HTTP mock：
deployments、metrics compare、rollback、action status 四类接口。
所有业务数据来自 ``contracts/examples/*.json``，运行期不依赖真实基础设施。
"""

from __future__ import annotations

import copy
import json
import logging
import re
import secrets
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse


LOGGER = logging.getLogger("releaseguard.mock-gateway")

ALLOWED_ENVIRONMENTS = {"demo", "staging"}
ALLOWED_SERVICES = {"payment-service"}
DEFAULT_ROLLBACK = {
    "environment": "demo",
    "service": "payment-service",
    "from_version": "v2",
    "to_version": "v1",
}
DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "contracts" / "examples"


def _utc_now() -> str:
    """生成 RFC3339 UTC 时间，统一使用 Z 后缀便于比较。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _parse_datetime(value: str) -> datetime:
    """解析带时区的 RFC3339 时间；不接受无时区时间。"""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("datetime must include timezone")
    return parsed


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class MockGateway:
    """无状态接口处理逻辑 + 内存中的动作状态，便于单元测试直接调用。"""

    def __init__(
        self,
        fixtures_dir: Optional[Path] = None,
        clock=None,
    ) -> None:
        self.fixtures_dir = Path(fixtures_dir or DEFAULT_FIXTURES_DIR)
        self.deployment_fixture = _load_json(
            self.fixtures_dir / "deployment-response.json"
        )
        self.metrics_fixture = _load_json(
            self.fixtures_dir / "metrics-compare-response.json"
        )
        # 使用可注入 clock，方便测试过期审批而不必真实等待。
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._actions: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[str, str] = {}
        self._audit: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # 公共路由入口
    # ------------------------------------------------------------------
    def route(
        self,
        *,
        method: str,
        path: str,
        query: Optional[dict[str, list[str]]] = None,
        headers: Optional[dict[str, str]] = None,
        body: Optional[bytes] = None,
    ) -> tuple[int, dict[str, Any]]:
        """返回 (HTTP 状态码, JSON 响应体)，用于 HTTP handler 与单元测试。"""
        parsed = urlparse(path)
        params = query or parse_qs(parsed.query)
        req_headers = {k.lower(): v for k, v in (headers or {}).items()}
        request_id = f"req_{secrets.token_hex(8)}"

        if method == "GET" and parsed.path == "/healthz":
            return 200, {"status": "OK", "service": "ops-gateway-mock", "time": _utc_now()}

        if method == "GET" and parsed.path == "/version":
            return 200, {
                "service": "ops-gateway-mock",
                "version": "0.1.0-cp0-smoke",
                "source": "contracts/examples",
            }

        deployment_match = re.fullmatch(
            r"/api/v1/deployments/([a-z][a-z0-9-]{1,62})", parsed.path
        )
        if deployment_match:
            if method != "GET":
                return 405, self._error(request_id, "METHOD_NOT_ALLOWED", "仅支持 GET")
            return self._get_deployment(request_id, deployment_match.group(1), params)

        if parsed.path == "/api/v1/metrics/compare":
            if method != "GET":
                return 405, self._error(request_id, "METHOD_NOT_ALLOWED", "仅支持 GET")
            return self._compare_metrics(request_id, params)

        if parsed.path == "/api/v1/actions/rollback":
            if method != "POST":
                return 405, self._error(request_id, "METHOD_NOT_ALLOWED", "仅支持 POST")
            return self._submit_rollback(
                request_id, req_headers, body
            )

        action_match = re.fullmatch(
            r"/api/v1/actions/([A-Za-z0-9_-]+)", parsed.path
        )
        if action_match:
            if method != "GET":
                return 405, self._error(request_id, "METHOD_NOT_ALLOWED", "仅支持 GET")
            return self._get_action(request_id, action_match.group(1))

        return 404, self._error(request_id, "NOT_FOUND", "请求的资源不存在")

    # ------------------------------------------------------------------
    # 只读接口
    # ------------------------------------------------------------------
    def _get_deployment(
        self, request_id: str, service: str, params: dict[str, list[str]]
    ) -> tuple[int, dict[str, Any]]:
        environment = (params.get("environment") or [""])[0]
        if environment not in ALLOWED_ENVIRONMENTS:
            return 422, self._error(
                request_id, "INVALID_ARGUMENT", "environment 必须是 demo 或 staging"
            )
        if service not in ALLOWED_SERVICES or environment != "demo":
            return 404, self._error(request_id, "NOT_FOUND", "未找到该服务部署")
        payload = self._normalize_fixture(self.deployment_fixture, request_id)
        return 200, payload

    def _compare_metrics(
        self, request_id: str, params: dict[str, list[str]]
    ) -> tuple[int, dict[str, Any]]:
        required = ("service", "environment", "baseline", "candidate")
        values = {key: (params.get(key) or [""])[0] for key in required}
        if any(not value for value in values.values()):
            return 422, self._error(
                request_id, "INVALID_ARGUMENT", "缺少必填查询参数"
            )
        window = (params.get("window") or ["5m"])[0]
        if window not in {"1m", "5m", "10m", "15m"}:
            return 422, self._error(
                request_id, "INVALID_ARGUMENT", "window 取值不合法"
            )
        expected = {
            "service": "payment-service",
            "environment": "demo",
            "baseline": "v1",
            "candidate": "v2",
        }
        if any(values[key] != expected[key] for key in required):
            return 422, self._error(
                request_id,
                "INVALID_ARGUMENT",
                "当前 fixture 仅提供 payment-service v1/v2 对比",
            )
        payload = self._normalize_fixture(self.metrics_fixture, request_id)
        payload["window"] = window
        return 200, payload

    # ------------------------------------------------------------------
    # 动作接口
    # ------------------------------------------------------------------
    def _submit_rollback(
        self,
        request_id: str,
        headers: dict[str, str],
        body: Optional[bytes],
    ) -> tuple[int, dict[str, Any]]:
        idempotency_key = (headers.get("idempotency-key") or "").strip()
        if not 16 <= len(idempotency_key) <= 128:
            return 422, self._error(
                request_id,
                "INVALID_ARGUMENT",
                "缺少 Idempotency-Key 或长度不在 16-128",
            )

        try:
            request = json.loads(body or b"{}")
        except json.JSONDecodeError:
            return 422, self._error(request_id, "INVALID_ARGUMENT", "请求体不是 JSON")
        if not isinstance(request, dict):
            return 422, self._error(request_id, "INVALID_ARGUMENT", "请求体必须是对象")

        validation = self._validate_rollback_request(request_id, request)
        if validation is not None:
            return validation

        with self._lock:
            # 同一幂等键必须复用同一 action；换 proposal 则视为冲突。
            existing_action_id = self._idempotency.get(idempotency_key)
            if existing_action_id is not None:
                existing = self._actions[existing_action_id]
                if existing["proposal_id"] == request["proposal_id"]:
                    return 202, existing
                return 409, self._error(
                    request_id,
                    "ACTION_ALREADY_RUNNING",
                    "幂等键已被其他 proposal 使用",
                )

            # 同一 proposal 正在执行时不重复创建动作。
            for action in self._actions.values():
                if (
                    action["proposal_id"] == request["proposal_id"]
                    and action["status"] in {"ACCEPTED", "RUNNING", "VERIFYING"}
                ):
                    return 409, self._error(
                        request_id,
                        "ACTION_ALREADY_RUNNING",
                        "同一 proposal 已有动作正在运行",
                    )

            action_id = f"act_{secrets.token_hex(6)}"
            target = {
                "environment": request["environment"],
                "service": request["service"],
                "from_version": request["from_version"],
                "to_version": request["to_version"],
            }
            action = {
                "request_id": request_id,
                "action_id": action_id,
                "proposal_id": request["proposal_id"],
                "status": "SUCCEEDED",
                "target": target,
                "steps": [
                    {"name": "validate_approval", "status": "SUCCEEDED"},
                    {"name": "rollback", "status": "SUCCEEDED"},
                    {"name": "verify_recovery", "status": "SUCCEEDED"},
                ],
                "audit_ref": f"audit:{action_id}",
                "updated_at": _utc_now(),
            }
            self._actions[action_id] = action
            self._idempotency[idempotency_key] = action_id
            self._audit.append(
                {
                    "event": "rollback_submitted",
                    "action_id": action_id,
                    "proposal_id": request["proposal_id"],
                    "request_id": request_id,
                    "idempotency_key": idempotency_key,
                    "target": target,
                    "created_at": _utc_now(),
                }
            )
            return 202, action

    def _get_action(
        self, request_id: str, action_id: str
    ) -> tuple[int, dict[str, Any]]:
        with self._lock:
            action = self._actions.get(action_id)
        if action is None:
            return 404, self._error(request_id, "NOT_FOUND", "动作不存在")
        return 200, action

    def _validate_rollback_request(
        self, request_id: str, request: dict[str, Any]
    ) -> Optional[tuple[int, dict[str, Any]]]:
        required = (
            "proposal_id",
            "investigation_id",
            "environment",
            "service",
            "from_version",
            "to_version",
            "risk",
            "approval",
        )
        missing = [key for key in required if not request.get(key)]
        if missing:
            return 422, self._error(
                request_id, "INVALID_ARGUMENT", f"缺少字段: {', '.join(missing)}"
            )
        if request["environment"] not in ALLOWED_ENVIRONMENTS:
            return 422, self._error(
                request_id, "INVALID_ARGUMENT", "environment 取值不合法"
            )
        if request["service"] not in ALLOWED_SERVICES:
            return 403, self._error(
                request_id, "TARGET_NOT_ALLOWLISTED", "service 不在 allowlist"
            )
        if request["risk"] != "MEDIUM":
            return 422, self._error(
                request_id, "INVALID_ARGUMENT", "risk 当前只允许 MEDIUM"
            )
        target = {
            "environment": request["environment"],
            "service": request["service"],
            "from_version": request["from_version"],
            "to_version": request["to_version"],
        }
        if target != DEFAULT_ROLLBACK:
            return 403, self._error(
                request_id, "TARGET_NOT_ALLOWLISTED", "当前 mock 只支持 v2 回滚到 v1"
            )

        approval = request["approval"]
        if not isinstance(approval, dict):
            return 422, self._error(
                request_id, "INVALID_ARGUMENT", "approval 必须是对象"
            )
        for key in ("token", "approved_by", "approved_at", "expires_at"):
            if not approval.get(key):
                return 422, self._error(
                    request_id, "INVALID_ARGUMENT", f"approval.{key} 不能为空"
                )
        try:
            expires_at = _parse_datetime(approval["expires_at"])
        except ValueError:
            return 422, self._error(
                request_id, "INVALID_ARGUMENT", "approval.expires_at 必须带时区"
            )
        if self._clock() >= expires_at:
            return 403, self._error(
                request_id, "APPROVAL_EXPIRED", "审批材料已过期"
            )
        return None

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    def _normalize_fixture(
        self, fixture: dict[str, Any], request_id: str
    ) -> dict[str, Any]:
        """保留 fixture 的业务数据，覆盖 request_id/generated_at。"""
        payload = copy.deepcopy(fixture)
        payload["request_id"] = request_id
        payload["generated_at"] = _utc_now()
        return payload

    def _error(self, request_id: str, code: str, message: str) -> dict[str, str]:
        return {
            "request_id": request_id,
            "code": code,
            "message": message,
        }


class _GatewayHandler(BaseHTTPRequestHandler):
    """把标准库 HTTP 请求转给 MockGateway。"""

    server_version = "ReleaseGuardMockGateway/0.1"

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET", None)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self._dispatch("POST", self.rfile.read(length) if length else None)

    def _dispatch(self, method: str, body: Optional[bytes]) -> None:
        gateway: MockGateway = self.server.gateway
        try:
            status, payload = gateway.route(
                method=method,
                path=self.path,
                headers=dict(self.headers.items()),
                body=body,
            )
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("service.version", "ops-gateway-mock:cp0")
            self.end_headers()
            self.wfile.write(raw)
        except (ConnectionError, BrokenPipeError):
            # 客户端提前断开时不再写响应。
            return
        except Exception as exc:  # pragma: no cover - 防御性兜底
            LOGGER.exception("mock gateway 处理异常")
            raw = json.dumps(
                {"request_id": "", "code": "INTERNAL_ERROR", "message": str(exc)},
                ensure_ascii=False,
            ).encode("utf-8")
            try:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except OSError:
                return

    def log_message(self, format: str, *args: Any) -> None:
        """关闭标准库默认访问日志，保持冒烟输出干净。"""


class MockGatewayServer(ThreadingHTTPServer):
    """持有 MockGateway 实例的 HTTP 服务器。"""

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        gateway: MockGateway,
    ) -> None:
        super().__init__(server_address, _GatewayHandler)
        self.gateway = gateway


def start_mock_server(
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    gateway: Optional[MockGateway] = None,
) -> MockGatewayServer:
    """在独立线程启动 mock 服务器并返回，调用方负责 shutdown。"""
    server = MockGatewayServer((host, port), gateway or MockGateway())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server

"""Platform Mock Gateway 的 HTTP 契约单元测试。"""

from __future__ import annotations

import json
import sys
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


_GATEWAY_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _GATEWAY_DIR.parents[1]
sys.path.insert(0, str(_GATEWAY_DIR))

from mock_server import MockGateway, start_mock_server  # noqa: E402


def _utc_iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _request(
    base_url: str,
    method: str,
    path: str,
    body: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
) -> tuple[int, Any]:
    data = None
    request_headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    for key, value in (headers or {}).items():
        request_headers[key] = value
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers=request_headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read().decode("utf-8"))
        except (ValueError, OSError):
            return error.code, {}


class MockGatewayHttpTests(unittest.TestCase):
    """通过真实 HTTP 进程验证 CP0 契约冒烟路径。"""

    @classmethod
    def setUpClass(cls) -> None:
        fixtures_dir = _REPO_ROOT / "contracts" / "examples"
        cls.server = start_mock_server(
            gateway=MockGateway(fixtures_dir)
        )
        host, port = cls.server.server_address[:2]
        cls.base_url = f"http://{host}:{port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def _rollback_body(self, *, expires_minutes: int = 10) -> dict[str, Any]:
        fixture = json.loads(
            (_REPO_ROOT / "contracts" / "examples" / "rollback-request.json").read_text(
                encoding="utf-8"
            )
        )
        now = datetime.now(timezone.utc)
        fixture["approval"]["approved_at"] = _utc_iso(now - timedelta(minutes=1))
        fixture["approval"]["expires_at"] = _utc_iso(
            now + timedelta(minutes=expires_minutes)
        )
        return fixture

    def test_healthz(self) -> None:
        status, payload = _request(self.base_url, "GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "OK")

    def test_deployment_fixture_response(self) -> None:
        status, payload = _request(
            self.base_url,
            "GET",
            "/api/v1/deployments/payment-service?environment=demo",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["service"], "payment-service")
        self.assertEqual(payload["current"]["version"], "v2")
        self.assertIn("source_refs", payload)
        self.assertIn("generated_at", payload)

    def test_deployment_unknown_service(self) -> None:
        status, payload = _request(
            self.base_url,
            "GET",
            "/api/v1/deployments/order-service?environment=demo",
        )
        self.assertEqual(status, 404)
        self.assertEqual(payload["code"], "NOT_FOUND")

    def test_metrics_compare_fixture_response(self) -> None:
        status, payload = _request(
            self.base_url,
            "GET",
            "/api/v1/metrics/compare?service=payment-service"
            "&environment=demo&baseline=v1&candidate=v2&window=5m",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["service"], "payment-service")
        self.assertEqual(payload["baseline"], "v1")
        self.assertEqual(payload["candidate"], "v2")
        self.assertGreaterEqual(len(payload["metrics"]), 1)

    def test_metrics_compare_missing_argument(self) -> None:
        status, payload = _request(
            self.base_url,
            "GET",
            "/api/v1/metrics/compare?service=payment-service",
        )
        self.assertEqual(status, 422)
        self.assertEqual(payload["code"], "INVALID_ARGUMENT")

    def test_rollback_success_and_action_status(self) -> None:
        status, action = _request(
            self.base_url,
            "POST",
            "/api/v1/actions/rollback",
            body=self._rollback_body(),
            headers={"Idempotency-Key": "test-" + "a" * 20},
        )
        self.assertEqual(status, 202)
        self.assertEqual(action["status"], "SUCCEEDED")
        action_id = action["action_id"]

        status, state = _request(
            self.base_url, "GET", f"/api/v1/actions/{action_id}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(state["action_id"], action_id)
        self.assertEqual(state["status"], "SUCCEEDED")

    def test_rollback_same_idempotency_key_reuses_action(self) -> None:
        body = self._rollback_body()
        key = "test-" + "b" * 20
        _, first = _request(
            self.base_url,
            "POST",
            "/api/v1/actions/rollback",
            body=body,
            headers={"Idempotency-Key": key},
        )
        status, second = _request(
            self.base_url,
            "POST",
            "/api/v1/actions/rollback",
            body=body,
            headers={"Idempotency-Key": key},
        )
        self.assertEqual(status, 202)
        self.assertEqual(second["action_id"], first["action_id"])

    def test_expired_approval_is_rejected(self) -> None:
        status, payload = _request(
            self.base_url,
            "POST",
            "/api/v1/actions/rollback",
            body=self._rollback_body(expires_minutes=-1),
            headers={"Idempotency-Key": "test-" + "c" * 20},
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["code"], "APPROVAL_EXPIRED")

    def test_target_not_allowlisted_is_rejected(self) -> None:
        body = self._rollback_body()
        body["service"] = "order-service"
        status, payload = _request(
            self.base_url,
            "POST",
            "/api/v1/actions/rollback",
            body=body,
            headers={"Idempotency-Key": "test-" + "d" * 20},
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["code"], "TARGET_NOT_ALLOWLISTED")


if __name__ == "__main__":
    unittest.main()

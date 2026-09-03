"""promo-service 端点与可观测性的单元测试。"""

from __future__ import annotations

import re
import sys
import logging
import unittest
from pathlib import Path


# 允许测试直接从源码目录导入共享库与服务包，无需先 pip install。
_APPS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_APPS_ROOT / "common"))
sys.path.insert(0, str(_APPS_ROOT / "promo-service"))

from promo_service.app import app  # noqa: E402

# 单元测试关注断言结果，关闭访问日志，避免测试输出被大量 JSON 日志淹没。
logging.disable(logging.CRITICAL)


class PromoServiceEndpointTests(unittest.TestCase):
    """覆盖基础设施端点、结构化错误与优惠计算行为。"""

    _TRACEPARENT_RE = re.compile(
        r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$"
    )

    def setUp(self) -> None:
        self.client = app.test_client()

    def test_healthz(self) -> None:
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "OK")
        self.assertEqual(body["service"], "promo-service")
        self.assertIn("version", body)

    def test_readyz(self) -> None:
        response = self.client.get("/readyz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "READY")

    def test_metrics(self) -> None:
        # 先产生一个请求样本，再验证指标定义出现在文本输出中。
        self.client.get("/healthz")
        response = self.client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("http_server_requests_total", text)
        self.assertIn("http_server_request_duration_seconds", text)

    def test_version_and_service_header(self) -> None:
        response = self.client.get("/version")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["service"], "promo-service")
        self.assertEqual(
            response.headers.get("service.version"), "promo-service:v1"
        )

    def test_unknown_route_returns_json_error(self) -> None:
        response = self.client.get("/no-such-route")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"]["code"], "NOT_FOUND")

    def test_traceparent_is_propagated(self) -> None:
        incoming_trace = "e" * 32
        incoming = f"00-{incoming_trace}-{'f' * 16}-01"
        response = self.client.post(
            "/api/v1/promotions/apply",
            json={"promo_code": "SAVE10", "amount_cents": 1000},
            headers={"traceparent": incoming},
        )
        self.assertEqual(response.status_code, 201)
        traceparent = response.headers.get("traceparent")
        self.assertRegex(traceparent or "", self._TRACEPARENT_RE)
        self.assertTrue((traceparent or "").startswith(f"00-{incoming_trace}-"))

    def test_apply_promotion_success(self) -> None:
        response = self.client.post(
            "/api/v1/promotions/apply",
            json={"promo_code": "SAVE10", "amount_cents": 1000},
        )
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["promo_code"], "SAVE10")
        self.assertEqual(body["discount_cents"], 100)
        self.assertEqual(body["final_amount_cents"], 900)

    def test_apply_promotion_rejects_unknown_code(self) -> None:
        response = self.client.post(
            "/api/v1/promotions/apply",
            json={"promo_code": "NOPE99", "amount_cents": 1000},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"]["code"], "PROMO_CODE_NOT_FOUND"
        )

    def test_apply_promotion_rejects_invalid_amount(self) -> None:
        response = self.client.post(
            "/api/v1/promotions/apply",
            json={"promo_code": "SAVE10", "amount_cents": "100"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "INVALID_AMOUNT")


if __name__ == "__main__":
    unittest.main()

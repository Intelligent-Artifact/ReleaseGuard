"""Prometheus 指标定义。

所有标签保持低基数：只使用 service/version/environment/route 等枚举字段，
不把订单号、用户 ID 或完整 URL 放入标签。
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from .config import ServiceInfo


_LATENCY_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


class ServiceMetrics:
    """每个服务独立注册表，避免不同服务进程/测试互相污染指标名。"""

    def __init__(self, service_info: ServiceInfo) -> None:
        self.service_info = service_info
        self.registry = CollectorRegistry()
        self.start_time = Gauge(
            "releaseguard_service_start_time_seconds",
            "服务进程启动时刻（Unix 秒）。",
            registry=self.registry,
        )
        self.start_time.set_to_current_time()

        labels = (
            "environment",
            "service",
            "version",
            "method",
            "route",
            "status_class",
        )
        self.http_requests_total = Counter(
            "http_server_requests_total",
            "HTTP 请求总数，按状态码大类拆分。",
            labels,
            registry=self.registry,
        )
        self.http_request_duration_seconds = Histogram(
            "http_server_request_duration_seconds",
            "HTTP 请求处理耗时直方图。",
            labels,
            buckets=_LATENCY_BUCKETS,
            registry=self.registry,
        )

    def _base_labels(self) -> dict[str, str]:
        return {
            "environment": self.service_info.environment,
            "service": self.service_info.name,
            "version": self.service_info.version,
        }

    def observe_request(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """按低基数标签记录一次请求与耗时。"""
        status_class = f"{status_code // 100}xx"
        labels = {
            **self._base_labels(),
            "method": method,
            "route": route,
            "status_class": status_class,
        }
        self.http_requests_total.labels(**labels).inc()
        self.http_request_duration_seconds.labels(**labels).observe(
            duration_seconds
        )

    def render(self) -> tuple[bytes, str]:
        """返回 Prometheus 抓取格式的指标内容与 Content-Type。"""
        return generate_latest(self.registry), CONTENT_TYPE_LATEST

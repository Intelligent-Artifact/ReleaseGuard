"""Flask 应用工厂与 HTTP 观测中间层。

统一提供 /healthz、/readyz、/metrics、/version 四个基础设施端点，
并通过 before/after_request 注入 request_id、trace 上下文、统一响应头、
结构化访问日志和 Prometheus 请求指标。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from flask import Flask, Response, current_app, g, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from .checks import ReadinessCheck
from .config import ServiceInfo
from .logging_setup import setup_logging
from .metrics import ServiceMetrics
from .trace import (
    new_request_id,
    new_trace_context,
    parse_traceparent,
    sanitize_correlation_id,
)


class ApiError(Exception):
    """业务可预期错误：包含稳定错误码、面向人的中文消息与可选详情。"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[object] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def _request_id() -> str:
    """错误处理器中读取 request_id；before_request 未执行时使用空串。"""
    return getattr(g, "request_id", "")


def service_logger() -> logging.Logger:
    """返回当前 Flask 应用的服务专属 logger，供业务端点记录结构化日志。"""
    return current_app.extensions["releaseguard"]["logger"]


def _error_response(code: str, message: str, status_code: int, details=None):
    payload = {
        "error": {
            "code": code,
            "message": message,
            "request_id": _request_id(),
            "details": details,
        }
    }
    return jsonify(payload), status_code


def create_app(
    service_info: ServiceInfo,
    readiness_checks: Optional[list[ReadinessCheck]] = None,
) -> Flask:
    """创建带统一观测能力的 demo 服务 Flask 应用。"""
    app = Flask(service_info.name)
    # JSON 响应保留中文原文；Flask 2.2+ 使用 app.json.ensure_ascii。
    app.json.ensure_ascii = False
    app.config.update(
        # 限制请求体大小，防止超大 payload 影响 demo 环境稳定性。
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    logger = setup_logging(service_info)
    metrics = ServiceMetrics(service_info)
    checks = list(readiness_checks or [])
    app.extensions["releaseguard"] = {
        "service_info": service_info,
        "logger": logger,
    }

    @app.before_request
    def _prepare_request() -> None:
        # 服务端始终自行生成 request_id，不信任外部传入值。
        g.request_id = new_request_id()
        g.correlation_id = sanitize_correlation_id(
            request.headers.get("X-Correlation-Id")
        ) or g.request_id
        g.trace_context = parse_traceparent(
            request.headers.get("traceparent")
        ) or new_trace_context()
        g.start_time = time.perf_counter()
        # Werkzeug 只对 form 解析强制 MAX_CONTENT_LENGTH，JSON 请求需要显式限制。
        content_length = request.content_length
        if content_length is not None and content_length > app.config[
            "MAX_CONTENT_LENGTH"
        ]:
            raise RequestEntityTooLarge()

    @app.after_request
    def _observe_request(response: Response) -> Response:
        response.headers.setdefault(
            "service.version", service_info.version_header_value()
        )
        response.headers.setdefault("X-Request-Id", g.request_id)
        response.headers.setdefault("X-Correlation-Id", g.correlation_id)
        response.headers.setdefault(
            "traceparent", g.trace_context.to_header()
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")

        # /metrics 自身不被计入请求指标和访问日志，避免抓取行为产生噪声。
        if request.path == "/metrics":
            return response

        route = (
            request.url_rule.rule if request.url_rule is not None else "unmatched"
        )
        duration_seconds = time.perf_counter() - g.start_time
        metrics.observe_request(
            method=request.method,
            route=route,
            status_code=response.status_code,
            duration_seconds=duration_seconds,
        )
        logger.info(
            "HTTP 请求处理完成",
            extra={
                "event": "http_request",
                "request_id": g.request_id,
                "correlation_id": g.correlation_id,
                "trace_id": g.trace_context.trace_id,
                "method": request.method,
                "route": route,
                "status_code": response.status_code,
                "duration_ms": round(duration_seconds * 1000, 2),
            },
        )
        return response

    @app.errorhandler(ApiError)
    def _handle_api_error(error: ApiError):
        logger.warning(
            "业务请求校验失败",
            extra={
                "event": "api_error",
                "request_id": _request_id(),
                "error_code": error.code,
            },
        )
        return _error_response(
            error.code, error.message, error.status_code, error.details
        )

    @app.errorhandler(HTTPException)
    def _handle_http_error(error: HTTPException):
        return _error_response(
            error.name.upper().replace(" ", "_"),
            "请求无法被处理",
            error.code or 500,
        )

    @app.errorhandler(Exception)
    def _handle_unexpected(error: Exception):
        # 堆栈只写入日志，不向调用方暴露内部实现。
        logger.exception(
            "未处理的服务异常",
            extra={
                "event": "unhandled_exception",
                "request_id": _request_id(),
            },
        )
        return _error_response(
            "INTERNAL_ERROR", "服务内部错误", 500
        )

    @app.get("/healthz")
    def _healthz():
        # 存活探针只判断进程本身，不检查下游依赖。
        return jsonify(
            status="OK",
            service=service_info.name,
            version=service_info.version,
            environment=service_info.environment,
            time=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    @app.get("/readyz")
    def _readyz():
        # 就绪探针执行所有依赖检查；失败时返回 503 停止接收流量。
        results = []
        passed = True
        for check in checks:
            try:
                ok, message = check.check()
            except Exception:
                ok, message = False, "检查执行异常"
            results.append(
                {
                    "name": check.name,
                    "status": "PASS" if ok else "FAIL",
                    "message": message,
                }
            )
            passed = passed and ok
        status = "READY" if passed else "NOT_READY"
        payload = jsonify(
            status=status,
            service=service_info.name,
            version=service_info.version,
            environment=service_info.environment,
            checks=results,
        )
        return payload, 200 if passed else 503

    @app.get("/metrics")
    def _metrics():
        body, _content_type = metrics.render()
        return Response(body, mimetype=CONTENT_TYPE_LATEST)

    @app.get("/version")
    def _version():
        return jsonify(
            service=service_info.name,
            version=service_info.version,
            environment=service_info.environment,
            git_commit_sha=service_info.git_commit_sha,
            build_time=service_info.build_time,
            image_digest=service_info.image_digest,
            started_at=service_info.started_at,
        )

    return app

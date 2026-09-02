"""结构化 JSON 日志配置。

所有日志统一输出到标准输出，字段固定包含服务、版本、环境与可选上下文，
便于 Promtail/fluentd 等采集组件直接按字段解析。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from .config import ServiceInfo


# 允许出现在日志记录 extra 字段中的键；避免任意对象被无差别序列化。
_EXTRA_KEYS = (
    "event",
    "request_id",
    "trace_id",
    "correlation_id",
    "method",
    "route",
    "status_code",
    "duration_ms",
    "service",
    "version",
    "environment",
    "order_id",
    "payment_id",
    "promo_code",
    "discount_cents",
    "amount_cents",
    "item_count",
)


class JsonFormatter(logging.Formatter):
    """将日志记录格式化为单行 JSON 的 Formatter。"""

    def __init__(self, service_info: ServiceInfo) -> None:
        super().__init__()
        self.service_info = service_info

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_info.name,
            "version": self.service_info.version,
            "environment": self.service_info.environment,
        }
        for key in _EXTRA_KEYS:
            value = getattr(record, key, None)
            if value is not None and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except TypeError:
            # 个别字段无法序列化时，至少保证原始消息仍然可见。
            return json.dumps(
                {
                    "timestamp": payload["timestamp"],
                    "level": payload["level"],
                    "message": str(record.getMessage()),
                    "service": self.service_info.name,
                },
                ensure_ascii=False,
            )


def setup_logging(service_info: ServiceInfo) -> logging.Logger:
    """配置根 logger 并返回统一使用的 logger。

    重复调用时会替换根 logger 的 handler，保证测试与热重载场景下不重复输出。
    """
    # 容器与本地终端统一使用 UTF-8，保证中文日志不因平台编码差异而乱码。
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass

    logger = logging.getLogger()
    logger.setLevel(service_info.log_level)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service_info))
    logger.addHandler(handler)

    # Flask 内置开发服务器自带普通文本访问日志，统一关闭，
    # 访问日志由应用层 after_request 输出结构化 JSON。
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    return logger

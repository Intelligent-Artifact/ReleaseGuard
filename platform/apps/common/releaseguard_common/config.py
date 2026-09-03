"""服务元数据配置。

约定：所有可追溯字段统一通过 ``RELEASEGUARD_`` 前缀环境变量注入，
本地运行、Docker Compose 与后续 CI 使用同一套变量，避免运行环境之间不一致。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone


DEFAULT_VERSION = "v1"
DEFAULT_ENVIRONMENT = "demo"


def _now_iso() -> str:
    """返回当前 UTC 时间，格式为带秒精度的 ISO 8601。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def env_str(name: str, default: str = "") -> str:
    """读取字符串环境变量并去除首尾空白；变量不存在时返回默认值。"""
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class ServiceInfo:
    """服务启动后固定的元数据集合，供版本端点、日志和指标统一引用。"""

    name: str
    version: str = DEFAULT_VERSION
    environment: str = DEFAULT_ENVIRONMENT
    git_commit_sha: str = "unknown"
    build_time: str = "unknown"
    image_digest: str = "unknown"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    started_at: str = field(default_factory=_now_iso)

    @classmethod
    def from_env(cls, service_name: str, default_port: int) -> "ServiceInfo":
        """从环境变量构造服务元数据；本地直接运行时使用默认值。"""
        try:
            port = int(os.getenv("PORT", str(default_port)))
        except ValueError:
            port = default_port
        return cls(
            name=env_str("RELEASEGUARD_SERVICE_NAME", service_name),
            version=env_str("RELEASEGUARD_SERVICE_VERSION", DEFAULT_VERSION),
            environment=env_str(
                "RELEASEGUARD_ENVIRONMENT", DEFAULT_ENVIRONMENT
            ),
            git_commit_sha=env_str("RELEASEGUARD_GIT_COMMIT_SHA", "unknown"),
            build_time=env_str("RELEASEGUARD_BUILD_TIME", "unknown"),
            image_digest=env_str("RELEASEGUARD_IMAGE_DIGEST", "unknown"),
            host=env_str("RELEASEGUARD_BIND_HOST", "0.0.0.0"),
            port=port,
            log_level=env_str("RELEASEGUARD_LOG_LEVEL", "INFO").upper(),
        )

    def version_header_value(self) -> str:
        """返回 HTTP 响应头 service.version 使用的值。"""
        return f"{self.name}:{self.version}"

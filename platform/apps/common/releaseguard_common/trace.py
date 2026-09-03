"""W3C tracecontext 的轻量实现。

在未接入 OpenTelemetry SDK 前，由本模块负责生成、解析和向下游传播
``traceparent`` 头，确保三个 demo 服务从 V1 开始就保留统一 trace_id。
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, replace
from typing import Optional


_TRACEPARENT_RE = re.compile(
    r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$"
)


def _new_hex(digits: int) -> str:
    """生成指定长度的随机十六进制字符串，排除全零这种非法值。"""
    while True:
        value = secrets.token_hex(digits // 2)
        if not value.startswith("0" * digits):
            return value


def new_trace_id() -> str:
    """生成 128 位随机 trace_id。"""
    return _new_hex(32)


def new_span_id() -> str:
    """生成 64 位随机 span_id。"""
    return _new_hex(16)


@dataclass(frozen=True)
class TraceContext:
    """当前请求的 trace 上下文，trace_id 与父 span 保持不变。"""

    trace_id: str
    span_id: str
    parent_id: Optional[str] = None
    flags: str = "01"

    def to_header(self) -> str:
        """生成符合 W3C tracecontext 的 traceparent 请求/响应头。"""
        return f"00-{self.trace_id}-{self.span_id}-{self.flags}"

    def child_context(self) -> "TraceContext":
        """为下游调用生成子 span 上下文，trace_id 不变。"""
        return replace(self, span_id=new_span_id(), parent_id=self.span_id)


def parse_traceparent(header: Optional[str]) -> Optional[TraceContext]:
    """解析上游传入的 traceparent；格式非法时返回 None。

    返回的上下文会为本服务生成新 span_id，同时保留上游 span 作为 parent_id。
    """
    if not header:
        return None
    match = _TRACEPARENT_RE.fullmatch(header.strip())
    if not match:
        return None
    trace_id, parent_span_id, flags = match.groups()
    # W3C tracecontext 明确禁止全零 trace-id 和全零 parent-id。
    if trace_id == "0" * 32 or parent_span_id == "0" * 16:
        return None
    return TraceContext(
        trace_id=trace_id,
        span_id=new_span_id(),
        parent_id=parent_span_id,
        flags=flags,
    )


def new_trace_context() -> TraceContext:
    """为外部入口创建全新的 trace 上下文。"""
    return TraceContext(trace_id=new_trace_id(), span_id=new_span_id())


def new_request_id() -> str:
    """生成 HTTP 请求 ID，用于关联日志、审计与 Gateway 请求。"""
    return f"req_{secrets.token_hex(8)}"


def sanitize_correlation_id(raw: Optional[str]) -> Optional[str]:
    """校验外部传入的 correlation ID，避免不可信文本进入日志字段。"""
    if not raw:
        return None
    value = raw.strip()
    if re.fullmatch(r"[A-Za-z0-9._-]{8,64}", value):
        return value
    return None

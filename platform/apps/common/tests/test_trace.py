"""共享运行库 trace 模块的单元测试。"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


# 允许在不设置 PYTHONPATH 的干净 shell 中直接运行 common 测试。
_APPS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_APPS_ROOT / "common"))

from releaseguard_common.trace import (
    TraceContext,
    new_span_id,
    new_trace_context,
    new_trace_id,
    parse_traceparent,
)


class TraceContextTests(unittest.TestCase):
    """校验 traceparent 的生成、解析与子 span 派生逻辑。"""

    _HEADER_RE = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")

    def test_new_context_header_format(self) -> None:
        context = new_trace_context()
        self.assertRegex(context.to_header(), self._HEADER_RE)
        self.assertEqual(len(new_trace_id()), 32)
        self.assertEqual(len(new_span_id()), 16)

    def test_parse_valid_traceparent_creates_new_span(self) -> None:
        incoming = "00-" + ("a" * 32) + "-" + ("b" * 16) + "-01"
        context = parse_traceparent(incoming)
        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context.trace_id, "a" * 32)
        self.assertEqual(context.parent_id, "b" * 16)
        self.assertNotEqual(context.span_id, "b" * 16)
        self.assertRegex(context.to_header(), self._HEADER_RE)

    def test_parse_invalid_or_missing_traceparent(self) -> None:
        self.assertIsNone(parse_traceparent(None))
        self.assertIsNone(parse_traceparent(""))
        self.assertIsNone(parse_traceparent("01-" + ("a" * 32) + "-01"))
        self.assertIsNone(parse_traceparent("00-zzzz-0000-01"))
        # W3C 禁止全零 trace-id 与 parent-id。
        self.assertIsNone(parse_traceparent("00-" + ("0" * 32) + "-" + ("b" * 16) + "-01"))
        self.assertIsNone(parse_traceparent("00-" + ("a" * 32) + "-" + ("0" * 16) + "-01"))

    def test_child_context_keeps_trace_id(self) -> None:
        context = TraceContext(
            trace_id="c" * 32,
            span_id="d" * 16,
            parent_id=None,
            flags="01",
        )
        child = context.child_context()
        self.assertEqual(child.trace_id, context.trace_id)
        self.assertEqual(child.parent_id, context.span_id)
        self.assertNotEqual(child.span_id, context.span_id)


if __name__ == "__main__":
    unittest.main()

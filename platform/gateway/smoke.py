"""Platform 契约冒烟 CLI。

启动 Mock Gateway，按 ``contracts/openapi.yaml`` 的端点依次验证
deployments、metrics compare、rollback、action status 与幂等/过期审批路径，
并把可复现的 PASS/FAIL 输出打印到 stdout 或保存到文件。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

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
    """发送 HTTP 请求并返回 (状态码, JSON 响应)。"""
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
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read().decode("utf-8"))
        except (ValueError, OSError):
            payload = {}
        return error.code, payload


def run_smoke(
    *,
    fixtures_dir: Path,
    port: int,
    output: Optional[Path],
) -> tuple[int, list[str]]:
    """执行全部冒烟检查，返回 (退出码, 输出行)。"""
    rollback_fixture = json.loads(
        (fixtures_dir / "rollback-request.json").read_text(encoding="utf-8")
    )
    now = datetime.now(timezone.utc)
    rollback_fixture["approval"]["approved_at"] = _utc_iso(now - timedelta(minutes=1))
    rollback_fixture["approval"]["expires_at"] = _utc_iso(
        now + timedelta(minutes=10)
    )

    server = start_mock_server(port=port, gateway=MockGateway(fixtures_dir))
    host, actual_port = server.server_address[:2]
    base_url = f"http://{host}:{actual_port}"
    lines: list[str] = []

    def check(name: str, ok: bool, detail: str) -> None:
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    try:
        status, payload = _request(base_url, "GET", "/healthz")
        check("healthz", status == 200 and payload.get("status") == "OK", f"HTTP {status}")

        status, payload = _request(base_url, "GET", "/version")
        check(
            "version",
            status == 200 and payload.get("service") == "ops-gateway-mock",
            f"HTTP {status}",
        )

        status, deployment = _request(
            base_url,
            "GET",
            "/api/v1/deployments/payment-service?environment=demo",
        )
        deployment_ok = (
            status == 200
            and deployment.get("service") == "payment-service"
            and deployment.get("current", {}).get("version") == "v2"
            and "source_refs" in deployment
        )
        check("deployments", deployment_ok, f"HTTP {status}")

        status, metrics = _request(
            base_url,
            "GET",
            "/api/v1/metrics/compare?service=payment-service"
            "&environment=demo&baseline=v1&candidate=v2&window=5m",
        )
        metrics_ok = (
            status == 200
            and metrics.get("service") == "payment-service"
            and len(metrics.get("metrics", [])) >= 1
        )
        check("metrics_compare", metrics_ok, f"HTTP {status}")

        idempotency_key = "smoke-" + "a" * 20
        status, action = _request(
            base_url,
            "POST",
            "/api/v1/actions/rollback",
            body=rollback_fixture,
            headers={"Idempotency-Key": idempotency_key},
        )
        rollback_ok = (
            status == 202
            and action.get("status") == "SUCCEEDED"
            and action.get("action_id", "").startswith("act_")
            and action.get("audit_ref")
        )
        check("rollback_accept", rollback_ok, f"HTTP {status}")

        action_id = action.get("action_id", "")
        status, action_state = _request(
            base_url, "GET", f"/api/v1/actions/{action_id}"
        )
        check(
            "action_status",
            status == 200
            and action_state.get("action_id") == action_id
            and action_state.get("status") == "SUCCEEDED",
            f"HTTP {status}",
        )

        status, replay = _request(
            base_url,
            "POST",
            "/api/v1/actions/rollback",
            body=rollback_fixture,
            headers={"Idempotency-Key": idempotency_key},
        )
        check(
            "idempotent_replay",
            status == 202 and replay.get("action_id") == action_id,
            f"HTTP {status}",
        )

        expired_request = json.loads(json.dumps(rollback_fixture))
        expired_request["approval"]["expires_at"] = _utc_iso(
            now - timedelta(minutes=1)
        )
        status, error = _request(
            base_url,
            "POST",
            "/api/v1/actions/rollback",
            body=expired_request,
            headers={"Idempotency-Key": "smoke-" + "b" * 20},
        )
        check(
            "approval_expired_rejected",
            status == 403 and error.get("code") == "APPROVAL_EXPIRED",
            f"HTTP {status} {error.get('code', '')}",
        )
    finally:
        server.shutdown()
        server.server_close()

    passed = sum(line.startswith("[PASS]") for line in lines)
    lines.append(f"RESULT: {passed}/{len(lines)} checks passed")
    if passed == len(lines) - 1:
        lines.append("PASS: Platform contract smoke")
        exit_code = 0
    else:
        lines.append("FAIL: Platform contract smoke")
        exit_code = 1

    text = "\n".join(lines)
    print(text)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    return exit_code, lines


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="ReleaseGuard Platform CP0 契约冒烟测试"
    )
    parser.add_argument(
        "--fixtures-dir",
        default=str(REPO_ROOT / "contracts" / "examples"),
        help="契约 fixture 目录（默认为仓库 contracts/examples）",
    )
    parser.add_argument("--port", type=int, default=0, help="监听端口，0 表示随机")
    parser.add_argument(
        "--output",
        default=None,
        help="将冒烟输出保存到文件（默认只打印 stdout）",
    )
    args = parser.parse_args(argv)
    fixtures_dir = Path(args.fixtures_dir).resolve()
    if not (fixtures_dir / "deployment-response.json").exists():
        print(f"未找到契约 fixture: {fixtures_dir}", file=sys.stderr)
        return 2
    exit_code, _ = run_smoke(
        fixtures_dir=fixtures_dir,
        port=args.port,
        output=Path(args.output) if args.output else None,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

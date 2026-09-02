"""payment-service：执行支付授权的最小 demo 服务。"""

from __future__ import annotations

import secrets

from flask import current_app, jsonify, request

from releaseguard_common.checks import dependency_checks_from_env
from releaseguard_common.config import ServiceInfo
from releaseguard_common.web import ApiError, create_app


SERVICE_INFO = ServiceInfo.from_env("payment-service", default_port=8002)
app = create_app(
    SERVICE_INFO,
    readiness_checks=dependency_checks_from_env(),
)

_ALLOWED_PAYMENT_METHODS = {"card", "balance"}


@app.post("/api/v1/payments")
def authorize_payment():
    """对一笔订单执行支付授权，暂不接真实收单渠道。"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("INVALID_JSON", "请求体必须是 JSON 对象", 400)

    order_id = body.get("order_id")
    if not isinstance(order_id, str) or not order_id.strip():
        raise ApiError("INVALID_ORDER_ID", "order_id 不能为空", 400)

    amount_cents = body.get("amount_cents")
    if (
        not isinstance(amount_cents, int)
        or isinstance(amount_cents, bool)
        or amount_cents <= 0
    ):
        raise ApiError(
            "INVALID_AMOUNT", "amount_cents 必须是大于 0 的整数", 400
        )

    payment_method = body.get("payment_method", "card")
    if payment_method not in _ALLOWED_PAYMENT_METHODS:
        raise ApiError(
            "INVALID_PAYMENT_METHOD", f"不支持的支付方式: {payment_method}", 400
        )

    payment_id = f"pay_{secrets.token_hex(6)}"
    payload = {
        "payment_id": payment_id,
        "order_id": order_id.strip(),
        "status": "AUTHORIZED",
        "amount_cents": amount_cents,
        "payment_method": payment_method,
        "currency": "CNY",
    }
    current_app.logger.info(
        "支付授权成功",
        extra={
            "event": "payment_authorized",
            "payment_id": payment_id,
            "order_id": order_id.strip(),
            "amount_cents": amount_cents,
        },
    )
    return jsonify(payload), 201


def main() -> None:
    """本地或容器内启动入口（demo 阶段使用 Flask 内置服务器）。"""
    app.run(
        host=SERVICE_INFO.host,
        port=SERVICE_INFO.port,
        threaded=True,
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()

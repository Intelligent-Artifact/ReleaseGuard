"""order-service：创建订单的最小 demo 服务。"""

from __future__ import annotations

import secrets

from flask import current_app, jsonify, request

from releaseguard_common.checks import dependency_checks_from_env
from releaseguard_common.config import ServiceInfo
from releaseguard_common.web import ApiError, create_app


SERVICE_INFO = ServiceInfo.from_env("order-service", default_port=8001)
app = create_app(
    SERVICE_INFO,
    readiness_checks=dependency_checks_from_env(),
)


@app.post("/api/v1/orders")
def create_order():
    """受理一个购物车订单并返回订单号，暂不依赖 PostgreSQL/Redis。"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("INVALID_JSON", "请求体必须是 JSON 对象", 400)

    items = body.get("items")
    if not isinstance(items, list) or not items:
        raise ApiError("INVALID_ORDER_ITEMS", "订单至少需要一个商品条目", 400)

    total_amount_cents = 0
    normalized_items: list[dict] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ApiError("INVALID_ORDER_ITEM", f"第 {index + 1} 个商品条目格式错误", 400)
        sku = item.get("sku")
        quantity = item.get("quantity")
        unit_price_cents = item.get("unit_price_cents")
        if not isinstance(sku, str) or not sku.strip():
            raise ApiError("INVALID_ORDER_ITEM", f"第 {index + 1} 个商品缺少 sku", 400)
        if (
            not isinstance(quantity, int)
            or isinstance(quantity, bool)
            or quantity <= 0
        ):
            raise ApiError(
                "INVALID_ORDER_ITEM",
                f"第 {index + 1} 个商品 quantity 必须是正整数",
                400,
            )
        if (
            not isinstance(unit_price_cents, int)
            or isinstance(unit_price_cents, bool)
            or unit_price_cents < 0
        ):
            raise ApiError(
                "INVALID_ORDER_ITEM",
                f"第 {index + 1} 个商品 unit_price_cents 必须是非负整数",
                400,
            )
        amount_cents = quantity * unit_price_cents
        total_amount_cents += amount_cents
        normalized_items.append(
            {
                "sku": sku.strip(),
                "quantity": quantity,
                "unit_price_cents": unit_price_cents,
                "amount_cents": amount_cents,
            }
        )

    order_id = f"ord_{secrets.token_hex(6)}"
    promo_code = body.get("promo_code")
    if promo_code is not None and (
        not isinstance(promo_code, str) or not promo_code.strip()
    ):
        raise ApiError("INVALID_PROMO_CODE", "promo_code 必须是字符串", 400)

    payload = {
        "order_id": order_id,
        "status": "CREATED",
        "customer_id": body.get("customer_id"),
        "currency": "CNY",
        "items": normalized_items,
        "amount_cents": total_amount_cents,
        "promo_code": promo_code,
    }
    current_app.logger.info(
        "订单受理成功",
        extra={
            "event": "order_created",
            "order_id": order_id,
            "amount_cents": total_amount_cents,
            "item_count": len(normalized_items),
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

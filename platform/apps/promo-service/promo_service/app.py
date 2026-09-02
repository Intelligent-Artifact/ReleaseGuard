"""promo-service：应用优惠码的最小 demo 服务。"""

from __future__ import annotations

from flask import current_app, jsonify, request

from releaseguard_common.checks import dependency_checks_from_env
from releaseguard_common.config import ServiceInfo
from releaseguard_common.web import ApiError, create_app


SERVICE_INFO = ServiceInfo.from_env("promo-service", default_port=8003)
app = create_app(
    SERVICE_INFO,
    readiness_checks=dependency_checks_from_env(),
)

# 折扣规则：百分比。后续 slow SQL / 错误配置等故障场景会按版本覆盖该表。
PROMO_DISCOUNT_PERCENT = {"SAVE10": 10, "WELCOME5": 5}


@app.post("/api/v1/promotions/apply")
def apply_promotion():
    """按优惠码计算折扣；未知优惠码返回可稳定复现的业务错误。"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("INVALID_JSON", "请求体必须是 JSON 对象", 400)

    promo_code = body.get("promo_code")
    if not isinstance(promo_code, str) or not promo_code.strip():
        raise ApiError("INVALID_PROMO_CODE", "promo_code 不能为空", 400)

    amount_cents = body.get("amount_cents")
    if (
        not isinstance(amount_cents, int)
        or isinstance(amount_cents, bool)
        or amount_cents <= 0
    ):
        raise ApiError(
            "INVALID_AMOUNT", "amount_cents 必须是大于 0 的整数", 400
        )

    code = promo_code.strip().upper()
    percent = PROMO_DISCOUNT_PERCENT.get(code)
    if percent is None:
        raise ApiError("PROMO_CODE_NOT_FOUND", "优惠码不存在或已失效", 400)

    discount_cents = amount_cents * percent // 100
    payload = {
        "promo_code": code,
        "original_amount_cents": amount_cents,
        "discount_cents": discount_cents,
        "final_amount_cents": amount_cents - discount_cents,
    }
    current_app.logger.info(
        "优惠码应用成功",
        extra={
            "event": "promotion_applied",
            "promo_code": code,
            "amount_cents": amount_cents,
            "discount_cents": discount_cents,
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

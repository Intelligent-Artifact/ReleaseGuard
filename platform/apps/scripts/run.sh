#!/usr/bin/env bash
# ReleaseGuard demo 服务本地运行脚本（Linux/macOS）。
set -euo pipefail

apps_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service="${1:-order-service}"
port="${2:-0}"

# 仅允许启动仓库内的三个 demo 服务，避免脚本被当作任意代码执行入口。
case "$service" in
    order-service) package="order_service" ;;
    payment-service) package="payment_service" ;;
    promo-service) package="promo_service" ;;
    *)
        echo "未知服务：$service" >&2
        exit 1
        ;;
esac

export PYTHONPATH="$apps_root/common:$apps_root/$service"
if [ "$port" != "0" ]; then
    export PORT="$port"
fi

cd "$apps_root"
exec python -m "$package.app"

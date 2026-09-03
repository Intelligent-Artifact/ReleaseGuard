# ReleaseGuard demo 服务本地运行脚本（Windows PowerShell）。
param(
    [string]$Service = "order-service",
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$appsRoot = Split-Path -Parent $PSScriptRoot

# 仅允许启动仓库内的三个 demo 服务，避免脚本被当作任意代码执行入口。
$services = @{
    "order-service" = "order_service"
    "payment-service" = "payment_service"
    "promo-service" = "promo_service"
}

if (-not $services.ContainsKey($Service)) {
    throw "未知服务 $Service，可选值：$($services.Keys -join ', ')"
}

$env:PYTHONPATH = "$(Join-Path $appsRoot 'common');$(Join-Path $appsRoot $Service)"
if ($Port -gt 0) {
    $env:PORT = "$Port"
}

Push-Location $appsRoot
try {
    python -m "$($services[$Service]).app"
}
finally {
    Pop-Location
}

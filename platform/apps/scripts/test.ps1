# 依次运行三个 demo 服务与共享运行库的单元测试。
$ErrorActionPreference = "Stop"
$appsRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $appsRoot "common"

Push-Location $appsRoot
try {
    python -m unittest discover -s common/tests -p "test_*.py" -v
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    python -m unittest discover -s order-service/tests -p "test_*.py" -v
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    python -m unittest discover -s payment-service/tests -p "test_*.py" -v
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    python -m unittest discover -s promo-service/tests -p "test_*.py" -v
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Output "全部测试通过"
}
finally {
    Pop-Location
}

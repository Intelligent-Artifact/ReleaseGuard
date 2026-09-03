#!/usr/bin/env bash
# 依次运行三个 demo 服务与共享运行库的单元测试。
set -euo pipefail

apps_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$apps_root/common"

cd "$apps_root"
python -m unittest discover -s common/tests -p "test_*.py" -v
python -m unittest discover -s order-service/tests -p "test_*.py" -v
python -m unittest discover -s payment-service/tests -p "test_*.py" -v
python -m unittest discover -s promo-service/tests -p "test_*.py" -v

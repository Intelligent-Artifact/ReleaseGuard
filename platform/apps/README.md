# ReleaseGuard Demo 应用

本目录包含 ReleaseGuard 的电商 demo 服务链路，用于后续的发布、故障注入、指标对比与恢复验证：

```text
client / k6
    → order-service（订单受理）
        → payment-service（支付授权，slow SQL 等故障场景的候选载体）
            → promo-service（优惠计算）
```

当前处于“阶段 0：最小健康端点与 telemetry”。三个服务尚未通过 HTTP 互相调用，
但已经具备接入 Compose 后形成依赖链所需的全部基础设施端点与统一遥测字段。

## 目录结构

```text
platform/apps/
├── common/                     # 三个服务共享的运行库
│   ├── releaseguard_common/    # 配置、JSON 日志、指标、trace、Flask 工厂
│   └── tests/
├── order-service/              # 订单服务（默认端口 8001）
├── payment-service/            # 支付服务（默认端口 8002）
├── promo-service/              # 优惠服务（默认端口 8003）
└── scripts/                    # 本地启动与测试脚本
```

## 统一端点

每个服务都提供以下端点：

| 端点 | 用途 |
|---|---|
| `GET /healthz` | 存活探针，只检查进程本身 |
| `GET /readyz` | 就绪探针，可检查上游依赖，未配置依赖时直接通过 |
| `GET /metrics` | Prometheus 文本格式指标 |
| `GET /version` | 返回 service、version、environment、commit SHA、digest、启动时间 |

每个响应都包含 `service.version`、`X-Request-Id`、`X-Correlation-Id` 和
`traceparent` 响应头；所有日志均为单行 UTF-8 JSON，字段使用 service/version/
environment/trace_id 等低基数标签。

## 业务端点（骨架）

| 服务 | 端点 | 说明 |
|---|---|---|
| order-service | `POST /api/v1/orders` | 校验商品条目并创建订单 |
| payment-service | `POST /api/v1/payments` | 校验订单金额并返回支付授权 |
| promo-service | `POST /api/v1/promotions/apply` | 按优惠码计算折扣 |

## 本地运行

前置条件：Python 3.10+。首次运行先在三个服务目录分别安装固定版本依赖：

```powershell
cd order-service
pip install -r requirements.txt
```

启动单个服务：

```powershell
.\scripts\run.ps1 -Service order-service
.\scripts\run.ps1 -Service payment-service -Port 18002
```

Linux/macOS：

```bash
./scripts/run.sh order-service
./scripts/run.sh payment-service 18002
```

冒烟验证：

```powershell
curl.exe http://127.0.0.1:8001/healthz
curl.exe http://127.0.0.1:8001/version
curl.exe http://127.0.0.1:8001/metrics
```

## 运行测试

```powershell
.\scripts\test.ps1
```

或分别执行：

```powershell
python -m unittest discover -s common/tests -p "test_*.py" -v
python -m unittest discover -s order-service/tests -p "test_*.py" -v
python -m unittest discover -s payment-service/tests -p "test_*.py" -v
python -m unittest discover -s promo-service/tests -p "test_*.py" -v
```

## Docker 镜像

Docker 构建上下文是 `platform/apps`（因为需要同时复制共享运行库），例如：

```powershell
docker build -f order-service/Dockerfile -t releaseguard/order-service:v1 .
docker build -f payment-service/Dockerfile -t releaseguard/payment-service:v1 .
docker build -f promo-service/Dockerfile -t releaseguard/promo-service:v1 .
```

镜像内以非 root 用户（UID/GID 10001）运行，并带 Docker HEALTHCHECK。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PORT` | 8001/8002/8003 | 监听端口 |
| `RELEASEGUARD_BIND_HOST` | `0.0.0.0` | 监听地址 |
| `RELEASEGUARD_ENVIRONMENT` | `demo` | 部署环境，进入统一标签 |
| `RELEASEGUARD_SERVICE_VERSION` | `v1` | 当前服务版本，用于 baseline/canary 对比 |
| `RELEASEGUARD_GIT_COMMIT_SHA` | `unknown` | CI 构建时注入的 commit SHA |
| `RELEASEGUARD_BUILD_TIME` | `unknown` | CI 构建时注入的构建时间 |
| `RELEASEGUARD_IMAGE_DIGEST` | `unknown` | 发布时注入的镜像 digest |
| `RELEASEGUARD_DEPENDENCY_URLS` | 空 | 逗号分隔的上游基础地址，注入后写入 `/readyz` 检查 |
| `RELEASEGUARD_LOG_LEVEL` | `INFO` | 日志级别 |

## 下一步

- 用 Docker Compose 把三个服务与 PostgreSQL、Redis、Prometheus、Grafana、Loki 组合起来。
- 让 order-service 携带 `traceparent` 调用 payment-service 和 promo-service，形成真实传播链。
- 为 payment-service 增加可按版本启用的 slow SQL 故障开关。

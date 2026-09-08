# Platform Mock Gateway（CP0 契约冒烟）

本目录实现 CP0 退出条件要求的 **Platform 契约冒烟**：按
[`contracts/openapi.yaml`](../../contracts/openapi.yaml) 提供最小 HTTP Mock，
并直接复用 [`contracts/examples/*.json`](../../contracts/examples/) 作为数据源。

它用于验证旧发布契约的 HTTP 边界，不替代真实 Ops Gateway，也不代表 Agent harness
已接入 HTTP。新的 v0.1 要求真实监控事件、只读取证及恢复验证，见
[监控契约迁移计划](../../contracts/MONITORING_CONTRACT_PLAN.md)。

本 Mock 的 rollback 端点仅模拟动作，不连接真实集群。新的 v0.1/v0.2 监控运行身份
没有自动执行权限；审批与真实单动作执行在 v0.3 验收。以下为当前 Mock 的实际行为。

## 已实现端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/healthz` | 网关存活检查 |
| `GET` | `/version` | mock 版本与数据来源 |
| `GET` | `/api/v1/deployments/{service}` | 返回 deployment-response fixture |
| `GET` | `/api/v1/metrics/compare` | 返回 metrics-compare-response fixture |
| `POST` | `/api/v1/actions/rollback` | 校验审批与幂等键后返回 action |
| `GET` | `/api/v1/actions/{action_id}` | 查询 action 状态 |

Mock 校验以下语义：environment 允许 `demo/staging`、service 使用
allowlist、rollback 审批必须带时区且未过期、`Idempotency-Key` 长度 16–128，
同一幂等键重复提交不会重复创建 action。

## 运行契约冒烟

在仓库根目录执行：

```bash
python platform/gateway/smoke.py
```

保存验收证据：

```bash
python platform/gateway/smoke.py --output platform/gateway/smoke-output.txt
```

Windows PowerShell：

```powershell
python platform\gateway\smoke.py
python platform\gateway\smoke.py --output platform\gateway\smoke-output.txt
```

## 运行单元测试

```bash
python -m unittest discover -s platform/gateway/tests -p "test_*.py" -v
```

冒烟与测试只依赖 Python 标准库，不需要安装第三方包。

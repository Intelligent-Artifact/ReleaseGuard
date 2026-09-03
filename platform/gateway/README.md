# Platform Mock Gateway（CP0 契约冒烟）

本目录实现 CP0 退出条件要求的 **Platform 契约冒烟**：按
[`contracts/openapi.yaml`](../../contracts/openapi.yaml) 提供最小 HTTP Mock，
并直接复用 [`contracts/examples/*.json`](../../contracts/examples/) 作为数据源。

它只证明“Agent 可以跨 HTTP 边界消费平台契约”，不替代真实 Ops Gateway；
真实网关与本地适配器属于 v0.1/v0.2 的实现范围。

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

# Platform

主要负责人：[@adminxue](https://github.com/adminxue)

本目录用于存放 ReleaseGuard 的运行与可靠性平台，包括：

- Demo 微服务和有状态依赖；
- Docker Compose 与 Kubernetes 部署；
- Helm、Argo CD 和 Argo Rollouts；
- Prometheus、Grafana、Loki 和 OpenTelemetry；
- 受约束的 Ops Gateway；
- 工作负载生成和故障注入；
- 策略强制执行、RBAC、动作审计和恢复验证。

## 边界

平台只能暴露 `../contracts/openapi.yaml` 中定义的版本化结构化能力，不得执行 Agent 提供的任意命令。

只读身份与写入身份必须分离。所有变更类动作必须经过 allowlist 限制，具备幂等性和审计记录，并在执行后接受独立验证。

## Demo 应用

三个 demo 服务骨架已放在 [apps/](./apps/README.md)：

- order-service（订单受理，端口 8001）；
- payment-service（支付授权，端口 8002）；
- promo-service（优惠计算，端口 8003）。

每个服务统一提供 `/healthz`、`/readyz`、`/metrics`、`/version`，
输出结构化 JSON 日志，并生成/传播 W3C `traceparent` 上下文。

这些服务是路线调整前已经合入的原型资产。当前只把 `payment-service` 纳入 v0.2 的正式支持范围；
`order-service` 与 `promo-service` 可以保留用于后续场景，但不构成 v0.1/v0.2 的交付或维护承诺。

## 当前任务：v0.1 联合 Portfolio MVP

1. 与 Agent 负责人冻结 deployment、metrics、logs、Git、action 和 recovery 的最小契约。
2. 将共享 fixture 包装成可独立启动的 HTTP Mock Gateway，确保 Agent 不能直接读取平台 fixture。
3. 在 Gateway 侧实现审批材料校验、稳定 action ID、idempotency key 和 audit trail。
4. 模拟 slow SQL 场景的 rollback 前后状态，并通过独立 recovery evidence 验证结果。
5. 与 Agent 侧共同覆盖 rollback、`HOLD`、`INCONCLUSIVE` 和恶意日志四条跨进程 E2E 路径。
6. 完成双方功能 PR、跨边界 review、重复评测和联合演示后发布 `portfolio-v0.1.0`。

Docker Compose、真实 Prometheus 和业务服务从 v0.2 开始；Kubernetes、Helm 与 Argo 从 v1.0 开始，不阻塞 v0.1。

完整计划参见 [DevOps / Platform 工程负责人执行手册](../docs/DEVOPS_PLATFORM_PLAYBOOK.md)。

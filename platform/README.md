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

## 初始任务

1. 建立三个包含健康检查、指标和结构化日志的最小 Demo 服务。
2. 建立 Docker Compose 开发平台。
3. 实现部署元数据与指标对比接口。
4. 增加稳定的 k6 checkout 工作负载。
5. 实现带 TTL 和清理流程的 slow SQL 场景。
6. 增加策略门控回滚和恢复验证。

完整计划参见 [DevOps / Platform 工程负责人执行手册](../docs/DEVOPS_PLATFORM_PLAYBOOK.md)。

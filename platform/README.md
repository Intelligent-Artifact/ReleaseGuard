# Platform

主要负责人：[@adminxue](https://github.com/adminxue)

本目录承载 ReleaseGuard 的运行与可靠性平台。新的业务载体计划采用 Google Online Boutique，平台方重点交付上游集成、监控告警、受限 Ops Gateway、故障注入、独立恢复验证和后续安全执行。

## 当前资产

- [apps/](apps/README.md)：原先的 order/payment/promo 自研服务原型，保留运行说明，停止扩展业务功能。
- [gateway/](gateway/README.md)：CP0 发布契约 HTTP Mock，保留兼容性冒烟用途。

Online Boutique 与真实监控尚未在本次计划改动中部署；既有 Mock 不代表新主线完成。

## 当前目标：v0.1 监控调查作品集

1. G0：固定上游版本与镜像，验证最小 Kind 环境、购物流程、Redis 不可用信号、资源和 TTL 清理。
2. G1：接入 Prometheus、Alertmanager、Loki、最小 Grafana 看板及 Gateway 事件入口，支持 Agent 自动创建唯一调查。
3. G2：通过真实 HTTP 查询提供业务指标、依赖日志和 Kubernetes 资源证据，满足无发布 RCA。
4. G3：交付人工恢复运行手册、操作记录、独立业务验证、重复评测及联合录屏。

首版正式诊断范围限定购物车到 Redis 链路，部署必要上游依赖。首版 Agent 只读；v0.2 加强调查可靠性，v0.3 才引入已审批的单个无状态服务恢复动作，v1.0 再深化 GitOps 与发布专项。

## 边界

已实现 API 以 [OpenAPI](../contracts/openapi.yaml) 为准，新监控接口按 [迁移计划](../contracts/MONITORING_CONTRACT_PLAN.md) 在独立版本中冻结。禁止静默修改旧版本比较语义。

Agent 不直接访问集群、遥测后端或注入工具，不得执行自由命令。人工操作记录与真实恢复证据分开；故障注入必须有范围、独立 TTL 与幂等清理。后续写动作才引入独立 Executor，并完整实施审批、幂等与审计。

完整任务与验收见 [平台 playbook](../docs/DEVOPS_PLATFORM_PLAYBOOK.md)。

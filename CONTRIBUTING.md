# ReleaseGuard 贡献指南

## 分支工作流

`main` 必须始终保持可 Review；MVP 建立后还必须保持可运行。不要直接在 `main` 上开发。

从最新的 `main` 创建短期分支：

```powershell
git switch main
git pull --ff-only
git switch -c feat/agent-investigation
```

建议的分支前缀：

- `feat/agent-*`：Agent 功能。
- `feat/ops-*`：平台功能。
- `feat/contract-*`：共享契约变更。
- `fix/*`：缺陷修复。
- `docs/*`：仅文档变更。
- `test/*`：仅测试变更。

## Commit 信息

使用简洁的 Conventional Commits 风格前缀，并写明受影响区域。冒号后的说明使用中文：

```text
feat(agent): 添加证据模型
feat(ops): 暴露部署元数据接口
feat(contract): 定义回滚请求
fix(ops): 保证回滚操作幂等
test(agent): 增加过期审批拒绝用例
docs: 说明 slow SQL 场景
```

## 合并请求（Pull Request）

所有合入 `main` 的变更都应通过 Pull Request。每个 PR 只聚焦一个结果，并包含：

- 问题和预期结果；
- 受影响的路径与契约；
- 测试和验证方式；
- 安全与运维风险；
- 必要的截图或示例输出；
- 平台变更的回滚或清理说明。

合并前应由另一位项目成员完成 Review。

## 跨边界变更

涉及 Agent–Gateway 的变更应遵循：

1. 创建 Issue，说明消费方需要解决的问题。
2. 先更新 `contracts/openapi.yaml` 和对应示例。
3. 对齐字段语义、缺失数据行为和错误处理方式。
4. 双方根据同一组测试夹具分别实现。
5. 运行契约测试和端到端测试。
6. 若兼容性有要求，先合并提供方，或将提供方与消费方一起合并。

不得静默修改或删除必填字段。破坏兼容性的变更必须引入新的 API 版本，或者提供双方认可的迁移方案。

## Review 职责

`@adminxue` Review Agent 变更时重点检查：

- 基础设施访问边界；
- namespace、service 和 action 限制；
- 重试、幂等和影响范围；
- 恢复检查是否符合真实平台 SLO；
- 不可信遥测是否可能影响权限。

`@Manticore0918` Review 平台变更时重点检查：

- 部署版本、commit SHA、时间戳和来源引用；
- 缺失数据和部分数据是否被结构化表达；
- 错误码是否稳定；
- 部署与遥测证据能否相互关联；
- 响应是否有边界并适合 Agent 消费。

## Secret 管理

禁止提交：

- 包含真实值的 `.env` 文件；
- API Key 或访问令牌；
- kubeconfig 文件；
- 私钥或证书；
- 云平台凭据；
- 生产数据或敏感日志。

使用 `.env.example` 记录变量名和安全的占位值。

## 完成定义

一项变更只有同时满足以下条件才算完成：

- 测试覆盖正常路径和相关失败路径；
- API 变更同步更新契约和测试夹具；
- 日志和错误使用结构化格式；
- 安全边界仍然有效；
- 相关文档或运行手册已更新；
- PR 清楚说明其他人如何验证结果。

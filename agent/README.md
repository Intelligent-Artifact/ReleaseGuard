# Agent

主要负责人：[@Manticore0918](https://github.com/Manticore0918)

ReleaseGuard 是一个面向渐进式发布的 AI 辅助可靠性平台。Agent 负责调查、推理、
建议与评测；Ops Gateway（平台侧）负责基础设施访问、权限、执行、幂等与审计。
**Agent 不直接访问 Kubernetes 或执行任意命令**，只能通过 `../contracts/openapi.yaml`
定义的版本化契约读取数据。

> 当前目录处于 **CP0：协作与契约基线** 阶段。它交付一份可复现的
> **Agent 契约冒烟测试**——在没有真实基础设施、没有 LLM、没有 langgraph 的前提下，
> 读取共享契约 fixture，完成一次确定性 mock 调查，并输出区分事实/推断/建议的报告。
> 后续 Checkpoint（CP1+）的 LangGraph 调查引擎将在此领域模型之上扩展。

## 本目录能做什么

在任意干净环境执行一条命令（见下），即可：

1. **校验共享契约 fixture**：加载并校验 `contracts/examples/*.json`
   （deployment / metrics compare / rollback request）符合 OpenAPI v0.1 的结构与语义；
2. **跑一次确定性 mock 调查**：把 fixture 转成结构化 `Evidence`，
   按固定规则判断回归、形成 `Finding`，并裁决处置方向；
3. **生成事故报告**：机器可读 JSON + 人可读 Markdown，严格区分事实 / 推断 / 建议；
4. **输出冒烟验收证据**：stdout 打印 PASS / 判定结果，可作为 CP0 验收证据留档。

## 快速开始

要求：Python 3.11+。

```bash
# 在仓库根目录下执行（fixture 位于 contracts/examples，会被自动发现）
cd agent

# 方式 A：无需安装，直接以 src 作为模块路径运行
PYTHONPATH=src python -m releaseguard.smoke        # bash / macOS / Linux
# PowerShell：$env:PYTHONPATH="src"; python -m releaseguard.smoke

# 方式 B：安装为可执行命令后运行（跨平台一致）
python -m venv .venv
# Windows：.venv\Scripts\activate    /    macOS-Linux：source .venv/bin/activate
pip install -e ".[test]"
releaseguard-smoke
```

保存验收证据（stdout 即“Agent 契约冒烟测试输出”）：

```bash
PYTHONPATH=src python -m releaseguard.smoke > reports/local/agent-smoke-output.txt
```

运行契约冒烟测试（pytest）：

```bash
cd agent
PYTHONPATH=src python -m pytest            # 或 pip install -e ".[test]" 后直接 pytest
```

> 提示：Windows 控制台若出现中文乱码，可在命令前加 `PYTHONIOENCODING=utf-8`。

生成的 JSON / Markdown 报告默认写入 `<仓库根>/reports/local/agent/`（已被
`.gitignore` 忽略，不会污染仓库）。可用 `--output-dir` 修改输出位置，用
`RELEASEGUARD_FIXTURES_DIR` 环境变量覆盖 fixture 目录（便于 CI 接入平台方 mock）。

## 代码结构

```text
agent/
├── pyproject.toml                  # 仅依赖 pydantic；test extra 提供 pytest
├── src/releaseguard/
│   ├── contracts.py                # OpenAPI v0.1 报文模型 + fixture 加载/校验
│   ├── domain.py                   # Investigation/Evidence/Finding/Proposal/Report 领域模型
│   ├── smoke.py                    # 确定性 mock 调查流水线 + CLI（releaseguard-smoke）
│   └── report.py                   # JSON + Markdown 报告渲染
└── tests/
    ├── test_contract_fixtures.py   # 共享 fixture 契约符合性测试
    └── test_smoke_investigation.py # 调查流水线：正常/降级/裁决/报告输出
```

## 冒烟测试判定逻辑

`smoke.decide()` 使用确定性规则（不由 LLM 自评，符合项目“AI 提议，策略裁决”原则）：

| 条件 | 处置 | 是否触发执行动作 |
|---|---|---|
| 缺部署或指标数据 / 不可比 / 未检测到回归 | `INCONCLUSIVE` | 否 |
| 确认 candidate 回归，但缺代码变更（git）证据 | `HOLD` | 否（保守） |
| 部署 + 指标 + 变更证据齐备，置信度达标 | `ROLLBACK_RELEASE` | 构造建议，**需人工审批**，不自动执行 |

- 所有结论只引用真实存在、确实落入本次调查的 `evidence_id`；
- 缺失的日志 / 链路 / 代码变更证据会写入 `finding.missing_evidence`，
  **绝不把“无数据”当作正常，也绝不编造“已定位到具体 SQL”**；
- 主流程对当前共享 fixture 的判定为 `HOLD`；`ROLLBACK_RELEASE` 路径由单元测试
  构造完整证据（deployment+metrics+git）覆盖，并验证其符合写契约 `RollbackRequest` 形状。

## CP0 退出条件对照

- [x] Agent 能根据 fixture 生成一次模拟调查结果（`releaseguard-smoke`）；
- [x] Agent 契约冒烟测试输出可复现（确定性、无随机、无网络）；
- [x] 仓库无 secret / token / kubeconfig；
- [ ] 与平台侧共同 review OpenAPI v0.1，并让平台侧的契约冒烟测试并行通过；
- [ ] 双方各一个合并 PR（本目录通过 PR 合入 `main`）。

详细路线见 [`../docs/PROJECT_DIRECTION_AND_CHECKPOINTS.md`](../docs/PROJECT_DIRECTION_AND_CHECKPOINTS.md)
与 [`../docs/AGENT_ENGINEER_PLAYBOOK.md`](../docs/AGENT_ENGINEER_PLAYBOOK.md)。

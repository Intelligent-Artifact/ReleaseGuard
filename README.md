# ReleaseGuard

ReleaseGuard is an AI-assisted release risk analysis and policy-gated remediation platform. It correlates deployment changes with metrics, logs, traces, and Git metadata, then proposes safe actions and verifies recovery after execution.

## Project goals

- Detect regressions introduced by canary releases.
- Produce evidence-grounded root-cause findings.
- Keep infrastructure mutations behind a constrained Ops Gateway.
- Require deterministic policy checks and human approval for risky actions.
- Replay incidents and measure RCA accuracy, remediation quality, safety, diagnosis latency, and MTTR.

## Ownership

| Area | Owner | Responsibility |
|---|---|---|
| `agent/` | [@Manticore0918](https://github.com/Manticore0918) | Agent engine, evidence, release correlation, policy, HITL, evaluation, reports |
| `platform/` | [@adminxue](https://github.com/adminxue) | Demo services, Docker/Kubernetes, GitOps, observability, Ops Gateway, fault injection, recovery verification |
| `contracts/` | Both | Versioned Agent–Gateway API contracts and examples |
| `scenarios/` | Both | Incident definitions, expected evidence, safe actions, and recovery criteria |
| `tests/e2e/` | Both | End-to-end release, incident, remediation, and recovery tests |
| `docs/` | Both | Architecture, decisions, runbooks, and project documentation |

## Repository layout

```text
.
├── agent/                 # AI/Agent application
├── platform/              # Runtime and reliability platform
├── contracts/             # OpenAPI, schemas, and fixtures
├── scenarios/             # Reproducible incident scenarios
├── tests/e2e/             # Cross-boundary tests
├── docs/                  # Detailed engineering playbooks
└── .github/               # Collaboration templates and ownership
```

## Current phase

**Phase 0 — contract and local platform bootstrap**

Initial shared deliverables:

1. Freeze the first version of the Agent–Gateway API.
2. Bootstrap the Agent service against contract fixtures.
3. Bootstrap the Docker Compose platform and demo services.
4. Implement one complete slow-SQL release-regression scenario.
5. Run the same scenario repeatedly and record success and failure results.

## Documentation

- [Agent / AI Engineer Playbook](docs/AGENT_ENGINEER_PLAYBOOK.md)
- [DevOps / Platform Engineer Playbook](docs/DEVOPS_PLATFORM_PLAYBOOK.md)
- [Contributing and collaboration workflow](CONTRIBUTING.md)
- [API contract guide](contracts/README.md)
- [Incident scenario guide](scenarios/README.md)

## Engineering principle

> AI proposes. Policy decides. Humans approve high-risk actions. Infrastructure verifies.

## Status

The repository currently contains the collaboration skeleton and the initial API contract. Application code and deployable infrastructure will be added through reviewed pull requests.

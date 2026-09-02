# Contributing to ReleaseGuard

## Branch workflow

`main` must remain reviewable and, once the MVP exists, runnable. Do not develop directly on `main`.

Create a short-lived branch from the latest `main`:

```powershell
git switch main
git pull --ff-only
git switch -c feat/agent-investigation
```

Suggested branch prefixes:

- `feat/agent-*` — Agent-owned features
- `feat/ops-*` — platform-owned features
- `feat/contract-*` — shared contract changes
- `fix/*` — bug fixes
- `docs/*` — documentation only
- `test/*` — test-only work

## Commit messages

Use a concise Conventional Commit-style prefix and include the affected area:

```text
feat(agent): add evidence schema
feat(ops): expose deployment metadata
feat(contract): define rollback request
fix(ops): make rollback idempotent
test(agent): reject expired approvals
docs: document slow SQL scenario
```

## Pull requests

Every change to `main` should use a pull request. Keep each PR focused on one outcome and include:

- the problem and intended result;
- the paths and contracts affected;
- how the change was tested;
- security and operational risks;
- screenshots or sample output when useful;
- rollback or cleanup instructions for platform changes.

The other project member should review before merge.

## Cross-boundary changes

For an Agent–Gateway change:

1. Open an issue describing the consumer need.
2. Update `contracts/openapi.yaml` and the relevant example first.
3. Agree on field semantics and error behavior.
4. Implement both sides against the same fixtures.
5. Run contract and end-to-end tests.
6. Merge the provider before or together with the consumer when compatibility requires it.

Do not silently change or remove required fields. Breaking changes require a new API version or an agreed migration.

## Review responsibilities

When `@adminxue` reviews Agent changes, focus on:

- infrastructure access boundaries;
- namespace, service, and action restrictions;
- retries, idempotency, and blast radius;
- whether recovery checks match the real platform SLO;
- whether untrusted telemetry can influence permissions.

When `@Manticore0918` reviews platform changes, focus on:

- deployment version, commit SHA, timestamp, and source references;
- structured handling of missing and partial data;
- stable error codes;
- evidence correlation across deployment and telemetry sources;
- whether responses are bounded and suitable for Agent consumption.

## Secrets

Never commit:

- `.env` files with real values;
- API keys or access tokens;
- kubeconfig files;
- private keys or certificates;
- cloud credentials;
- production data or sensitive logs.

Use `.env.example` for variable names and safe placeholders.

## Definition of done

A change is complete when:

- tests cover the normal and relevant failure paths;
- API changes include contract and fixture updates;
- logs and errors are structured;
- security boundaries remain enforced;
- documentation or runbooks are updated;
- the PR explains how another person can verify the result.

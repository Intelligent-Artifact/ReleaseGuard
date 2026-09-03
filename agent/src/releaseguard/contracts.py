"""Ops Gateway 契约客户端（Developer Preview：仅读取共享 fixture）。

`contracts/openapi.yaml` 是 Agent 与 Ops Gateway 之间的唯一事实来源。本模块
用 Pydantic 模型镜像 OpenAPI v0.1 中 Agent 真正消费/产生的报文结构，用于：

- 读取并校验共享测试夹具 `contracts/examples/*.json`；
- 语义校验：必填字段、枚举、service 命名、时间格式与错误码；
- 在 v0.1 接入独立 HTTP Mock Gateway 时，作为响应结构校验与稳定错误码判断的依据。

本文件只描述“线上契约”，不包含任何 Agent 调查逻辑。Agent 调查逻辑见 domain.py 与 smoke.py。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 通用类型：时间必须携带时区（RFC3339 / ISO8601）。这是双方在 Developer Preview 需要明确的
# “时间格式”语义：禁止把无时区的本地时间当作可比较时间。
# ---------------------------------------------------------------------------


def _require_tz(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("时间戳必须携带时区（RFC3339），例如 2026-09-02T14:36:00Z")
    return value


TzDateTime = Annotated[datetime, AfterValidator(_require_tz)]

# 与 openapi.yaml 一致的 service 命名约束。
SERVICE_PATTERN = r"^[a-z][a-z0-9-]{1,62}$"
# 当前契约允许的环境。
ENVIRONMENT_VALUES = ("demo", "staging")


# ---------------------------------------------------------------------------
# 枚举：镜像 openapi.yaml components 中的枚举，禁止出现契约之外的取值。
# ---------------------------------------------------------------------------


class RolloutStatus(str, Enum):
    """Rollout 状态：openapi.yaml 中 rollout.status 的枚举。"""

    STABLE = "STABLE"
    PROGRESSING = "PROGRESSING"
    PAUSED = "PAUSED"
    DEGRADED = "DEGRADED"
    ABORTED = "ABORTED"


class MetricName(str, Enum):
    """受限指标模板名：Agent 不允许提交任意 PromQL。"""

    REQUEST_RATE = "request_rate"
    ERROR_RATE = "error_rate"
    P95_LATENCY = "p95_latency"
    AVAILABILITY = "availability"


class ErrorCode(str, Enum):
    """稳定错误码：Agent 只依据 code 做逻辑判断，绝不解析面向人的 message。"""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NOT_FOUND = "NOT_FOUND"
    TARGET_NOT_ALLOWLISTED = "TARGET_NOT_ALLOWLISTED"
    POLICY_DENIED = "POLICY_DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    ACTION_ALREADY_RUNNING = "ACTION_ALREADY_RUNNING"
    TELEMETRY_UNAVAILABLE = "TELEMETRY_UNAVAILABLE"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


# OpenAPI 里 RollbackRequest.risk 当前只允许 MEDIUM（Developer Preview 尚未放开其他风险）。
RollbackRisk = Literal["MEDIUM"]


# ---------------------------------------------------------------------------
# 只读接口报文：GET /api/v1/deployments/{service} 与 GET /api/v1/metrics/compare
# ---------------------------------------------------------------------------


class ReleaseRevision(BaseModel):
    """一次发布版本：version、镜像摘要、commit SHA 与上线时间。"""

    model_config = ConfigDict(extra="forbid")

    version: str
    image_digest: str
    commit_sha: str
    deployed_at: TzDateTime


class RolloutState(BaseModel):
    """Rollout 状态：状态机枚举 + candidate 流量权重（0–100）。"""

    model_config = ConfigDict(extra="forbid")

    status: RolloutStatus
    candidate_weight: int = Field(ge=0, le=100)


class DeploymentResponse(BaseModel):
    """GET /api/v1/deployments/{service} 的响应体（镜像 openapi.yaml）。

    `warnings` / `source_refs` 在 openapi.yaml 中是 required（可为空数组但字段必须存在），
    因此这里不设默认值：缺这两个字段的报文必须被契约校验拦截，防止静默漂移。
    """

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    generated_at: TzDateTime
    environment: Literal["demo", "staging"]
    service: str = Field(pattern=SERVICE_PATTERN)
    current: ReleaseRevision
    previous: ReleaseRevision | None = None
    rollout: RolloutState
    warnings: list[str]
    source_refs: list[str]


class MetricComparison(BaseModel):
    """单个受限指标的 baseline / candidate 比较结果。"""

    model_config = ConfigDict(extra="forbid")

    name: MetricName
    unit: str
    baseline_value: float
    candidate_value: float
    sample_count: int = Field(ge=0)
    comparable: bool


class MetricsCompareResponse(BaseModel):
    """GET /api/v1/metrics/compare 的响应体（镜像 openapi.yaml）。"""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    generated_at: TzDateTime
    environment: Literal["demo", "staging"]
    service: str = Field(pattern=SERVICE_PATTERN)
    baseline: str
    candidate: str
    window: str
    metrics: list[MetricComparison] = Field(min_length=1)
    # 与 openapi.yaml 一致：required（可为空数组但字段必须存在），不设默认值。
    warnings: list[str]
    source_refs: list[str]


# ---------------------------------------------------------------------------
# 写接口报文：POST /api/v1/actions/rollback（示例请求体）
# ---------------------------------------------------------------------------


class Approval(BaseModel):
    """短时效审批信息：token 与 proposal/target/有效期绑定。"""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1)
    approved_by: str
    approved_at: TzDateTime
    expires_at: TzDateTime


class RollbackRequest(BaseModel):
    """POST /api/v1/actions/rollback 的请求体（镜像 openapi.yaml）。

    Agent 只有在政策判定为允许、需要审批的动作获得批准后，才会构造并提交
    该报文；Developer Preview 只校验其契约形状，不真正提交给 Gateway。
    """

    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    investigation_id: str
    environment: Literal["demo", "staging"]
    service: str = Field(pattern=SERVICE_PATTERN)
    from_version: str
    to_version: str
    risk: RollbackRisk
    approval: Approval


class ErrorResponse(BaseModel):
    """统一错误响应：request_id + 稳定错误码 code + 人读 message。"""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    code: ErrorCode
    message: str


# ---------------------------------------------------------------------------
# fixture 发现与加载
# ---------------------------------------------------------------------------

# 共享 fixture 文件 → 对应契约模型。文件位置与名称由双方在 contracts/ 共同维护。
_FIXTURE_MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("deployment-response.json", DeploymentResponse),
    ("metrics-compare-response.json", MetricsCompareResponse),
    ("rollback-request.json", RollbackRequest),
)

# 允许通过环境变量覆盖 fixture 目录，便于 CI 使用平台方提供的 mock 文件。
FIXTURES_DIR_ENV = "RELEASEGUARD_FIXTURES_DIR"


@dataclass
class FixtureBundle:
    """一次性加载并解析共享契约 fixture 的结果。

    - deployment / metrics / rollback_request：成功解析后的契约对象；
    - results：逐文件的解析状态（"PASS" / "FAIL" / "MISSING"，供冒烟输出按真实
      解析结果展示，避免“文件存在但内容不合契约”时仍打印 PASS）；
    - errors：逐文件收集的失败信息（缺失文件、JSON 或字段不符合契约）。
    """

    fixtures_dir: Path
    deployment: DeploymentResponse | None = None
    metrics: MetricsCompareResponse | None = None
    rollback_request: RollbackRequest | None = None
    results: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """所有共享 fixture 都符合契约才算加载成功。"""
        return not self.errors


def find_repo_root(start: Path | None = None) -> Path:
    """向上查找仓库根目录（以存在 contracts/openapi.yaml 为标志）。

    这样无论从 agent/ 目录、仓库根目录还是任意子目录运行，都能定位到共享 fixture。
    """
    probe = (start or Path.cwd()).resolve()
    for candidate in (probe, *probe.parents):
        if (candidate / "contracts" / "openapi.yaml").is_file():
            return candidate
    raise FileNotFoundError(
        "找不到仓库根目录（缺少 contracts/openapi.yaml）。"
        "请在 ReleaseGuard 仓库内运行本冒烟测试。"
    )


def resolve_fixtures_dir(explicit: Path | str | None = None) -> Path:
    """返回共享 fixture 目录：优先显式参数，其次环境变量，最后仓库默认位置。"""
    if explicit is not None:
        return Path(explicit).resolve()
    env_dir = os.environ.get(FIXTURES_DIR_ENV)
    if env_dir:
        return Path(env_dir).resolve()
    return find_repo_root() / "contracts" / "examples"


def load_shared_fixtures(explicit: Path | str | None = None) -> FixtureBundle:
    """读取并校验 contracts/examples 下的全部共享 fixture。

    任一文件缺失或不符合 OpenAPI v0.1 结构都会被记录到 errors，
    由冒烟测试判定为失败——这正是“契约基线”验收要拦截的问题。
    """
    fixtures_dir = resolve_fixtures_dir(explicit)
    bundle = FixtureBundle(fixtures_dir=fixtures_dir)

    for filename, model in _FIXTURE_MODELS:
        path = fixtures_dir / filename
        if not path.is_file():
            bundle.errors.append(f"缺少共享 fixture：{path}")
            bundle.results[filename] = "MISSING"
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            parsed = model.model_validate(payload)
        except json.JSONDecodeError as exc:
            bundle.errors.append(f"fixture 不是合法 JSON：{filename}（{exc}）")
            bundle.results[filename] = "FAIL"
            continue
        except Exception as exc:  # pydantic.ValidationError 等
            bundle.errors.append(f"fixture 不符合 OpenAPI v0.1：{filename} -> {exc}")
            bundle.results[filename] = "FAIL"
            continue
        if filename.startswith("deployment"):
            bundle.deployment = parsed  # type: ignore[assignment]
        elif filename.startswith("metrics"):
            bundle.metrics = parsed  # type: ignore[assignment]
        else:
            bundle.rollback_request = parsed  # type: ignore[assignment]
        bundle.results[filename] = "PASS"

    return bundle


def fixture_checklines(bundle: FixtureBundle) -> list[str]:
    """生成逐文件契约校验结果行（供冒烟输出与验收证据使用）。

    状态按真实解析结果输出（PASS/FAIL/MISSING），不是只看文件是否存在——
    避免“文件存在但内容不符合契约”时 stdout 仍先显示 PASS。
    """
    lines: list[str] = []
    for filename, _ in _FIXTURE_MODELS:
        status = bundle.results.get(filename, "MISSING")
        lines.append(f"  [{status}] {filename}")
    return lines

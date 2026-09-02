"""Agent 配置加载。"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量读取运行配置，并提供安全的演示默认值。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RELEASEGUARD_",
        extra="ignore",
    )

    environment: Literal["demo", "staging"] = "demo"
    gateway_mode: Literal["fixture", "http"] = "fixture"
    gateway_base_url: str = "http://localhost:8081"
    gateway_token: str = ""
    gateway_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    model: str = "fixture"
    checkpoint_path: Path = Path("data/agent-checkpoints.sqlite")
    allowed_services: Annotated[tuple[str, ...], NoDecode] = ("payment-service",)
    approval_ttl_seconds: int = Field(default=600, ge=30, le=3600)
    max_model_calls: int = Field(default=4, ge=2, le=8)

    @field_validator("allowed_services", mode="before")
    @classmethod
    def parse_allowed_services(cls, value: object) -> object:
        """允许通过逗号分隔的环境变量配置服务白名单。"""
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

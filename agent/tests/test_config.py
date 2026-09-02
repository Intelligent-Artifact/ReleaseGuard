"""配置加载回归测试。"""

from releaseguard.config import Settings


def test_allowed_services_accepts_comma_separated_env(monkeypatch):
    """服务白名单支持文档约定的逗号分隔格式。"""
    monkeypatch.setenv(
        "RELEASEGUARD_ALLOWED_SERVICES", "payment-service,order-service"
    )

    settings = Settings()

    assert settings.allowed_services == ("payment-service", "order-service")

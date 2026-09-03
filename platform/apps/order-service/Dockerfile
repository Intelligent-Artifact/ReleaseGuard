# order-service 容器镜像：固定基础镜像版本，运行非 root 用户。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 先复制依赖清单安装，利用 Docker 层缓存。
COPY order-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 复制共享运行库与当前服务源码。
COPY common/releaseguard_common ./releaseguard_common
COPY order-service/order_service ./order_service

# 使用数值 UID/GID 避免依赖镜像内置账号，且容器内不以 root 运行。
RUN chown -R 10001:10001 /app
USER 10001:10001

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/healthz', timeout=2)"]

CMD ["python", "-m", "order_service.app"]

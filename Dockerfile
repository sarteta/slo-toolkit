# Multi-stage build: slim runtime, no build tools in final image.
FROM python:3.13-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --prefix=/install --no-deps . \
 && pip install --prefix=/install "PyYAML>=6.0"


FROM python:3.13-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/sarteta/slo-toolkit"
LABEL org.opencontainers.image.description="Generate Prometheus rules + Grafana dashboards from a YAML SLO spec"
LABEL org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 app \
 && useradd  --system --uid 10001 --gid app --create-home app

COPY --from=builder /install /usr/local

USER app
WORKDIR /home/app

ENTRYPOINT ["slo-toolkit"]

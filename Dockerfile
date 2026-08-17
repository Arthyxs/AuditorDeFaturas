# syntax=docker/dockerfile:1.7
FROM node:24-alpine AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=build_ca,required=false \
    if [ -s /run/secrets/build_ca ]; then \
        npm_config_cafile=/run/secrets/build_ca npm ci; \
    else \
        npm ci; \
    fi
COPY frontend/ ./
RUN npm run lint && npm test && npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/invoice-auditor

RUN groupadd --system invoice-auditor \
    && useradd --system --gid invoice-auditor --home-dir /opt/invoice-auditor invoice-auditor \
    && mkdir -p /app/data \
    && chown -R invoice-auditor:invoice-auditor /app/data /opt/invoice-auditor

COPY pyproject.toml README.md ./
COPY app/ ./app/
RUN --mount=type=secret,id=build_ca,required=false \
    if [ -s /run/secrets/build_ca ]; then \
        PIP_CERT=/run/secrets/build_ca python -m pip install --no-cache-dir .; \
    else \
        python -m pip install --no-cache-dir .; \
    fi

COPY alembic.ini ./
COPY migrations/ ./migrations/

COPY --from=frontend-build /build/frontend/dist ./frontend/dist

USER invoice-auditor

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

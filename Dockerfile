FROM node:24-alpine AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/invoice-auditor

RUN groupadd --system invoice-auditor \
    && useradd --system --gid invoice-auditor --home-dir /opt/invoice-auditor invoice-auditor \
    && mkdir -p /app/data/tariffs /app/data/invoices /app/data/reports /app/data/backups \
    && chown -R invoice-auditor:invoice-auditor /app/data /opt/invoice-auditor

COPY pyproject.toml README.md ./
COPY app/ ./app/
RUN python -m pip install --no-cache-dir .

COPY alembic.ini ./
COPY migrations/ ./migrations/

COPY --from=frontend-build /build/frontend/dist ./frontend/dist

USER invoice-auditor

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

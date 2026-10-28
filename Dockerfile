FROM node:22-alpine AS ui
WORKDIR /ui/frontend
COPY frontend/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 VISION_DATA_DIR=/app/data/workspace
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY --from=ui /ui/src/visionguard/web ./src/visionguard/web
RUN --mount=type=cache,id=visionguard-pip,target=/root/.cache/pip pip install . && useradd --create-home app && mkdir -p /app/data /app/artifacts && chown -R app:app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "visionguard.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

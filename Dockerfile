FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (layer-cache friendly)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code (data/fairlane.db excluded via .dockerignore)
COPY agents/ agents/
COPY api/ api/
COPY compliance/ compliance/
COPY data/ data/
COPY observability/ observability/

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]

# TradeBot servis imajı: Python 3.12 + uv, root olmayan kullanıcı, UTC.
# Pano arayüzü (Faz 10) ayrı aşamada derlenir; imaja yalnız statik çıktı girer (Node çalışma anında yok).
FROM node:24-slim AS pano
WORKDIR /pano
COPY pano/package.json pano/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY pano/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 TZ=UTC
WORKDIR /app
# Bağımlılık katmanı (kod değişince yeniden kurulmaz)
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
COPY config ./config
COPY --from=pano /pano/dist ./pano/dist
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --create-home --uid 10001 tradebot && mkdir -p /app/data /app/log && chown -R tradebot /app
USER tradebot
CMD ["tradebot", "saglik", "--dongu", "300"]

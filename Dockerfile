FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
COPY packages/client/package.json packages/client/package.json
COPY apps/web/package.json apps/web/package.json
COPY apps/mobile/package.json apps/mobile/package.json
COPY apps/desktop/package.json apps/desktop/package.json
RUN ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm ci --ignore-scripts
COPY packages/client packages/client
COPY apps/web apps/web
RUN npm run build --workspace @jobhunt/web

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JOBHUNT_WEB_HOME=/data \
    JOBHUNT_WEB_HOSTS=localhost,127.0.0.1 \
    JOBHUNT_WEB_ORIGINS=http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174 \
    HOME=/home/jobhunt \
    TMPDIR=/run/jobhunt
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src src
COPY --from=frontend /build/apps/web/dist src/jobhunt/web/static
RUN pip install --no-cache-dir ".[web,docs]" \
    && groupadd --gid 10001 jobhunt \
    && useradd --uid 10001 --gid jobhunt --create-home jobhunt \
    && mkdir -p /data /run/jobhunt \
    && chown -R jobhunt:jobhunt /data /home/jobhunt /run/jobhunt
USER 10001:10001
EXPOSE 8650
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8650/api/health', timeout=4)"
CMD ["python", "-m", "jobhunt.web", "--host", "0.0.0.0", "--port", "8650", "--data-dir", "/data"]

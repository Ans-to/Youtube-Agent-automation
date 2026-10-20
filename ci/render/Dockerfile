# This test-only service runs the full test suite during Render's image build.
# The final runtime image contains only a tiny sanitized health endpoint.
FROM node:22-bookworm-slim AS node-runtime

FROM python:3.12-slim-bookworm AS tester
COPY --from=node-runtime /usr/local/ /usr/local/

ENV CI=1 \
    PUPPETEER_SKIP_DOWNLOAD=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    ffmpeg \
    fonts-liberation \
    fonts-noto-color-emoji \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libgbm1 \
    libglib2.0-0 \
    libnss3 \
    libpango-1.0-0 \
    libcairo2 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    libxshmfence1 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Any failed check fails the image build and prevents a successful deploy.
RUN bash ci/render/run_smoke_tests.sh && \
    printf '{"status":"passed","scope":"agent-queue-to-video-render-smoke-tests","publication":"disabled"}\n' > /tmp/ci-test-status.json

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY ci/render/status_server.py /app/status_server.py
COPY --from=tester /tmp/ci-test-status.json /app/ci-test-status.json
EXPOSE 10000
CMD ["python", "/app/status_server.py"]

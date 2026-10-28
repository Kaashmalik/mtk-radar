# Shared worker image — deterministic dependencies, ffmpeg present at build
# time. Previously each compose service ran `pip install` (and the renderer
# `apt-get install ffmpeg`) on every restart, so "the worker" was a different
# environment each time it booted.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /repo

COPY workers/requirements.txt /tmp/requirements-workers.txt
COPY workers/publishing/requirements.txt /tmp/requirements-publishing.txt
COPY workers/metrics/requirements.txt /tmp/requirements-metrics.txt
COPY workers/batch/requirements.txt /tmp/requirements-batch.txt
RUN pip install --no-cache-dir \
        -r /tmp/requirements-workers.txt \
        -r /tmp/requirements-publishing.txt \
        -r /tmp/requirements-metrics.txt \
        -r /tmp/requirements-batch.txt

COPY . .

# Writable locations are explicit. Mount named volumes over these paths so a
# restart/redeploy cannot lose media or the materialization cache.
RUN useradd --create-home --uid 10001 mtk \
    && mkdir -p /repo/projects /data /repo/.storage-cache /var/lib/mtk-outbox \
    && chown -R mtk:mtk /repo /data /var/lib/mtk-outbox

USER mtk

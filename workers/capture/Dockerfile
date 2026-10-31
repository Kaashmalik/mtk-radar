# Public-page capture worker (storyboard `page` scenes).
#
# Separate from the shared worker image: it needs Chromium and its system
# libraries, which the official Playwright image provides at the SAME
# version pinned in workers/capture/requirements.txt (keep them in step).
# The browser runs headless as the image's non-root `pwuser`; all of its
# traffic goes through the in-process validating egress proxy.

FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /repo

COPY workers/capture/requirements.txt /tmp/requirements-capture.txt
RUN pip install --no-cache-dir -r /tmp/requirements-capture.txt

# Only what the worker imports: shared packages + the capture worker.
COPY packages ./packages
COPY workers/capture ./workers/capture

RUN mkdir -p /data /tmp/page-captures \
    && chown -R pwuser:pwuser /repo /data /tmp/page-captures

USER pwuser

CMD ["python", "workers/capture/page_capture.py", "--watch", "--out", "/tmp/page-captures"]

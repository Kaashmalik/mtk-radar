FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Keep the repository layout so `media_api` can resolve ../../packages and the
# migration runner finds services/api/db without path guesses.
WORKDIR /repo
COPY services/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY services/api /repo/services/api
COPY packages /repo/packages

WORKDIR /repo/services/api
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

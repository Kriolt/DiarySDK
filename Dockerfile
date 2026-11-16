FROM python:3.15-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY diarysdk ./diarysdk
# Без [dev]: тесты и сборка в образ не нужны.
RUN pip install ".[server]" && rm -rf /app/diarysdk /app/pyproject.toml /app/README.md /app/LICENSE

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin diarysdk

# Файл ключей монтируется в контейнер только для чтения:
#   docker run --read-only -v "$PWD/api-keys:/etc/diarysdk/api-keys:ro" ...
ENV DIARYSDK_HOST=0.0.0.0 \
    DIARYSDK_PORT=8000 \
    DIARYSDK_KEYS_FILE=/etc/diarysdk/api-keys

USER 10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('DIARYSDK_PORT', '8000') + '/healthz', timeout=3)"]

CMD ["python", "-m", "diarysdk.server"]

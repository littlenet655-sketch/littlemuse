FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 DBMATE_MIGRATIONS_DIR=/app/db/migrations DBMATE_NO_DUMP_SCHEMA=true DBMATE_STRICT=true
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 libgomp1 curl ca-certificates && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL -o /usr/local/bin/dbmate https://github.com/amacneil/dbmate/releases/download/v2.34.1/dbmate-linux-amd64 \
    && echo "b002d5249d53d0c6c482ed761b5a806c6fb9a364fcc5f9db3e8763c1d9e40e1d  /usr/local/bin/dbmate" | sha256sum -c - \
    && chmod +x /usr/local/bin/dbmate \
    && dbmate --version
COPY requirements-core.txt requirements-safety.txt requirements-text.txt requirements-ai.txt ./
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements-ai.txt -r requirements-safety.txt \
    && python -m spacy download en_core_web_sm
COPY . .
RUN chmod +x /app/docker-entrypoint.sh
EXPOSE 8080
CMD ["/app/docker-entrypoint.sh"]

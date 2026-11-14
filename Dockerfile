FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=Africa/Tunis
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends cron tzdata libatomic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt \
    && playwright install --with-deps chromium

COPY . .
RUN chmod +x deploy/entrypoint.sh

ENTRYPOINT ["deploy/entrypoint.sh"]
CMD ["scheduler"]

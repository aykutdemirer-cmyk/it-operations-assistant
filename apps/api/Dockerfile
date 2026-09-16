# apps/api/Dockerfile — FastAPI/Uvicorn backend imajı.
#
# ÖNEMLİ: build context REPO KÖKÜ olmalı (`docker build -f apps/api/
# Dockerfile .` veya kök `docker-compose.yml`'deki gibi `context: .`),
# apps/api DEĞİL — çünkü `app/db/assets.py::_SCHEMA_SQL_PATH` runtime'da
# `infra/postgres/init.sql`'i `__file__`'dan GÖRELİ (parents[4]) olarak
# okuyor (bkz. o dosyadaki yorum: "tek doğruluk kaynağı"). İmaj içinde
# `/app/apps/api` ve `/app/infra` AYNI göreli derinlikte durmalı ki bu
# yol çözümü kırılmasın — ORM/Alembic YOK, ham SQL dosyası tek kaynak.
#
# Çok aşamalı build: derleyici araçları (asyncpg/cryptography/bcrypt gibi
# C uzantılı paketler için) yalnızca `builder` aşamasında kalır, son
# imaj yalnızca çalışma zamanı bağımlılıklarını taşır.

FROM python:3.12-slim AS builder

WORKDIR /build

# psycopg/asyncpg gibi paketlerin bazı sürümleri libpq başlıklarına
# ihtiyaç duyabilir; build-essential C uzantılarını (bcrypt/cryptography)
# derleyebilmek için gerekir. Yalnızca bu aşamada kalır.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt .
RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir --upgrade pip \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim

# libpq5 — asyncpg'nin çalışma zamanında ihtiyaç duyduğu paylaşımlı
# kütüphane (derleme başlıkları DEĞİL, yalnızca runtime .so).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH" PYTHONUNBUFFERED=1

# Tek doğruluk kaynağı şema dosyası (bkz. yukarıdaki yorum) + backend
# kaynak kodu — repo köküyle AYNI göreli yapı korunuyor.
COPY infra /app/infra
COPY apps/api /app/apps/api

WORKDIR /app/apps/api

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# --ws-ping-interval/--ws-ping-timeout — Faz 51: PAM RDP/SSH WebSocket
# kanalları uygulama-seviyesi bir ping mesajı TAŞIYAMAZ (ham Guacamole
# protokolünü bozar), bu yüzden uvicorn'un native keepalive'ı kullanılır.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--ws-ping-interval", "15", "--ws-ping-timeout", "15"]

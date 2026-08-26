# IT Operations Assistant

Kurumsal ağ altyapısını keşfedip merkezi bir veritabanında tutan, web
dashboard üzerinden gösteren bir platform. Mimari için
[`docs/architecture.md`](docs/architecture.md), faz planı için
[`docs/roadmap.md`](docs/roadmap.md), çalışma kuralları için
[`CLAUDE.md`](CLAUDE.md) dosyalarına bakın.

Şu an **Faz 1** tamamlandı: minimum çalışan iskelet (frontend + backend +
PostgreSQL bağlantısı), henüz network discovery yok.

## Gereksinimler

- Node.js 20+
- Python 3.11+
- Docker Desktop (PostgreSQL için)

## Kurulum

```bash
# Kök dizinde (frontend workspace bağımlılıkları)
npm install

# Backend için sanal ortam
cd apps/api
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows
# .venv/bin/pip install -r requirements.txt     # macOS/Linux
cd ../..
```

## Çalıştırma

**1. PostgreSQL (Docker Compose):**

```bash
docker compose -f infra/docker-compose.yml up -d
```

**2. Backend (FastAPI), `apps/api` içinde:**

```bash
cp .env.example .env   # gerekirse DATABASE_URL'i düzenleyin
.venv/Scripts/uvicorn app.main:app --reload --port 8000   # Windows
# .venv/bin/uvicorn app.main:app --reload --port 8000     # macOS/Linux
```

`http://localhost:8000/api/health` → `{"status": "ok"}`
`http://localhost:8000/api/health/db` → PostgreSQL çalışıyorsa `{"database": "ok"}`

**3. Frontend (Next.js), kök dizinde:**

```bash
cp apps/web/.env.local.example apps/web/.env.local
npm run dev:web
```

`http://localhost:3000` → dashboard, "Backend: 🟢 Connected" göstergesi.

## Test

```bash
# Backend
cd apps/api && .venv/Scripts/pytest -v

# Frontend
npm run test:web
```

`apps/api/tests/test_health_db.py`, PostgreSQL erişilemezse (Docker
çalışmıyorsa) otomatik olarak `skip` edilir; DB bağlantısını doğrulamak
için önce `docker compose -f infra/docker-compose.yml up -d` çalıştırın.

## Dizin Yapısı

```
apps/
  web/     # Next.js dashboard
  api/     # FastAPI backend
infra/
  docker-compose.yml   # PostgreSQL
docs/                  # mimari, roadmap, kararlar
```

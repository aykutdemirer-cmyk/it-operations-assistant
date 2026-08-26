import asyncio

import pytest

from app.db.connection import check_db_connection
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_db_returns_ok_when_postgres_reachable():
    try:
        asyncio.run(check_db_connection())
    except OSError:
        pytest.skip(
            "PostgreSQL erişilemiyor — önce `docker compose -f infra/docker-compose.yml up -d` çalıştırın"
        )

    response = client.get("/api/health/db")

    assert response.status_code == 200
    assert response.json() == {"database": "ok"}

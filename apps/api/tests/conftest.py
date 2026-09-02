from dotenv import load_dotenv

# Test koleksiyonu sırasında hangi test modülünün önce import edildiğine
# bağlı olarak `app.db.connection`'ın `DATABASE_URL`'i .env yüklenmeden
# önce okuma riski var (örn. yalnızca `tests/db/` çalıştırıldığında
# `app.main` hiç import edilmeyebilir, dolayısıyla `load_dotenv()` hiç
# çağrılmaz ve yanlış varsayılan bağlantı dizesine düşülür). Kök
# `conftest.py` pytest tarafından her zaman en önce yüklendiği için
# `.env` burada, herhangi bir `app.*` modülü import edilmeden önce yüklenir.
load_dotenv()

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


import asyncpg  # noqa: E402
import httpx  # noqa: E402
from unittest.mock import patch  # noqa: E402

from app.db.assets import ensure_schema  # noqa: E402
from app.db.assets import get_connection as _real_get_connection  # noqa: E402
from app.main import app as _app  # noqa: E402


@pytest.fixture
async def client():
    """`fastapi.testclient.TestClient` YERİNE: `TestClient` her isteği
    ayrı bir arka plan thread'inde (`anyio` blocking portal) çalıştırıyor
    — bu da `isolated_db`'nin asyncpg connection'ının bağlı olduğu event
    loop'tan FARKLI bir loop demek, ve asyncpg "attached to a different
    loop" hatasıyla çöküyor. `httpx.AsyncClient` + `ASGITransport` ise
    isteği doğrudan çağıran testin KENDİ event loop'unda çalıştırır —
    `isolated_db` ile aynı loop, aynı connection. Kullanım: `await
    client.get(...)`/`await client.post(...)` (senkron `TestClient`'tan
    farklı olarak `await` gerekir)."""
    transport = httpx.ASGITransport(app=_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c

# `get_connection()` her API route modülüne `from app.db.assets import
# get_connection` (veya `app.db.scans`) ile kopyalanıyor — bu yüzden tek
# bir yeri patch'lemek yetmiyor, TestClient üzerinden gerçekten
# çağrılabilecek her import noktası ayrı ayrı patch'lenmeli. `app.db.
# scans.get_connection`'ı patch'lemek, `app/routes/discovery.py`'nin
# `scans_repo.get_connection()` (modül referansı üzerinden, import-time
# kopyalanmamış) çağrısını da otomatik kapsar.
_ROUTE_GET_CONNECTION_TARGETS = [
    "app.routes.agent_commands.get_connection",
    "app.routes.agents.get_connection",
    "app.routes.asset_snmp_profiles.get_connection",
    "app.routes.assets.get_connection",
    "app.routes.discovery.get_connection",
    "app.routes.monitoring.get_connection",
    "app.routes.scans.get_connection",
    "app.routes.snmp.get_connection",
    "app.routes.snmp_profiles.get_connection",
    "app.db.agents.get_connection",
    "app.db.asset_snmp_profiles.get_connection",
    "app.db.assets.get_connection",
    "app.db.scans.get_connection",
    "app.db.snmp_profiles.get_connection",
]


class _NoCloseConnection:
    """`asyncpg.Connection` etrafında ince bir vekil — `.close()` hariç
    her şeyi gerçek connection'a devreder. `close` slotted/yalnızca-okunur
    olduğu için doğrudan `conn.close = ...` ataması yapılamıyor."""

    def __init__(self, real_conn: asyncpg.Connection):
        self._real_conn = real_conn

    def __getattr__(self, name):
        return getattr(self._real_conn, name)

    async def close(self, *args, **kwargs) -> None:
        return None


@pytest.fixture
async def isolated_db():
    """TÜM `get_connection()` çağrılarını — `TestClient` üzerinden
    yapılan gerçek HTTP istekleri dahil — testin sonunda ROLLBACK
    edilen TEK bir paylaşımlı transaction'a yönlendirir. Bu sayede bir
    testin içinde `TRUNCATE TABLE ...` çalışsa bile gerçek/kalıcı
    (commit edilmiş) veriye kalıcı bir etkisi olmaz — transaction hiç
    commit edilmez. PostgreSQL erişilemezse testi açık bir nedenle
    skip eder (mock database kullanılmaz).

    `tests/db/conftest.py::db_conn`'den farkı: o yalnızca repository
    fonksiyonlarına doğrudan geçirilen bir connection sağlıyor; bu
    fixture ONU KULLANAN gerçek FastAPI route'larının kendi
    `get_connection()` çağrılarını da AYNI transaction'a yönlendiriyor
    (route'lar `finally: await conn.close()` yaptığı için `close()`
    fixture süresince bilerek no-op'a çevriliyor)."""
    try:
        conn = await _real_get_connection()
    except OSError:
        pytest.skip(
            "PostgreSQL erişilemiyor — önce "
            "`docker compose -f infra/docker-compose.yml up -d` çalıştırın"
        )
        return

    await ensure_schema(conn)
    transaction = conn.transaction()
    await transaction.start()

    # `asyncpg.Connection.close` yalnızca-okunur (slotted) bir öznitelik —
    # doğrudan `conn.close = ...` atanamıyor. Bunun yerine `.close()`'u
    # no-op yapan ince bir vekil (proxy) nesne kullanılıyor; route'lar her
    # istekten sonra `finally: await conn.close()` çağırdığı için bu,
    # paylaşımlı transaction'ın erken kapanmasını engelliyor.
    wrapped = _NoCloseConnection(conn)

    async def _shared_connection() -> "_NoCloseConnection":
        return wrapped

    patchers = [patch(target, _shared_connection) for target in _ROUTE_GET_CONNECTION_TARGETS]
    for p in patchers:
        p.start()

    try:
        yield wrapped
    finally:
        for p in patchers:
            p.stop()
        await transaction.rollback()
        await conn.close()

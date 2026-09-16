import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.routes import (  # noqa: E402
    agent_commands,
    agent_ssh,
    agent_updates,
    agents,
    asset_snmp_profiles,
    assets,
    auth,
    discovery,
    health,
    ldap_settings,
    monitoring,
    pam_access_requests,
    pam_audit,
    pam_rdp,
    pam_rules,
    pam_server_groups,
    pam_ssh,
    pam_tags,
    pam_users,
    pam_vault,
    pam_web,
    scans,
    smtp_settings,
    snmp,
    snmp_profiles,
    tickets,
    vcenter,
    vcenter_settings,
)
from app.agents.scheduler import is_agent_maintenance_enabled, run_agent_maintenance  # noqa: E402
from app.discovery.scheduler import is_discovery_scheduler_enabled, run_discovery_scheduler  # noqa: E402
from app.auth.permissions import default_permissions_for_role  # noqa: E402
from app.auth.security import hash_password  # noqa: E402
from app.db.assets import ensure_schema as ensure_db_schema, get_connection  # noqa: E402
from app.db.users import (  # noqa: E402
    count_users,
    get_connection as get_users_connection,
    get_permissions,
    grant_permission,
    insert_user,
    list_users,
    set_permissions,
)
from app.services.ldap_scheduler import is_scheduled_sync_enabled, run_scheduled_ldap_sync  # noqa: E402
from app.snmp.scheduler import is_background_polling_enabled, run_background_poller  # noqa: E402

logger = logging.getLogger(__name__)


async def _ensure_schema_once() -> None:
    """Tüm tabloların (assets/scans/agents/agent_commands/snmp_profiles/
    ...) şeması TEK bir dosyadan (`infra/postgres/init.sql`) gelir —
    her modülün kendi `ensure_schema()`'sı aslında AYNI tam dosyayı
    çalıştırır (bkz. `app/db/assets.py::_SCHEMA_SQL_PATH` ile aynı
    desen diğer `app/db/*.py` modüllerinde). Bu yüzden BURADA, uygulama
    başlangıcında, TEK BİR ÇAĞRI yeterlidir.

    **Gerçek bir bug'ın düzeltmesi:** önceden birçok route kendi
    `_connect()` yardımcısında `ensure_schema(conn)`'i HER İSTEKTE
    yeniden çalıştırıyordu (DDL: `CREATE TABLE`/`ALTER TABLE`/`ADD
    CONSTRAINT`) — eşzamanlı istekler altında (ör. bir Agent'ın 3 arka
    plan thread'i + tek bir ek istek) CANLI olarak gerçek bir
    `asyncpg.exceptions.DeadlockDetectedError` üretti (bu oturumda
    tekrar tekrar gözlemlendi). O per-request çağrılar artık
    KALDIRILDI (bkz. ilgili route dosyaları) — şema artık yalnızca
    burada, uygulama YAŞAM DÖNGÜSÜ başına bir kez kurulur/güncellenir.
    PostgreSQL henüz erişilemezse (ör. konteyner henüz ayağa kalkmadı)
    uygulamayı ÇÖKERTMEZ — yalnızca loglar, ilk gerçek isteğe kadar
    tekrar denenmez (bu durumda o istek kendi 503'ünü döner, mevcut
    davranış korunur)."""
    try:
        conn = await get_connection()
    except OSError:
        logger.warning("PostgreSQL erişilemedi — şema başlangıçta kurulamadı, ilk isteğe kadar beklenecek")
        return
    try:
        await ensure_db_schema(conn)
        logger.info("Veritabanı şeması hazır (infra/postgres/init.sql)")
    finally:
        await conn.close()


async def _ensure_bootstrap_admin() -> None:
    """`users` tablosu bomboşken (bu projenin GERÇEK ilk çalıştırması,
    ya da bu artırım öncesi kaydolmuş HİÇBİR insan kullanıcı yoksa) tek
    bir ADMIN hesabı oluşturur — aksi halde kimse `/pam/*` ekranlarına
    hiç giremez (ilk-admin'i oluşturacak bir admin yok, klasik
    tavuk-yumurta). Yalnızca `.env`'de `BOOTSTRAP_ADMIN_USERNAME` VE
    `BOOTSTRAP_ADMIN_PASSWORD` İKİSİ BİRDEN varsa çalışır — sessizce
    tahmin edilebilir bir varsayılan şifre ÜRETİLMEZ. Kullanıcı zaten
    varsa (tablo boş değilse) HİÇBİR ŞEY yapmaz, mevcut hesaplara asla
    dokunmaz."""
    username = os.environ.get("BOOTSTRAP_ADMIN_USERNAME")
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
    if not username or not password:
        return
    try:
        conn = await get_users_connection()
    except OSError:
        logger.warning("PostgreSQL erişilemedi — bootstrap admin kontrolü atlandı")
        return
    try:
        if await count_users(conn) > 0:
            return
        row = await insert_user(conn, username=username, password_hash=hash_password(password), role="ADMIN", full_name=None)
        await set_permissions(conn, row["id"], default_permissions_for_role("ADMIN"))
        logger.info("İlk ADMIN kullanıcı oluşturuldu (BOOTSTRAP_ADMIN_USERNAME): %s", username)
    finally:
        await conn.close()


async def _ensure_default_permissions_backfill() -> None:
    """Faz 47 — `user_permissions` tablosu bu fazdan ÖNCE var olan
    kullanıcılar için (ör. Faz 46'da oluşturulan ilk bootstrap ADMIN)
    boş kalır — izin kontrolü artık salt role'e değil bu tabloya
    dayandığı için, hiç izin satırı OLMAYAN her kullanıcıya rolünün
    VARSAYILAN iznini bir kerelik atar. Zaten en az bir izni OLAN
    kullanıcılara (admin panelinden bilinçli olarak boşaltılmış olsa
    bile) DOKUNMAZ — bu yalnızca "hiç migrate edilmemiş" satırlar için
    bir geçiş kancasıdır, sürekli çalışan bir "sıfırlama" değil."""
    try:
        conn = await get_users_connection()
    except OSError:
        logger.warning("PostgreSQL erişilemedi — izin backfill'i atlandı")
        return
    try:
        for user in await list_users(conn):
            if not await get_permissions(conn, user["id"]):
                await set_permissions(conn, user["id"], default_permissions_for_role(user["role"]))
                logger.info("Kullanıcı için varsayılan izinler atandı (Faz 47 backfill): %s", user["username"])
    finally:
        await conn.close()


async def _ensure_tickets_permission_backfill() -> None:
    """Faz 62 — `TICKETS_VIEW` yeni bir izin türü. Bu fazdan ÖNCE var
    olan HİÇBİR kullanıcıda yok; menüde/`/tickets`'te 403 görmemeleri
    için, HER kullanıcıya (rol ayrımı olmadan — Helpdesk tüm roller için
    varsayılan açık) bir kerelik eklenir. `grant_permission` tek izni
    ekler, kullanıcının diğer (özelleştirilmiş olabilecek) izinlerine
    DOKUNMAZ; zaten varsa no-op — bu yüzden her başlangıçta güvenle
    çalışır (Faz 47 backfill'iyle aynı "geçiş kancası" ilkesi)."""
    try:
        conn = await get_users_connection()
    except OSError:
        logger.warning("PostgreSQL erişilemedi — TICKETS_VIEW backfill'i atlandı")
        return
    try:
        for user in await list_users(conn):
            if await grant_permission(conn, user["id"], "TICKETS_VIEW"):
                logger.info("TICKETS_VIEW izni atandı (Faz 62 backfill): %s", user["username"])
    finally:
        await conn.close()


async def _ensure_ticket_roles_backfill() -> None:
    """Faz 65 — `users.ticket_role` (init.sql'de zaten var, varsayılan
    REQUESTER). Sistemde hiç TECHNICIAN/ADMIN bilet rolü yoksa (ilk
    kez), sistem `role='ADMIN'` olan kullanıcıları bilet ADMIN'ine
    yükseltir — aksi halde ilk restart'tan sonra KİMSE tüm biletleri
    yönetemez (Faz 47/62 backfill'iyle aynı idempotent "geçiş kancası"
    ilkesi; bir kez çalışır, sonra no-op)."""
    try:
        conn = await get_users_connection()
    except OSError:
        logger.warning("PostgreSQL erişilemedi — ticket_role backfill'i atlandı")
        return
    try:
        already = await conn.fetchval("SELECT count(*) FROM users WHERE ticket_role IN ('TECHNICIAN', 'ADMIN')")
        if already:
            return
        promoted = await conn.execute(
            "UPDATE users SET ticket_role = 'ADMIN' WHERE role = 'ADMIN' AND ticket_role = 'REQUESTER'"
        )
        if promoted != "UPDATE 0":
            logger.info("Bilet rolü backfill (Faz 65): ADMIN kullanıcılar bilet ADMIN'ine yükseltildi — %s", promoted)
    finally:
        await conn.close()


async def _ensure_vcenter_permission_backfill() -> None:
    """Faz 72 — `VCENTER_VIEW` yeni bir izin türü, `TICKETS_VIEW`
    (Faz 62) ile AYNI "her kullanıcıya bir kerelik varsayılan görüntüleme
    izni" deseni. `VCENTER_ADMIN` OPERATOR/VIEWER'a backfill EDİLMİYOR
    (güç işlemleri daha yüksek riskli bir yetki, Admin panelinden elle
    açılması gerekir) — ama `role='ADMIN'` olan kullanıcılara VERİLİR:
    `default_permissions_for_role("ADMIN")`'in `ALL_PERMISSIONS`
    varsayılanı yalnızca YENİ oluşturulan/hiç izin satırı olmayan
    kullanıcılarda (Faz 47 backfill) devreye girer — Faz 72'den ÖNCE
    zaten izin satırları OLAN mevcut bir ADMIN, bu ek adım olmadan
    `VCENTER_ADMIN`'i asla almazdı (Faz 65'in `ticket_role` backfill'iyle
    AYNI "role='ADMIN' → ilgili admin izni" ilkesi)."""
    try:
        conn = await get_users_connection()
    except OSError:
        logger.warning("PostgreSQL erişilemedi — VCENTER_VIEW backfill'i atlandı")
        return
    try:
        for user in await list_users(conn):
            if await grant_permission(conn, user["id"], "VCENTER_VIEW"):
                logger.info("VCENTER_VIEW izni atandı (Faz 72 backfill): %s", user["username"])
            if user["role"] == "ADMIN" and await grant_permission(conn, user["id"], "VCENTER_ADMIN"):
                logger.info("VCENTER_ADMIN izni atandı (Faz 72 backfill): %s", user["username"])
    finally:
        await conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # `httpx.ASGITransport` (bkz. `tests/conftest.py::client`) FastAPI
    # lifespan event'lerini TETİKLEMEZ — bu yüzden bu bloktaki hiçbir
    # şey testlerde çalışmaz; `tests/conftest.py::isolated_db` kendi
    # `ensure_schema()` çağrısını BAĞIMSIZ olarak, her testte ayrı
    # yapar (bkz. o fixture'ın docstring'i) — test izolasyonuna hiçbir
    # etkisi YOK.
    await _ensure_schema_once()
    await _ensure_bootstrap_admin()
    await _ensure_default_permissions_backfill()
    await _ensure_tickets_permission_backfill()
    await _ensure_ticket_roles_backfill()
    await _ensure_vcenter_permission_backfill()

    tasks: list[asyncio.Task] = []
    if is_background_polling_enabled():
        tasks.append(asyncio.create_task(run_background_poller()))
    else:
        logger.info("Arka plan SNMP polling worker devre dışı (SNMP_BACKGROUND_POLLING_ENABLED=false)")
    if is_agent_maintenance_enabled():
        tasks.append(asyncio.create_task(run_agent_maintenance()))
    if is_discovery_scheduler_enabled():
        tasks.append(asyncio.create_task(run_discovery_scheduler()))
    else:
        logger.info("Zamanlanmış tarama worker'ı devre dışı (DISCOVERY_SCHEDULER_ENABLED=false)")
    if is_scheduled_sync_enabled():
        tasks.append(asyncio.create_task(run_scheduled_ldap_sync()))
    else:
        logger.info("Zamanlanmış LDAP senkronizasyonu devre dışı (LDAP_SCHEDULED_SYNC_ENABLED=false)")
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="IT Operations Assistant API", lifespan=lifespan)

# Normal akışta frontend backend'e hiç doğrudan (cross-origin) fetch
# ATMAZ — `apps/web/next.config.ts::rewrites()` `/api/*` isteklerini
# sunucu tarafında proxy'ler, tarayıcı için her zaman same-origin'dir.
# Bu liste yalnızca (a) `NEXT_PUBLIC_API_URL` açıkça mutlak bir adrese
# set edilmişse ya da (b) RDP/SSH gibi proxy'lenmeyen doğrudan
# bağlantılar için savunma amaçlı bir ek katmandır. `localhost:3000`
# her zaman dahildir; LAN üzerinden başka bir origin'e ihtiyaç varsa
# `.env`'de virgülle ayrılmış `CORS_ADDITIONAL_ORIGINS` ile genişletin
# — sırra dokunmaz, yalnızca origin listesi, koda hardcode edilmez.
_additional_cors_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ADDITIONAL_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", *_additional_cors_origins],
    # PUT/DELETE Faz 29'da SNMP Profile CRUD için eklendi (bkz.
    # app/routes/snmp_profiles.py) — önceden yalnızca GET/POST vardı.
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(discovery.router)
app.include_router(assets.router)
app.include_router(scans.router)
app.include_router(snmp.router)
app.include_router(monitoring.router)
app.include_router(agents.router)
app.include_router(agent_commands.router)
app.include_router(agent_ssh.router)
app.include_router(agent_updates.router)
app.include_router(snmp_profiles.router)
app.include_router(asset_snmp_profiles.router)
app.include_router(pam_users.router)
app.include_router(pam_vault.router)
app.include_router(pam_rules.router)
app.include_router(pam_rules.my_access_router)
app.include_router(pam_tags.router)
app.include_router(pam_server_groups.router)
app.include_router(pam_access_requests.router)
app.include_router(pam_access_requests.my_router)
app.include_router(pam_audit.router)
app.include_router(pam_audit.ws_router)
app.include_router(ldap_settings.router)
app.include_router(pam_ssh.router)
app.include_router(pam_rdp.router)
app.include_router(pam_web.router)
app.include_router(tickets.router)
app.include_router(smtp_settings.router)
app.include_router(vcenter.router)
app.include_router(vcenter_settings.router)

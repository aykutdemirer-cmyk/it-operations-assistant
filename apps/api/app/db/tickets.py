"""Faz 62 — `tickets`/`ticket_comments`/`ticket_number_seq` için DB
katmanı (ham SQL/`asyncpg`, ORM yok). İki tablo tek bir özelliğin
(Helpdesk) parçası olduğu için `app/db/pam.py`/`app/db/agents.py`
deseniyle tutarlı tek modülde birleştirildi."""

from datetime import datetime
from uuid import UUID

import asyncpg

from app.db.connection import DATABASE_URL


async def get_connection() -> asyncpg.Connection:
    return await asyncpg.connect(DATABASE_URL, timeout=2)


# `tickets` + oluşturan/atanan kullanıcı adları + Faz 63 dinamik
# kategori/departman adlarını LEFT JOIN'le getirir.
_TICKET_SELECT = """
SELECT
    t.id, t.ticket_number, t.title, t.description, t.priority, t.status,
    t.created_by, cu.username AS created_by_username,
    t.assigned_to, au.username AS assigned_to_username,
    t.category_id, cat.name AS category_name,
    t.department_id, dep.name AS department_name,
    t.created_at, t.updated_at, t.resolved_at, t.sla_due_at
FROM tickets t
JOIN users cu ON cu.id = t.created_by
LEFT JOIN users au ON au.id = t.assigned_to
LEFT JOIN ticket_categories cat ON cat.id = t.category_id
LEFT JOIN ticket_departments dep ON dep.id = t.department_id
"""


async def next_ticket_number(conn: asyncpg.Connection, *, year: int) -> str:
    """Yıl bazlı atomik sayaç — `INC-YYYY-NNNN`. Aynı transaction
    içinde çağrılır; `ON CONFLICT ... DO UPDATE` satır kilidi
    eşzamanlı iki oluşturmanın aynı numarayı almasını engeller."""
    value = await conn.fetchval(
        """
        INSERT INTO ticket_number_seq (year, last_value)
        VALUES ($1, 1)
        ON CONFLICT (year) DO UPDATE SET last_value = ticket_number_seq.last_value + 1
        RETURNING last_value;
        """,
        year,
    )
    return f"INC-{year}-{value:04d}"


async def insert_ticket(
    conn: asyncpg.Connection,
    *,
    ticket_number: str,
    title: str,
    description: str,
    category_id: UUID,
    department_id: UUID | None,
    priority: str,
    created_by: UUID,
    sla_due_at: datetime | None,
) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        INSERT INTO tickets (ticket_number, title, description, category_id, department_id, priority, created_by, sla_due_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id;
        """,
        ticket_number,
        title,
        description,
        category_id,
        department_id,
        priority,
        created_by,
        sla_due_at,
    )
    return await conn.fetchrow(_TICKET_SELECT + " WHERE t.id = $1", row["id"])


async def get_ticket(conn: asyncpg.Connection, ticket_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(_TICKET_SELECT + " WHERE t.id = $1", ticket_id)


_TICKET_COUNT_FROM = """
FROM tickets t
JOIN users cu ON cu.id = t.created_by
LEFT JOIN ticket_categories cat ON cat.id = t.category_id
LEFT JOIN ticket_departments dep ON dep.id = t.department_id
"""


async def list_tickets(
    conn: asyncpg.Connection,
    *,
    status: str | None = None,
    priority: str | None = None,
    category_id: UUID | None = None,
    department_id: UUID | None = None,
    search: str | None = None,
    created_by_scope: UUID | None = None,
    assignee_scope: UUID | None = None,
    overdue: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[asyncpg.Record], int]:
    conditions: list[str] = []
    params: list = []
    # Faz 65 — REQUESTER yalnızca kendi açtığı biletleri görür.
    if created_by_scope is not None:
        params.append(created_by_scope)
        conditions.append(f"t.created_by = ${len(params)}")
    # Faz 69 — "bana atananlar".
    if assignee_scope is not None:
        params.append(assignee_scope)
        conditions.append(f"t.assigned_to = ${len(params)}")
    # Faz 67 — yalnızca SLA'sı aşılmış AÇIK biletler.
    if overdue:
        conditions.append(
            "t.sla_due_at IS NOT NULL AND t.sla_due_at < now() AND t.status NOT IN ('RESOLVED', 'CLOSED')"
        )
    if status:
        params.append(status)
        conditions.append(f"t.status = ${len(params)}")
    if priority:
        params.append(priority)
        conditions.append(f"t.priority = ${len(params)}")
    if category_id:
        params.append(category_id)
        conditions.append(f"t.category_id = ${len(params)}")
    if department_id:
        params.append(department_id)
        conditions.append(f"t.department_id = ${len(params)}")
    if search:
        params.append(f"%{search}%")
        idx = len(params)
        conditions.append(
            f"(t.ticket_number ILIKE ${idx} OR t.title ILIKE ${idx} OR cu.username ILIKE ${idx} "
            f"OR cat.name ILIKE ${idx} OR dep.name ILIKE ${idx})"
        )
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    total = await conn.fetchval(f"SELECT count(*){_TICKET_COUNT_FROM}{where}", *params)

    params.append(limit)
    params.append(offset)
    rows = await conn.fetch(
        _TICKET_SELECT + where + f" ORDER BY t.created_at DESC LIMIT ${len(params) - 1} OFFSET ${len(params)}",
        *params,
    )
    return rows, total


async def ticket_metrics(conn: asyncpg.Connection, *, created_by_scope: UUID | None = None) -> dict:
    """Faz 68 — salt-okunur helpdesk metrikleri. `created_by_scope`
    verilirse (REQUESTER) yalnızca o kullanıcının biletleri sayılır."""
    scope = "" if created_by_scope is None else " WHERE t.created_by = $1"
    args: list = [] if created_by_scope is None else [created_by_scope]

    totals = await conn.fetchrow(
        f"""
        SELECT
            count(*) AS total,
            count(*) FILTER (WHERE status NOT IN ('RESOLVED', 'CLOSED')) AS open_tickets,
            count(*) FILTER (WHERE status IN ('RESOLVED', 'CLOSED')) AS closed_tickets,
            count(*) FILTER (
                WHERE status NOT IN ('RESOLVED', 'CLOSED')
                AND sla_due_at IS NOT NULL AND sla_due_at < now()
            ) AS overdue_open,
            avg(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600.0)
                FILTER (WHERE resolved_at IS NOT NULL) AS avg_resolution_hours,
            count(*) FILTER (WHERE resolved_at IS NOT NULL AND sla_due_at IS NOT NULL) AS resolved_with_sla,
            count(*) FILTER (
                WHERE resolved_at IS NOT NULL AND sla_due_at IS NOT NULL AND resolved_at <= sla_due_at
            ) AS resolved_within_sla
        FROM tickets t{scope};
        """,
        *args,
    )

    by_status = await conn.fetch(f"SELECT status AS k, count(*) AS c FROM tickets t{scope} GROUP BY status", *args)
    by_priority = await conn.fetch(f"SELECT priority AS k, count(*) AS c FROM tickets t{scope} GROUP BY priority", *args)
    by_category = await conn.fetch(
        f"""
        SELECT COALESCE(cat.name, '—') AS k, count(*) AS c
        FROM tickets t LEFT JOIN ticket_categories cat ON cat.id = t.category_id{scope}
        GROUP BY cat.name ORDER BY c DESC;
        """,
        *args,
    )
    by_department = await conn.fetch(
        f"""
        SELECT COALESCE(dep.name, '—') AS k, count(*) AS c
        FROM tickets t LEFT JOIN ticket_departments dep ON dep.id = t.department_id{scope}
        GROUP BY dep.name ORDER BY c DESC;
        """,
        *args,
    )

    # Son 30 gün — gün bazında açılan / çözülen.
    day_scope_c = "" if created_by_scope is None else " AND t.created_by = $1"
    daily = await conn.fetch(
        f"""
        WITH days AS (
            SELECT generate_series(date_trunc('day', now()) - interval '29 days', date_trunc('day', now()), interval '1 day') AS d
        )
        SELECT
            to_char(days.d, 'YYYY-MM-DD') AS day,
            (SELECT count(*) FROM tickets t WHERE date_trunc('day', t.created_at) = days.d{day_scope_c}) AS created,
            (SELECT count(*) FROM tickets t WHERE date_trunc('day', t.resolved_at) = days.d{day_scope_c}) AS resolved
        FROM days ORDER BY days.d;
        """,
        *args,
    )

    def _kv(rows) -> dict[str, int]:
        return {r["k"]: r["c"] for r in rows}

    return {
        "total": totals["total"],
        "open_tickets": totals["open_tickets"],
        "closed_tickets": totals["closed_tickets"],
        "overdue_open": totals["overdue_open"],
        "avg_resolution_hours": (
            round(float(totals["avg_resolution_hours"]), 1) if totals["avg_resolution_hours"] is not None else None
        ),
        "sla_compliance_pct": (
            round(100.0 * totals["resolved_within_sla"] / totals["resolved_with_sla"], 1)
            if totals["resolved_with_sla"]
            else None
        ),
        "by_status": _kv(by_status),
        "by_priority": _kv(by_priority),
        "by_category": _kv(by_category),
        "by_department": _kv(by_department),
        "daily": [{"day": r["day"], "created": r["created"], "resolved": r["resolved"]} for r in daily],
    }


async def ticket_stats(conn: asyncpg.Connection, *, user_id: UUID, created_by_scope: UUID | None = None) -> asyncpg.Record:
    """Üst paneldeki 4 KPI — tek sorguda. Faz 65: `created_by_scope`
    verilirse (REQUESTER) sayaçlar yalnızca o kullanıcının biletlerini
    kapsar."""
    scope = "" if created_by_scope is None else " WHERE created_by = $2"
    args: list = [user_id]
    if created_by_scope is not None:
        args.append(created_by_scope)
    return await conn.fetchrow(
        f"""
        SELECT
            count(*) FILTER (WHERE status NOT IN ('RESOLVED', 'CLOSED')) AS open_tickets,
            count(*) FILTER (WHERE assigned_to = $1 AND status NOT IN ('RESOLVED', 'CLOSED')) AS assigned_to_me,
            count(*) FILTER (
                WHERE status NOT IN ('RESOLVED', 'CLOSED')
                AND (priority = 'CRITICAL' OR (sla_due_at IS NOT NULL AND sla_due_at < now()))
            ) AS critical_or_overdue,
            count(*) FILTER (
                WHERE status IN ('RESOLVED', 'CLOSED')
                AND resolved_at IS NOT NULL
                AND resolved_at >= date_trunc('month', now())
            ) AS resolved_this_month
        FROM tickets{scope};
        """,
        *args,
    )


async def update_ticket_status_and_assignee(
    conn: asyncpg.Connection,
    ticket_id: UUID,
    *,
    status: str | None,
    set_assignee: bool,
    assigned_to: UUID | None,
    mark_resolved: bool,
    clear_resolved: bool,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        UPDATE tickets SET
            status = COALESCE($2, status),
            assigned_to = CASE WHEN $3 THEN $4 ELSE assigned_to END,
            resolved_at = CASE
                WHEN $5 THEN clock_timestamp()
                WHEN $6 THEN NULL
                ELSE resolved_at
            END,
            updated_at = clock_timestamp()
        WHERE id = $1
        RETURNING id;
        """,
        ticket_id,
        status,
        set_assignee,
        assigned_to,
        mark_resolved,
        clear_resolved,
    )


_COMMENT_SELECT = """
SELECT
    c.id, c.ticket_id, c.author_id, au.username AS author_username,
    c.event, c.body, c.status_from, c.status_to,
    fu.username AS assigned_from_username, tu.username AS assigned_to_username,
    c.is_internal, c.created_at
FROM ticket_comments c
JOIN users au ON au.id = c.author_id
LEFT JOIN users fu ON fu.id = c.assigned_from
LEFT JOIN users tu ON tu.id = c.assigned_to
"""


async def insert_comment(
    conn: asyncpg.Connection,
    *,
    ticket_id: UUID,
    author_id: UUID,
    event: str,
    body: str | None,
    status_from: str | None,
    status_to: str | None,
    assigned_from: UUID | None,
    assigned_to: UUID | None,
    is_internal: bool = False,
) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        INSERT INTO ticket_comments (ticket_id, author_id, event, body, status_from, status_to, assigned_from, assigned_to, is_internal)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id;
        """,
        ticket_id,
        author_id,
        event,
        body,
        status_from,
        status_to,
        assigned_from,
        assigned_to,
        is_internal,
    )
    return await conn.fetchrow(_COMMENT_SELECT + " WHERE c.id = $1", row["id"])


async def list_comments(conn: asyncpg.Connection, ticket_id: UUID, *, include_internal: bool = True) -> list[asyncpg.Record]:
    # `include_internal=False` — REQUESTER'a IT'nin gizli notları HİÇ
    # dönmez (bkz. `service.py::get_ticket_detail`).
    where = " WHERE c.ticket_id = $1" if include_internal else " WHERE c.ticket_id = $1 AND c.is_internal = false"
    return await conn.fetch(_COMMENT_SELECT + where + " ORDER BY c.created_at ASC", ticket_id)


# ---- Faz 63 — dinamik Departman + Kategori taksonomisi ---------------
# `ticket_departments` ve `ticket_categories` şema olarak birebir aynı;
# tekrar yazmamak için `_table` parametreli tek bir fonksiyon seti.
# Çağıran katman (service) tablo adını sabit ('ticket_departments' /
# 'ticket_categories') geçer — SQL injection yüzeyi YOK.


async def list_taxonomy(conn: asyncpg.Connection, table: str, *, include_inactive: bool) -> list[asyncpg.Record]:
    where = "" if include_inactive else " WHERE is_active = true"
    return await conn.fetch(f"SELECT id, name, is_active FROM {table}{where} ORDER BY name ASC")


async def get_taxonomy_by_name(conn: asyncpg.Connection, table: str, name: str) -> asyncpg.Record | None:
    return await conn.fetchrow(f"SELECT id, name, is_active FROM {table} WHERE lower(name) = lower($1)", name)


async def get_taxonomy(conn: asyncpg.Connection, table: str, item_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(f"SELECT id, name, is_active FROM {table} WHERE id = $1", item_id)


async def insert_taxonomy(conn: asyncpg.Connection, table: str, name: str) -> asyncpg.Record:
    return await conn.fetchrow(
        f"INSERT INTO {table} (name) VALUES ($1) RETURNING id, name, is_active", name
    )


async def set_taxonomy_active(conn: asyncpg.Connection, table: str, item_id: UUID, *, is_active: bool) -> asyncpg.Record | None:
    return await conn.fetchrow(
        f"UPDATE {table} SET is_active = $2 WHERE id = $1 RETURNING id, name, is_active", item_id, is_active
    )


# ---- Faz 67 — SLA politikası ----------------------------------------


async def get_sla_policy(conn: asyncpg.Connection) -> dict[str, int]:
    """`{priority: sla_hours}`. Satır yoksa boş dict döner — çağıran
    katman kod sabitine (`SLA_HOURS_BY_PRIORITY`) düşer."""
    rows = await conn.fetch("SELECT priority, sla_hours FROM ticket_sla_policy")
    return {row["priority"]: row["sla_hours"] for row in rows}


async def upsert_sla_policy(conn: asyncpg.Connection, priority: str, sla_hours: int) -> asyncpg.Record:
    return await conn.fetchrow(
        """
        INSERT INTO ticket_sla_policy (priority, sla_hours) VALUES ($1, $2)
        ON CONFLICT (priority) DO UPDATE SET sla_hours = EXCLUDED.sla_hours, updated_at = clock_timestamp()
        RETURNING priority, sla_hours, updated_at;
        """,
        priority,
        sla_hours,
    )

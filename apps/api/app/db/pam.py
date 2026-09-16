"""Faz 46 — `vault_credentials`/`pam_access_rules`/`pam_session_logs`
için DB katmanı. Üç tablo birlikte tek bir özelliğin (PAM) parçası
olduğu için (Faz 28'in `agents.py`'sindeki gibi ilgili tabloları tek
dosyada tutma deseniyle tutarlı) tek modülde birleştirildi."""

from datetime import datetime
from uuid import UUID

import asyncpg

from app.db.connection import DATABASE_URL

# Hiçbir tabloda JSONB kolon yok — codec kaydına gerek yok.


async def get_connection() -> asyncpg.Connection:
    return await asyncpg.connect(DATABASE_URL, timeout=2)


# ---- vault_credentials ----------------------------------------------


async def insert_credential(
    conn: asyncpg.Connection,
    *,
    name: str,
    credential_type: str,
    username: str,
    domain: str | None,
    encrypted_payload: str,
    created_by: UUID | None,
) -> asyncpg.Record:
    return await conn.fetchrow(
        """
        INSERT INTO vault_credentials (name, credential_type, username, domain, encrypted_payload, created_by)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *;
        """,
        name,
        credential_type,
        username,
        domain,
        encrypted_payload,
        created_by,
    )


async def get_credential(conn: asyncpg.Connection, credential_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM vault_credentials WHERE id = $1", credential_id)


async def list_credentials(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch("SELECT * FROM vault_credentials ORDER BY created_at ASC")


async def update_credential(
    conn: asyncpg.Connection,
    credential_id: UUID,
    *,
    name: str | None,
    username: str | None,
    domain_set: bool,
    domain: str | None,
    encrypted_payload: str | None,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        UPDATE vault_credentials SET
            name = COALESCE($2, name),
            username = COALESCE($3, username),
            domain = CASE WHEN $4 THEN $5 ELSE domain END,
            encrypted_payload = COALESCE($6, encrypted_payload),
            updated_at = clock_timestamp()
        WHERE id = $1
        RETURNING *;
        """,
        credential_id,
        name,
        username,
        domain_set,
        domain,
        encrypted_payload,
    )


async def delete_credential(conn: asyncpg.Connection, credential_id: UUID) -> bool:
    result = await conn.execute("DELETE FROM vault_credentials WHERE id = $1", credential_id)
    return result != "DELETE 0"


async def credential_in_use_count(conn: asyncpg.Connection, credential_id: UUID) -> int:
    return await conn.fetchval("SELECT count(*) FROM pam_access_rules WHERE credential_id = $1", credential_id)


# ---- pam_access_rules --------------------------------------------------

_RULE_JOIN_SELECT = """
SELECT
    r.id, r.user_id, u.username, r.ad_group_id, g.name AS ad_group_name,
    r.asset_id, a.hostname AS asset_hostname, a.ip_address AS asset_ip_address,
    a.status AS asset_status,
    r.tag_id, tg.name AS tag_name,
    r.server_group_id, sg.name AS server_group_name,
    r.credential_id, c.name AS credential_name,
    r.allow_rdp, r.allow_ssh, r.allow_web, r.is_active, r.max_session_duration_mins, r.valid_until,
    r.created_at, r.updated_at
FROM pam_access_rules r
LEFT JOIN users u ON u.id = r.user_id
LEFT JOIN ad_groups g ON g.id = r.ad_group_id
LEFT JOIN assets a ON a.id = r.asset_id
LEFT JOIN tags tg ON tg.id = r.tag_id
LEFT JOIN server_groups sg ON sg.id = r.server_group_id
JOIN vault_credentials c ON c.id = r.credential_id
"""


async def insert_rule(
    conn: asyncpg.Connection,
    *,
    user_id: UUID | None,
    ad_group_id: UUID | None,
    asset_id: UUID | None,
    tag_id: UUID | None,
    server_group_id: UUID | None,
    credential_id: UUID,
    allow_rdp: bool,
    allow_ssh: bool,
    allow_web: bool,
    max_session_duration_mins: int,
    valid_until: datetime | None,
    created_by: UUID | None,
) -> asyncpg.Record:
    """Faz 55 — `asset_id`/`tag_id`/`server_group_id`'den TAM OLARAK
    biri dolu olmalı (Pydantic validator + DB CHECK constraint ile
    ÇİFT güvenceli, bkz. `app/pam/models.py`). Tekrar/duplikasyon
    kontrolü artık PROAKTIF bir SELECT ile DEĞİL, DB'nin kendi UNIQUE
    kısıtlarının fırlattığı `asyncpg.UniqueViolationError`'ı çağıran
    tarafın (`app/pam/service.py::create_rule`) yakalamasıyla yapılıyor
    — 6 farklı (principal × cihaz hedefi) kombinasyonu için 6 ayrı
    ön-kontrol SORGUSU yazmak yerine, zaten var olan DB kısıtına
    güvenmek daha basit/az hataya açık."""
    row = await conn.fetchrow(
        """
        INSERT INTO pam_access_rules (
            user_id, ad_group_id, asset_id, tag_id, server_group_id, credential_id,
            allow_rdp, allow_ssh, allow_web, max_session_duration_mins, valid_until, created_by
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        RETURNING id;
        """,
        user_id,
        ad_group_id,
        asset_id,
        tag_id,
        server_group_id,
        credential_id,
        allow_rdp,
        allow_ssh,
        allow_web,
        max_session_duration_mins,
        valid_until,
        created_by,
    )
    return await conn.fetchrow(_RULE_JOIN_SELECT + " WHERE r.id = $1", row["id"])


async def get_rule(conn: asyncpg.Connection, rule_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(_RULE_JOIN_SELECT + " WHERE r.id = $1", rule_id)


_DEVICE_RULE_MATCH = """(
    r.asset_id = $2
    OR r.tag_id IN (SELECT tag_id FROM asset_tag_assignments WHERE asset_id = $2)
    OR r.server_group_id IN (SELECT server_group_id FROM server_group_members WHERE asset_id = $2)
)"""

_DEVICE_SPECIFICITY_ORDER = "CASE WHEN r.asset_id IS NOT NULL THEN 0 WHEN r.tag_id IS NOT NULL THEN 1 ELSE 2 END"


async def get_device_rule_for_user(conn: asyncpg.Connection, user_id: UUID, asset_id: UUID) -> asyncpg.Record | None:
    """Faz 55 — bir asset için bu YEREL kullanıcının kuralını, üç
    olası kaynaktan (doğrudan asset > etiket > cihaz grubu — bu
    ÖNCELİK sırasıyla) TEK sorguda çözer. `get_rule_for_user_asset`'in
    (Faz 46-54) yerini alır — artık yalnızca doğrudan asset kuralı
    DEĞİL, etiket/grup kuralları da kapsanır."""
    return await conn.fetchrow(
        _RULE_JOIN_SELECT + f" WHERE r.user_id = $1 AND {_DEVICE_RULE_MATCH}"
        f" ORDER BY {_DEVICE_SPECIFICITY_ORDER} LIMIT 1",
        user_id,
        asset_id,
    )


async def get_device_rule_for_ad_groups(
    conn: asyncpg.Connection, ad_group_ids: list[UUID], asset_id: UUID
) -> asyncpg.Record | None:
    """Faz 55 — AYNI genişleme, bağlı bir AD kullanıcısının ÜYE OLDUĞU
    gruplardan herhangi biri için (`get_rule_for_ad_groups_asset`'in,
    Faz 49-54, yerini alır)."""
    if not ad_group_ids:
        return None
    return await conn.fetchrow(
        _RULE_JOIN_SELECT + f" WHERE r.ad_group_id = ANY($1::uuid[]) AND {_DEVICE_RULE_MATCH}"
        f" ORDER BY {_DEVICE_SPECIFICITY_ORDER}, r.updated_at DESC LIMIT 1",
        ad_group_ids,
        asset_id,
    )


async def get_rule_for_exact_user_target(
    conn: asyncpg.Connection,
    user_id: UUID,
    *,
    asset_id: UUID | None,
    tag_id: UUID | None,
    server_group_id: UUID | None,
) -> asyncpg.Record | None:
    """Faz 56 — bir erişim talebi onaylanırken, TAM OLARAK aynı
    (kullanıcı, cihaz hedefi) için ZATEN bir kural var mı diye bakar
    (varsa GENİŞLETİLİR, yoksa YENİ oluşturulur — bkz. `app/pam/
    service.py::approve_access_request`). `get_device_rule_for_user`
    ile KARIŞTIRILMASIN — o, en spesifik kuralı ÇÖZER (bir SSH/RDP
    bağlantısı açılırken), bu ise TAM eşleşen kuralı arar (mevcut
    UNIQUE kısıtları sayesinde en fazla bir satır döner)."""
    if asset_id is not None:
        return await conn.fetchrow(_RULE_JOIN_SELECT + " WHERE r.user_id = $1 AND r.asset_id = $2", user_id, asset_id)
    if tag_id is not None:
        return await conn.fetchrow(_RULE_JOIN_SELECT + " WHERE r.user_id = $1 AND r.tag_id = $2", user_id, tag_id)
    return await conn.fetchrow(
        _RULE_JOIN_SELECT + " WHERE r.user_id = $1 AND r.server_group_id = $2", user_id, server_group_id
    )


_EXPANDED_TAG_RULE_SELECT = """
SELECT
    r.id, a.id AS asset_id, a.hostname AS asset_hostname, a.ip_address AS asset_ip_address,
    a.status AS asset_status,
    r.allow_rdp, r.allow_ssh, r.allow_web, r.is_active, r.max_session_duration_mins, r.valid_until
FROM pam_access_rules r
JOIN asset_tag_assignments ata ON ata.tag_id = r.tag_id
JOIN assets a ON a.id = ata.asset_id
WHERE r.tag_id IS NOT NULL
"""

_EXPANDED_GROUP_RULE_SELECT = """
SELECT
    r.id, a.id AS asset_id, a.hostname AS asset_hostname, a.ip_address AS asset_ip_address,
    a.status AS asset_status,
    r.allow_rdp, r.allow_ssh, r.allow_web, r.is_active, r.max_session_duration_mins, r.valid_until
FROM pam_access_rules r
JOIN server_group_members sgm ON sgm.server_group_id = r.server_group_id
JOIN assets a ON a.id = sgm.asset_id
WHERE r.server_group_id IS NOT NULL
"""


async def list_tag_rules_expanded_for_user(conn: asyncpg.Connection, user_id: UUID) -> list[asyncpg.Record]:
    """Faz 55 — `/my-access` için: bu kullanıcının etiket-hedefli
    kurallarını, etiketi TAŞIYAN her GERÇEK asset için ayrı bir satıra
    genişletir (bkz. `app/pam/service.py::list_authorized_assets_for_
    user`)."""
    return await conn.fetch(_EXPANDED_TAG_RULE_SELECT + " AND r.user_id = $1", user_id)


async def list_tag_rules_expanded_for_ad_groups(conn: asyncpg.Connection, ad_group_ids: list[UUID]) -> list[asyncpg.Record]:
    if not ad_group_ids:
        return []
    return await conn.fetch(_EXPANDED_TAG_RULE_SELECT + " AND r.ad_group_id = ANY($1::uuid[])", ad_group_ids)


async def list_group_rules_expanded_for_user(conn: asyncpg.Connection, user_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(_EXPANDED_GROUP_RULE_SELECT + " AND r.user_id = $1", user_id)


async def list_group_rules_expanded_for_ad_groups(conn: asyncpg.Connection, ad_group_ids: list[UUID]) -> list[asyncpg.Record]:
    if not ad_group_ids:
        return []
    return await conn.fetch(_EXPANDED_GROUP_RULE_SELECT + " AND r.ad_group_id = ANY($1::uuid[])", ad_group_ids)


async def list_rules(
    conn: asyncpg.Connection,
    *,
    search: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[asyncpg.Record]:
    """Faz 54 — `search` kullanıcı adı/AD grup adı/cihaz hostname-IP/
    kasa hesabı adı üzerinde (ILIKE, tek bir metin kutusu) arar. Faz 55
    — etiket/cihaz grubu adı da arama kapsamına eklendi."""
    conditions: list[str] = []
    params: list = []
    if search:
        params.append(f"%{search}%")
        idx = len(params)
        conditions.append(
            f"(u.username ILIKE ${idx} OR g.name ILIKE ${idx} OR a.hostname ILIKE ${idx} "
            f"OR a.ip_address::text ILIKE ${idx} OR c.name ILIKE ${idx} "
            f"OR tg.name ILIKE ${idx} OR sg.name ILIKE ${idx})"
        )
    query = _RULE_JOIN_SELECT
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY r.created_at ASC"
    if limit is not None:
        params.append(limit)
        query += f" LIMIT ${len(params)}"
    if offset is not None:
        params.append(offset)
        query += f" OFFSET ${len(params)}"
    return await conn.fetch(query, *params)


async def list_rules_for_user(conn: asyncpg.Connection, user_id: UUID) -> list[asyncpg.Record]:
    """Yalnızca DOĞRUDAN asset-hedefli kurallar — etiket/grup hedefli
    kurallar için bkz. `list_tag_rules_expanded_for_user`/`list_group_
    rules_expanded_for_user` (Faz 55, `/my-access`'in ayrı bir katmanı)."""
    return await conn.fetch(
        _RULE_JOIN_SELECT + " WHERE r.user_id = $1 AND r.asset_id IS NOT NULL ORDER BY r.created_at ASC", user_id
    )


async def list_rules_for_ad_groups(conn: asyncpg.Connection, ad_group_ids: list[UUID]) -> list[asyncpg.Record]:
    if not ad_group_ids:
        return []
    return await conn.fetch(
        _RULE_JOIN_SELECT + " WHERE r.ad_group_id = ANY($1::uuid[]) AND r.asset_id IS NOT NULL ORDER BY r.created_at ASC",
        ad_group_ids,
    )


async def update_rule(
    conn: asyncpg.Connection,
    rule_id: UUID,
    *,
    credential_id: UUID | None,
    allow_rdp: bool | None,
    allow_ssh: bool | None,
    allow_web: bool | None,
    is_active: bool | None,
    max_session_duration_mins: int | None,
    valid_until_set: bool,
    valid_until: datetime | None,
) -> asyncpg.Record | None:
    updated = await conn.fetchrow(
        """
        UPDATE pam_access_rules SET
            credential_id = COALESCE($2, credential_id),
            allow_rdp = COALESCE($3, allow_rdp),
            allow_ssh = COALESCE($4, allow_ssh),
            allow_web = COALESCE($5, allow_web),
            is_active = COALESCE($6, is_active),
            max_session_duration_mins = COALESCE($7, max_session_duration_mins),
            valid_until = CASE WHEN $8 THEN $9 ELSE valid_until END,
            updated_at = clock_timestamp()
        WHERE id = $1
        RETURNING id;
        """,
        rule_id,
        credential_id,
        allow_rdp,
        allow_ssh,
        allow_web,
        is_active,
        max_session_duration_mins,
        valid_until_set,
        valid_until,
    )
    if updated is None:
        return None
    return await conn.fetchrow(_RULE_JOIN_SELECT + " WHERE r.id = $1", rule_id)


async def delete_rule(conn: asyncpg.Connection, rule_id: UUID) -> bool:
    result = await conn.execute("DELETE FROM pam_access_rules WHERE id = $1", rule_id)
    return result != "DELETE 0"


# ---- pam_session_logs --------------------------------------------------

_SESSION_JOIN_SELECT = """
SELECT
    s.id, s.user_id, u.username, s.asset_id, a.hostname AS asset_hostname,
    a.ip_address AS asset_ip_address, s.credential_id, c.name AS credential_name,
    s.protocol, s.started_at, s.ended_at, s.end_reason, s.client_ip,
    s.recording_file_path, s.terminated_by
FROM pam_session_logs s
JOIN users u ON u.id = s.user_id
JOIN assets a ON a.id = s.asset_id
LEFT JOIN vault_credentials c ON c.id = s.credential_id
"""


async def insert_session_log(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    asset_id: UUID,
    credential_id: UUID | None,
    protocol: str,
    client_ip: str | None,
) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        INSERT INTO pam_session_logs (user_id, asset_id, credential_id, protocol, client_ip)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id;
        """,
        user_id,
        asset_id,
        credential_id,
        protocol,
        client_ip,
    )
    return await conn.fetchrow(_SESSION_JOIN_SELECT + " WHERE s.id = $1", row["id"])


async def close_session_log(conn: asyncpg.Connection, session_id: UUID, *, end_reason: str) -> None:
    """`terminated_by` burada ASLA yazılmaz/silinmez — Faz 50'de
    Admin'in "Oturumu Kapat" eylemi o kolonu `mark_termination_
    requested` ile AYRI ve ÖNCE yazar (bu WebSocket-kapanış çağrısı
    kimin sonlandırdığını bilmez, yalnızca `end_reason`'ı bilir)."""
    await conn.execute(
        "UPDATE pam_session_logs SET ended_at = clock_timestamp(), end_reason = $2 WHERE id = $1 AND ended_at IS NULL",
        session_id,
        end_reason,
    )


async def mark_termination_requested(conn: asyncpg.Connection, session_id: UUID, terminated_by: UUID) -> None:
    """Faz 50 — bir admin "Oturumu Kapat"a bastığında, WebSocket
    köprüsü kill event'i GÖRÜP gerçekten kapanmadan ÖNCE çağrılır —
    `terminated_by`'ı burada, admin'in KENDİ isteği sırasında (kimliği
    biliniyorken) yazar. `close_session_log` daha sonra `ended_at`/
    `end_reason`'ı yazarken bu kolona DOKUNMAZ."""
    await conn.execute("UPDATE pam_session_logs SET terminated_by = $2 WHERE id = $1", session_id, terminated_by)


async def set_session_recording_path(conn: asyncpg.Connection, session_id: UUID, path: str) -> None:
    await conn.execute("UPDATE pam_session_logs SET recording_file_path = $2 WHERE id = $1", session_id, path)


async def get_session_log(conn: asyncpg.Connection, session_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(_SESSION_JOIN_SELECT + " WHERE s.id = $1", session_id)


async def list_session_logs(
    conn: asyncpg.Connection,
    *,
    active_only: bool,
    search: str | None = None,
    protocol: str | None = None,
    reason: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[asyncpg.Record]:
    """Faz 54 — `search` kullanıcı adı/cihaz hostname-IP/istemci IP
    üzerinde (ILIKE, tek bir metin kutusu) arar; `protocol` ('rdp'/
    'ssh'), `reason` (`end_reason`'ın kendisi, ör. 'user_closed') tam
    eşleşme filtreler."""
    conditions: list[str] = []
    params: list = []
    if active_only:
        conditions.append("s.ended_at IS NULL")
    if search:
        params.append(f"%{search}%")
        idx = len(params)
        conditions.append(f"(u.username ILIKE ${idx} OR a.hostname ILIKE ${idx} OR a.ip_address::text ILIKE ${idx} OR s.client_ip ILIKE ${idx})")
    if protocol:
        params.append(protocol)
        conditions.append(f"s.protocol = ${len(params)}")
    if reason:
        params.append(reason)
        conditions.append(f"s.end_reason = ${len(params)}")
    query = _SESSION_JOIN_SELECT
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY s.started_at DESC"
    if limit is not None:
        params.append(limit)
        query += f" LIMIT ${len(params)}"
    if offset is not None:
        params.append(offset)
        query += f" OFFSET ${len(params)}"
    return await conn.fetch(query, *params)


# ---- pam_keystrokes (Faz 50 — yalnızca SSH) -----------------------------


async def insert_keystroke_chunk(conn: asyncpg.Connection, session_id: UUID, data: str) -> None:
    await conn.execute(
        "INSERT INTO pam_keystrokes (session_id, data) VALUES ($1, $2)",
        session_id,
        data,
    )


async def list_keystrokes(conn: asyncpg.Connection, session_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        "SELECT id, recorded_at, data FROM pam_keystrokes WHERE session_id = $1 ORDER BY recorded_at ASC",
        session_id,
    )


# ---- tags (Faz 55) -------------------------------------------------------


async def insert_tag(conn: asyncpg.Connection, *, name: str, created_by: UUID | None) -> asyncpg.Record:
    return await conn.fetchrow(
        "INSERT INTO tags (name, created_by) VALUES ($1, $2) RETURNING *;", name, created_by
    )


async def list_tags(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch("SELECT * FROM tags ORDER BY name ASC")


async def get_tag(conn: asyncpg.Connection, tag_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM tags WHERE id = $1", tag_id)


async def delete_tag(conn: asyncpg.Connection, tag_id: UUID) -> bool:
    result = await conn.execute("DELETE FROM tags WHERE id = $1", tag_id)
    return result != "DELETE 0"


async def tag_rule_count(conn: asyncpg.Connection, tag_id: UUID) -> int:
    """Silme öncesi kontrol için — bir etiket en az bir PAM kuralında
    KULLANILIYORSA `app/pam/service.py` sessiz kaskad YERİNE 409
    döner (mevcut `credential_in_use_count` ile AYNI ilke)."""
    return await conn.fetchval("SELECT count(*) FROM pam_access_rules WHERE tag_id = $1", tag_id)


async def assign_tag(conn: asyncpg.Connection, *, asset_id: UUID, tag_id: UUID) -> None:
    await conn.execute(
        "INSERT INTO asset_tag_assignments (asset_id, tag_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        asset_id,
        tag_id,
    )


async def unassign_tag(conn: asyncpg.Connection, *, asset_id: UUID, tag_id: UUID) -> None:
    await conn.execute("DELETE FROM asset_tag_assignments WHERE asset_id = $1 AND tag_id = $2", asset_id, tag_id)


async def list_assets_for_tag(conn: asyncpg.Connection, tag_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT a.id, a.hostname, a.ip_address FROM assets a
        JOIN asset_tag_assignments ata ON ata.asset_id = a.id
        WHERE ata.tag_id = $1
        ORDER BY a.hostname NULLS LAST, a.ip_address;
        """,
        tag_id,
    )


async def list_tags_for_asset(conn: asyncpg.Connection, asset_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT tg.id, tg.name FROM tags tg
        JOIN asset_tag_assignments ata ON ata.tag_id = tg.id
        WHERE ata.asset_id = $1
        ORDER BY tg.name;
        """,
        asset_id,
    )


# ---- server_groups (Faz 55) -----------------------------------------------


async def insert_server_group(
    conn: asyncpg.Connection, *, name: str, description: str | None, created_by: UUID | None
) -> asyncpg.Record:
    return await conn.fetchrow(
        "INSERT INTO server_groups (name, description, created_by) VALUES ($1, $2, $3) RETURNING *;",
        name,
        description,
        created_by,
    )


async def list_server_groups(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch("SELECT * FROM server_groups ORDER BY name ASC")


async def get_server_group(conn: asyncpg.Connection, server_group_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM server_groups WHERE id = $1", server_group_id)


async def update_server_group(
    conn: asyncpg.Connection, server_group_id: UUID, *, name: str | None, description: str | None, description_set: bool
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        UPDATE server_groups SET
            name = COALESCE($2, name),
            description = CASE WHEN $3 THEN $4 ELSE description END,
            updated_at = clock_timestamp()
        WHERE id = $1
        RETURNING *;
        """,
        server_group_id,
        name,
        description_set,
        description,
    )


async def delete_server_group(conn: asyncpg.Connection, server_group_id: UUID) -> bool:
    result = await conn.execute("DELETE FROM server_groups WHERE id = $1", server_group_id)
    return result != "DELETE 0"


async def server_group_rule_count(conn: asyncpg.Connection, server_group_id: UUID) -> int:
    return await conn.fetchval("SELECT count(*) FROM pam_access_rules WHERE server_group_id = $1", server_group_id)


async def add_group_member(conn: asyncpg.Connection, *, server_group_id: UUID, asset_id: UUID) -> None:
    await conn.execute(
        "INSERT INTO server_group_members (server_group_id, asset_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        server_group_id,
        asset_id,
    )


async def remove_group_member(conn: asyncpg.Connection, *, server_group_id: UUID, asset_id: UUID) -> None:
    await conn.execute(
        "DELETE FROM server_group_members WHERE server_group_id = $1 AND asset_id = $2", server_group_id, asset_id
    )


async def list_assets_for_group(conn: asyncpg.Connection, server_group_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT a.id, a.hostname, a.ip_address FROM assets a
        JOIN server_group_members sgm ON sgm.asset_id = a.id
        WHERE sgm.server_group_id = $1
        ORDER BY a.hostname NULLS LAST, a.ip_address;
        """,
        server_group_id,
    )


async def list_groups_for_asset(conn: asyncpg.Connection, asset_id: UUID) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT sg.id, sg.name FROM server_groups sg
        JOIN server_group_members sgm ON sgm.server_group_id = sg.id
        WHERE sgm.asset_id = $1
        ORDER BY sg.name;
        """,
        asset_id,
    )


# ---- pam_access_requests (Faz 56) ------------------------------------------

_ACCESS_REQUEST_JOIN_SELECT = """
SELECT
    req.id, req.requester_id, u.username AS requester_username,
    req.asset_id, a.hostname AS asset_hostname, a.ip_address AS asset_ip_address,
    req.tag_id, tg.name AS tag_name,
    req.server_group_id, sg.name AS server_group_name,
    req.protocol, req.business_reason, req.requested_duration_mins, req.status,
    req.reviewed_by, ru.username AS reviewed_by_username, req.reviewed_at, req.review_note,
    req.created_at
FROM pam_access_requests req
JOIN users u ON u.id = req.requester_id
LEFT JOIN users ru ON ru.id = req.reviewed_by
LEFT JOIN assets a ON a.id = req.asset_id
LEFT JOIN tags tg ON tg.id = req.tag_id
LEFT JOIN server_groups sg ON sg.id = req.server_group_id
"""


async def insert_access_request(
    conn: asyncpg.Connection,
    *,
    requester_id: UUID,
    asset_id: UUID | None,
    tag_id: UUID | None,
    server_group_id: UUID | None,
    protocol: str,
    business_reason: str,
    requested_duration_mins: int,
) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        INSERT INTO pam_access_requests (
            requester_id, asset_id, tag_id, server_group_id, protocol, business_reason, requested_duration_mins
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id;
        """,
        requester_id,
        asset_id,
        tag_id,
        server_group_id,
        protocol,
        business_reason,
        requested_duration_mins,
    )
    return await conn.fetchrow(_ACCESS_REQUEST_JOIN_SELECT + " WHERE req.id = $1", row["id"])


async def get_access_request(conn: asyncpg.Connection, request_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(_ACCESS_REQUEST_JOIN_SELECT + " WHERE req.id = $1", request_id)


async def list_access_requests(
    conn: asyncpg.Connection, *, status: str | None = None, requester_id: UUID | None = None
) -> list[asyncpg.Record]:
    conditions: list[str] = []
    params: list = []
    if status:
        params.append(status)
        conditions.append(f"req.status = ${len(params)}")
    if requester_id:
        params.append(requester_id)
        conditions.append(f"req.requester_id = ${len(params)}")
    query = _ACCESS_REQUEST_JOIN_SELECT
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY req.created_at DESC"
    return await conn.fetch(query, *params)


async def mark_access_request_reviewed(
    conn: asyncpg.Connection,
    request_id: UUID,
    *,
    status: str,
    reviewed_by: UUID,
    review_note: str | None,
) -> asyncpg.Record | None:
    """Yalnızca hâlâ `pending` olan bir talebi günceller — `WHERE
    status = 'pending'` sayesinde ZATEN incelenmiş bir talep iki kez
    onaylanamaz/reddedilemez (yarış durumuna karşı da güvenli, tek bir
    UPDATE ile atomic)."""
    updated = await conn.fetchrow(
        """
        UPDATE pam_access_requests SET
            status = $2,
            reviewed_by = $3,
            reviewed_at = clock_timestamp(),
            review_note = $4
        WHERE id = $1 AND status = 'pending'
        RETURNING id;
        """,
        request_id,
        status,
        reviewed_by,
        review_note,
    )
    if updated is None:
        return None
    return await conn.fetchrow(_ACCESS_REQUEST_JOIN_SELECT + " WHERE req.id = $1", request_id)


# ---- Faz 76 — pam_web_console_profiles (PAM Web Konsolu) ------------------


async def get_web_console_profile(conn: asyncpg.Connection, asset_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM pam_web_console_profiles WHERE asset_id = $1", asset_id)


async def upsert_web_console_profile(
    conn: asyncpg.Connection,
    *,
    asset_id: UUID,
    port: int,
    verify_ssl: bool,
    login_path: str,
    username_field: str,
    password_field: str,
    created_by: UUID | None,
) -> asyncpg.Record:
    return await conn.fetchrow(
        """
        INSERT INTO pam_web_console_profiles (
            asset_id, port, verify_ssl, login_path, username_field, password_field, created_by
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (asset_id) DO UPDATE SET
            port = EXCLUDED.port,
            verify_ssl = EXCLUDED.verify_ssl,
            login_path = EXCLUDED.login_path,
            username_field = EXCLUDED.username_field,
            password_field = EXCLUDED.password_field,
            updated_at = clock_timestamp()
        RETURNING *;
        """,
        asset_id,
        port,
        verify_ssl,
        login_path,
        username_field,
        password_field,
        created_by,
    )


async def delete_web_console_profile(conn: asyncpg.Connection, asset_id: UUID) -> bool:
    result = await conn.execute("DELETE FROM pam_web_console_profiles WHERE asset_id = $1", asset_id)
    return result != "DELETE 0"

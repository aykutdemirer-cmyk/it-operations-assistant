"""Faz 62/63 — `/api/tickets` (IT Helpdesk) için gerçek PostgreSQL'e
bağlı testler. Faz 63 — dinamik Departman/Kategori taksonomisi
(`is_active` soft-delete), `category_id`/`department_id` FK'leri."""

from datetime import datetime, timezone

import pytest

from app.auth.permissions import default_permissions_for_role
from app.auth.security import hash_password
from app.db.users import insert_user, set_permissions

pytestmark = pytest.mark.anyio


async def _seed_user(isolated_db, *, username, role="OPERATOR", ticket_role="REQUESTER", password="s3cret-pw!", permissions=None):
    row = await insert_user(
        isolated_db,
        username=username,
        password_hash=hash_password(password),
        role=role,
        full_name=None,
        ticket_role=ticket_role,
    )
    await set_permissions(
        isolated_db, row["id"], permissions if permissions is not None else default_permissions_for_role(role)
    )
    return row


async def _login(client, *, username, password="s3cret-pw!") -> str:
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _headers(client, isolated_db, username="helpdesk-user", ticket_role="TECHNICIAN", **seed_kw) -> dict:
    # Varsayılan olarak IT ekibi (TECHNICIAN) — çoğu test tüm biletleri
    # gören bir aktörle çalışır; REQUESTER senaryoları açıkça geçer.
    await _seed_user(isolated_db, username=username, ticket_role=ticket_role, **seed_kw)
    token = await _login(client, username=username)
    return {"Authorization": f"Bearer {token}"}


async def _first_category_id(client, headers) -> str:
    response = await client.get("/api/tickets/categories", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()[0]["id"]


async def _dep_ids(client, headers) -> list[str]:
    return [d["id"] for d in (await client.get("/api/tickets/departments", headers=headers)).json()]


async def _create_ticket(client, headers, *, category_id=None, **overrides) -> dict:
    payload = {
        "title": "Switch portu down",
        "description": "port 12 flapping",
        "category_id": category_id or await _first_category_id(client, headers),
        "priority": "HIGH",
    }
    payload.update(overrides)
    response = await client.post("/api/tickets", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---- Faz 63 — taksonomi ---------------------------------------------


async def test_seeded_departments_and_categories_are_listable(isolated_db, client):
    headers = await _headers(client, isolated_db)
    deps = (await client.get("/api/tickets/departments", headers=headers)).json()
    cats = (await client.get("/api/tickets/categories", headers=headers)).json()
    assert len(deps) >= 1 and all(d["is_active"] for d in deps)
    assert len(cats) >= 1 and all(c["is_active"] for c in cats)


async def test_admin_can_add_category_non_admin_cannot(isolated_db, client):
    admin = await _headers(client, isolated_db, username="tax-admin", role="ADMIN")
    op = await _headers(client, isolated_db, username="tax-op", role="OPERATOR")

    assert (await client.post("/api/tickets/categories", headers=op, json={"name": "VPN"})).status_code == 403

    created = await client.post("/api/tickets/categories", headers=admin, json={"name": "VPN"})
    assert created.status_code == 201 and created.json()["is_active"] is True
    assert (await client.post("/api/tickets/categories", headers=admin, json={"name": "VPN"})).status_code == 409


async def test_delete_is_soft_and_reactivates_on_readd(isolated_db, client):
    admin = await _headers(client, isolated_db, username="soft-admin", role="ADMIN")
    created = await client.post("/api/tickets/departments", headers=admin, json={"name": "Depo"})
    did = created.json()["id"]

    deleted = await client.delete(f"/api/tickets/departments/{did}", headers=admin)
    assert deleted.status_code == 200 and deleted.json()["is_active"] is False
    assert did not in await _dep_ids(client, admin)

    readd = await client.post("/api/tickets/departments", headers=admin, json={"name": "Depo"})
    assert readd.json()["id"] == did and readd.json()["is_active"] is True


async def test_delete_unknown_taxonomy_returns_404(isolated_db, client):
    admin = await _headers(client, isolated_db, username="u404-admin", role="ADMIN")
    r = await client.delete("/api/tickets/departments/00000000-0000-0000-0000-000000000000", headers=admin)
    assert r.status_code == 404


# ---- Faz 62/63 — bilet çekirdeği ----------------------------------


async def test_create_ticket_generates_number_sla_and_category(isolated_db, client):
    headers = await _headers(client, isolated_db)
    cats = (await client.get("/api/tickets/categories", headers=headers)).json()
    deps = (await client.get("/api/tickets/departments", headers=headers)).json()

    ticket = await _create_ticket(client, headers, category_id=cats[0]["id"], department_id=deps[0]["id"])

    year = datetime.now(timezone.utc).year
    assert ticket["ticket_number"].startswith(f"INC-{year}-")
    assert len(ticket["ticket_number"].rsplit("-", 1)[1]) >= 4
    assert ticket["category_name"] == cats[0]["name"]
    assert ticket["department_name"] == deps[0]["name"]
    assert ticket["sla_due_at"] is not None
    assert "related_device" not in ticket
    assert [c["event"] for c in ticket["comments"]] == ["created"]


async def test_create_ticket_rejects_invalid_or_inactive_category(isolated_db, client):
    admin = await _headers(client, isolated_db, username="inv-admin", role="ADMIN")

    bad = await client.post(
        "/api/tickets",
        headers=admin,
        json={"title": "x", "category_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert bad.status_code == 400

    created = await client.post("/api/tickets/categories", headers=admin, json={"name": "Geçici"})
    cid = created.json()["id"]
    await client.delete(f"/api/tickets/categories/{cid}", headers=admin)
    inactive = await client.post("/api/tickets", headers=admin, json={"title": "x", "category_id": cid})
    assert inactive.status_code == 400


async def test_list_filters_by_category_and_department_and_search(isolated_db, client):
    admin = await _headers(client, isolated_db, username="filt-admin", role="ADMIN")
    # İzole bir kategori + departman: paylaşımlı transaction'daki diğer
    # testlerin biletleri bu filtrelere düşmesin.
    cid = (await client.post("/api/tickets/categories", headers=admin, json={"name": "FiltKat-xyz"})).json()["id"]
    did = (await client.post("/api/tickets/departments", headers=admin, json={"name": "FiltDep-xyz"})).json()["id"]

    await _create_ticket(client, admin, title="Zeta-uniq-arıza", category_id=cid, department_id=did)

    by_cat = await client.get(f"/api/tickets?category_id={cid}", headers=admin)
    assert {t["title"] for t in by_cat.json()["tickets"]} == {"Zeta-uniq-arıza"}

    by_dep = await client.get(f"/api/tickets?department_id={did}", headers=admin)
    assert {t["title"] for t in by_dep.json()["tickets"]} == {"Zeta-uniq-arıza"}

    by_search = await client.get("/api/tickets?search=Zeta-uniq", headers=admin)
    assert {t["title"] for t in by_search.json()["tickets"]} == {"Zeta-uniq-arıza"}


async def test_ticket_number_increments(isolated_db, client):
    headers = await _headers(client, isolated_db)
    first = await _create_ticket(client, headers)
    second = await _create_ticket(client, headers)
    n1 = int(first["ticket_number"].rsplit("-", 1)[1])
    n2 = int(second["ticket_number"].rsplit("-", 1)[1])
    assert n2 == n1 + 1


async def test_plain_comment_and_status_transition(isolated_db, client):
    headers = await _headers(client, isolated_db)
    ticket = await _create_ticket(client, headers)

    commented = await client.post(
        f"/api/tickets/{ticket['id']}/comments", headers=headers, json={"body": "İnceliyorum"}
    )
    assert commented.status_code == 200
    assert "İnceliyorum" in [c["body"] for c in commented.json()["comments"]]

    resolved = await client.post(
        f"/api/tickets/{ticket['id']}/comments", headers=headers, json={"status": "RESOLVED"}
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["resolved_at"] is not None
    events = [c["event"] for c in resolved.json()["comments"]]
    assert "status_change" in events

    reopened = await client.post(
        f"/api/tickets/{ticket['id']}/comments", headers=headers, json={"status": "OPEN"}
    )
    assert reopened.json()["resolved_at"] is None


async def test_assignment_change_validates_user(isolated_db, client):
    headers = await _headers(client, isolated_db, username="assign-op")
    assignee = await _seed_user(isolated_db, username="assignee-1")
    ticket = await _create_ticket(client, headers)

    ok = await client.post(
        f"/api/tickets/{ticket['id']}/comments", headers=headers, json={"assigned_to": str(assignee["id"])}
    )
    assert ok.status_code == 200
    assert ok.json()["assigned_to_username"] == "assignee-1"

    bad = await client.post(
        f"/api/tickets/{ticket['id']}/comments",
        headers=headers,
        json={"assigned_to": "00000000-0000-0000-0000-000000000000"},
    )
    assert bad.status_code == 400


async def test_empty_comment_and_unknown_ticket(isolated_db, client):
    headers = await _headers(client, isolated_db)
    ticket = await _create_ticket(client, headers)
    assert (await client.post(f"/api/tickets/{ticket['id']}/comments", headers=headers, json={})).status_code == 422
    assert (await client.get("/api/tickets/00000000-0000-0000-0000-000000000000", headers=headers)).status_code == 404


async def test_tickets_require_permission(isolated_db, client):
    no_perm = await _headers(client, isolated_db, username="no-tickets", role="OPERATOR", permissions=["PAM_ACCESS"])
    assert (await client.get("/api/tickets", headers=no_perm)).status_code == 403


# ---- Faz 65 — basit REQUESTER RBAC + IT varsayılan departmanı --------


async def test_requester_lists_only_own_tickets(isolated_db, client):
    tech = await _headers(client, isolated_db, username="f65-tech", ticket_role="TECHNICIAN")
    await _create_ticket(client, tech, title="Tech'in bileti")

    req = await _headers(client, isolated_db, username="f65-req", ticket_role="REQUESTER")
    await _create_ticket(client, req, title="Requester'ın bileti")

    listed = await client.get("/api/tickets", headers=req)
    titles = {t["title"] for t in listed.json()["tickets"]}
    assert titles == {"Requester'ın bileti"}
    assert listed.json()["stats"]["open_tickets"] == 1  # sayaçlar da kapsamlı

    # TECHNICIAN her ikisini de görür.
    all_titles = {t["title"] for t in (await client.get("/api/tickets", headers=tech)).json()["tickets"]}
    assert {"Tech'in bileti", "Requester'ın bileti"} <= all_titles


async def test_requester_cannot_access_other_users_ticket_via_api(isolated_db, client):
    tech = await _headers(client, isolated_db, username="f65-tech2", ticket_role="TECHNICIAN")
    other = await _create_ticket(client, tech, title="Başkasının bileti")

    req = await _headers(client, isolated_db, username="f65-req2", ticket_role="REQUESTER")
    assert (await client.get(f"/api/tickets/{other['id']}", headers=req)).status_code == 403
    assert (
        await client.post(f"/api/tickets/{other['id']}/comments", headers=req, json={"body": "sızma denemesi"})
    ).status_code == 403


async def test_requester_can_work_on_own_ticket(isolated_db, client):
    req = await _headers(client, isolated_db, username="f65-req3", ticket_role="REQUESTER")
    mine = await _create_ticket(client, req, title="Kendi biletim")

    assert (await client.get(f"/api/tickets/{mine['id']}", headers=req)).status_code == 200
    commented = await client.post(f"/api/tickets/{mine['id']}/comments", headers=req, json={"body": "ek bilgi"})
    assert commented.status_code == 200
    assert "ek bilgi" in [c["body"] for c in commented.json()["comments"]]


async def test_new_ticket_defaults_to_it_department(isolated_db, client):
    headers = await _headers(client, isolated_db, username="f65-dept")
    ticket = await _create_ticket(client, headers)  # department_id verilmedi
    assert ticket["department_name"] == "IT"

    # Açıkça seçilen departmana saygı gösterilir.
    deps = (await client.get("/api/tickets/departments", headers=headers)).json()
    finans = next(d for d in deps if d["name"] == "Finans")
    explicit = await _create_ticket(client, headers, department_id=finans["id"])
    assert explicit["department_name"] == "Finans"


async def test_me_response_carries_ticket_role(isolated_db, client):
    req = await _headers(client, isolated_db, username="f65-me", ticket_role="REQUESTER")
    me = await client.get("/api/auth/me", headers=req)
    assert me.status_code == 200
    assert me.json()["ticket_role"] == "REQUESTER"


# ---- Faz 67 — SLA politikası + gecikmiş filtresi ------------------


async def test_sla_policy_returns_seed_values(isolated_db, client):
    headers = await _headers(client, isolated_db, username="f67-sla")
    policy = (await client.get("/api/tickets/sla-policy", headers=headers)).json()
    assert policy == {"CRITICAL": 4, "HIGH": 24, "MEDIUM": 72, "LOW": 168}


async def test_admin_updates_sla_policy_non_admin_forbidden(isolated_db, client):
    admin = await _headers(client, isolated_db, username="f67-admin", role="ADMIN")
    op = await _headers(client, isolated_db, username="f67-op", role="OPERATOR")

    assert (await client.put("/api/tickets/sla-policy/HIGH", headers=op, json={"sla_hours": 8})).status_code == 403

    resp = await client.put("/api/tickets/sla-policy/HIGH", headers=admin, json={"sla_hours": 8})
    assert resp.status_code == 200
    assert resp.json()["HIGH"] == 8

    assert (await client.put("/api/tickets/sla-policy/BOGUS", headers=admin, json={"sla_hours": 8})).status_code == 400


async def test_updated_sla_policy_applies_to_new_tickets(isolated_db, client):
    admin = await _headers(client, isolated_db, username="f67-apply", role="ADMIN")
    await client.put("/api/tickets/sla-policy/HIGH", headers=admin, json={"sla_hours": 1})

    ticket = await _create_ticket(client, admin, priority="HIGH")  # _create_ticket default priority HIGH
    created = datetime.fromisoformat(ticket["created_at"])
    due = datetime.fromisoformat(ticket["sla_due_at"])
    assert 0.9 <= (due - created).total_seconds() / 3600 <= 1.1


async def test_overdue_filter_returns_only_breached_open_tickets(isolated_db, client):
    admin = await _headers(client, isolated_db, username="f67-overdue", role="ADMIN")
    # SLA'yı çok kısa yap → yeni bilet anında "gecikmiş" olur (sla_due_at < now).
    await client.put("/api/tickets/sla-policy/HIGH", headers=admin, json={"sla_hours": 1})
    breached = await _create_ticket(client, admin, title="Gecikmiş bilet", priority="HIGH")
    # Uzun SLA → gecikmemiş.
    await client.put("/api/tickets/sla-policy/LOW", headers=admin, json={"sla_hours": 8760})
    await _create_ticket(client, admin, title="Zamanında bilet", priority="LOW")

    # `sla_hours=1` → sla_due_at = now + 1h, yani henüz geçmedi. Bunu
    # gerçekten "geçmiş" yapmak için bileti elle geriye alalım:
    await isolated_db.execute(
        "UPDATE tickets SET sla_due_at = now() - interval '2 hours' WHERE id = $1", breached["id"]
    )

    listed = await client.get("/api/tickets?overdue=true", headers=admin)
    titles = {t["title"] for t in listed.json()["tickets"]}
    assert "Gecikmiş bilet" in titles
    assert "Zamanında bilet" not in titles

    # Çözülünce gecikmiş listesinden düşer.
    await client.post(f"/api/tickets/{breached['id']}/comments", headers=admin, json={"status": "RESOLVED"})
    listed2 = await client.get("/api/tickets?overdue=true", headers=admin)
    assert "Gecikmiş bilet" not in {t["title"] for t in listed2.json()["tickets"]}


# ---- Faz 68 — salt-okunur metrikler ------------------------------


async def test_metrics_response_shape(isolated_db, client):
    # Not: `isolated_db` TÜM testler için TEK paylaşımlı transaction —
    # "boş sistem" garanti edilemez, bu yüzden yalnızca yapı doğrulanır.
    headers = await _headers(client, isolated_db, username="f68-shape")
    body = (await client.get("/api/tickets/metrics", headers=headers)).json()
    for key in ("total", "open_tickets", "closed_tickets", "overdue_open"):
        assert isinstance(body[key], int)
    assert body["avg_resolution_hours"] is None or isinstance(body["avg_resolution_hours"], (int, float))
    assert len(body["daily"]) == 30
    assert {"day", "created", "resolved"} == set(body["daily"][0])


async def test_metrics_aggregate_after_activity(isolated_db, client):
    admin = await _headers(client, isolated_db, username="f68-admin", role="ADMIN")
    cats = (await client.get("/api/tickets/categories", headers=admin)).json()
    before = (await client.get("/api/tickets/metrics", headers=admin)).json()

    a = await _create_ticket(client, admin, title="m1", category_id=cats[0]["id"], priority="HIGH")
    await _create_ticket(client, admin, title="m2", category_id=cats[1]["id"], priority="LOW")
    # a'yı SLA'sından ÖNCE çöz → uyum sayılır.
    await client.post(f"/api/tickets/{a['id']}/comments", headers=admin, json={"status": "RESOLVED"})

    after = (await client.get("/api/tickets/metrics", headers=admin)).json()
    assert after["total"] - before["total"] == 2
    assert after["open_tickets"] - before["open_tickets"] == 1
    assert after["closed_tickets"] - before["closed_tickets"] == 1
    assert after["by_priority"].get("HIGH", 0) - before["by_priority"].get("HIGH", 0) == 1
    assert after["by_priority"].get("LOW", 0) - before["by_priority"].get("LOW", 0) == 1
    assert after["avg_resolution_hours"] is not None
    assert after["sla_compliance_pct"] is not None and 0.0 <= after["sla_compliance_pct"] <= 100.0

    def _daily_sum(m, key):
        return sum(p[key] for p in m["daily"])

    assert _daily_sum(after, "created") - _daily_sum(before, "created") == 2
    assert _daily_sum(after, "resolved") - _daily_sum(before, "resolved") == 1


async def test_metrics_requester_scoped_to_own_tickets(isolated_db, client):
    tech = await _headers(client, isolated_db, username="f68-tech", ticket_role="TECHNICIAN")
    await _create_ticket(client, tech, title="tech's")

    req = await _headers(client, isolated_db, username="f68-req", ticket_role="REQUESTER")
    await _create_ticket(client, req, title="req's own")

    tech_total = (await client.get("/api/tickets/metrics", headers=tech)).json()["total"]
    req_total = (await client.get("/api/tickets/metrics", headers=req)).json()["total"]
    assert tech_total >= 2  # tüm biletler
    assert req_total == 1  # yalnızca kendi


# ---- Faz 69 — "bana atananlar" + CSV dışa aktarma ---------------


async def test_mine_filter_returns_only_tickets_assigned_to_actor(isolated_db, client):
    tech = await _headers(client, isolated_db, username="f69-tech", ticket_role="TECHNICIAN")
    other = await _seed_user(isolated_db, username="f69-other", ticket_role="TECHNICIAN")

    a = await _create_ticket(client, tech, title="atanmamış")
    b = await _create_ticket(client, tech, title="bana atanacak")
    await client.post(f"/api/tickets/{b['id']}/comments", headers=tech, json={"assigned_to": str(other["id"])})
    # a'yı actor'a ata (assignable-users listesi tech'i içermeyebilir → önce b'yi geri al)
    me = (await client.get("/api/auth/me", headers=tech)).json()
    await client.post(f"/api/tickets/{a['id']}/comments", headers=tech, json={"assigned_to": me["id"]})

    listed = await client.get("/api/tickets?mine=true", headers=tech)
    titles = {t["title"] for t in listed.json()["tickets"]}
    assert titles == {"atanmamış"}


async def test_csv_export_has_header_and_rows(isolated_db, client):
    headers = await _headers(client, isolated_db, username="f69-csv")
    await _create_ticket(client, headers, title="CSV satırı")

    resp = await client.get("/api/tickets/export.csv", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert 'attachment; filename="tickets.csv"' in resp.headers["content-disposition"]
    lines = resp.text.strip().splitlines()
    assert lines[0].startswith("ticket_number,title,priority,status")
    assert any("CSV satırı" in ln for ln in lines[1:])


async def test_csv_export_requires_permission(isolated_db, client):
    no_perm = await _headers(client, isolated_db, username="f69-noperm", role="OPERATOR", permissions=["PAM_ACCESS"])
    assert (await client.get("/api/tickets/export.csv", headers=no_perm)).status_code == 403


# ---- Gizli IT İç Notları (is_internal) --------------------------------


async def test_technician_internal_note_hidden_from_requester(isolated_db, client, monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr("app.tickets.service.email_service.notify", lambda kind, **kw: sent.append(kind))

    tech = await _headers(client, isolated_db, username="int-tech", ticket_role="TECHNICIAN")
    req = await _headers(client, isolated_db, username="int-req", ticket_role="REQUESTER")
    await isolated_db.execute("UPDATE users SET email = $1 WHERE username = $2", "req1@example.com", "int-req")
    ticket = await _create_ticket(client, req, title="Gizli not testi")

    internal = await client.post(
        f"/api/tickets/{ticket['id']}/comments",
        headers=tech,
        json={"body": "Sunucuda RAID hatası var, kullanıcıya söylemeden değiştiriyoruz", "is_internal": True},
    )
    assert internal.status_code == 200
    tech_bodies = [c["body"] for c in internal.json()["comments"]]
    assert "Sunucuda RAID hatası var, kullanıcıya söylemeden değiştiriyoruz" in tech_bodies
    # İç not REQUESTER'a e-posta olarak da gitmemeli (yalnızca görünür
    # yanıt "new_reply" tetikler).
    assert "new_reply" not in sent

    seen_by_requester = await client.get(f"/api/tickets/{ticket['id']}", headers=req)
    assert seen_by_requester.status_code == 200
    req_bodies = [c["body"] for c in seen_by_requester.json()["comments"]]
    assert "Sunucuda RAID hatası var, kullanıcıya söylemeden değiştiriyoruz" not in req_bodies


async def test_requester_cannot_mark_own_comment_internal(isolated_db, client):
    req = await _headers(client, isolated_db, username="int-req2", ticket_role="REQUESTER")
    ticket = await _create_ticket(client, req, title="Requester iç not denemesi")

    resp = await client.post(
        f"/api/tickets/{ticket['id']}/comments",
        headers=req,
        json={"body": "bunu gizli yapmayı deniyorum", "is_internal": True},
    )
    assert resp.status_code == 200
    comment = next(c for c in resp.json()["comments"] if c["body"] == "bunu gizli yapmayı deniyorum")
    assert comment["is_internal"] is False


async def test_visible_reply_still_notifies_requester(isolated_db, client, monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr("app.tickets.service.email_service.notify", lambda kind, **kw: sent.append(kind))

    tech = await _headers(client, isolated_db, username="int-tech2", ticket_role="TECHNICIAN")
    req = await _headers(client, isolated_db, username="int-req3", ticket_role="REQUESTER")
    await isolated_db.execute("UPDATE users SET email = $1 WHERE username = $2", "req3@example.com", "int-req3")
    ticket = await _create_ticket(client, req, title="Görünür yanıt testi")

    resp = await client.post(
        f"/api/tickets/{ticket['id']}/comments",
        headers=tech,
        json={"body": "Sorun çözüldü, kontrol edin"},
    )
    assert resp.status_code == 200
    assert "new_reply" in sent

"""`assets` şema SQL'inin doğru yüklendiğini doğrulayan saf (DB'siz)
testler. `infra/postgres/init.sql` gerçek bir dosya olduğundan bu testler
mock database kullanmaz — gerçek dosya I/O'sunu test eder."""

from app.db.assets import CREATE_ASSETS_TABLE_SQL


def test_schema_sql_contains_assets_table_definition():
    assert "CREATE TABLE IF NOT EXISTS assets" in CREATE_ASSETS_TABLE_SQL


def test_schema_sql_contains_expected_columns():
    for column in (
        "ip_address",
        "hostname",
        "mac_address",
        "vendor",
        "device_type",
        "confidence",
        "status",
        "open_ports",
        "evidence",
        "last_seen",
        "created_at",
        "updated_at",
    ):
        assert column in CREATE_ASSETS_TABLE_SQL


def test_schema_sql_declares_ip_address_as_unique():
    assert "UNIQUE" in CREATE_ASSETS_TABLE_SQL


def test_schema_sql_declares_required_indexes():
    assert "idx_assets_mac_address" in CREATE_ASSETS_TABLE_SQL
    assert "idx_assets_device_type" in CREATE_ASSETS_TABLE_SQL
    assert "idx_assets_status" in CREATE_ASSETS_TABLE_SQL
    assert "idx_assets_last_seen" in CREATE_ASSETS_TABLE_SQL

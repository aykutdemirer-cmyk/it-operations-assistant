"""`scans` şema SQL'inin doğru yüklendiğini doğrulayan saf (DB'siz)
testler — `test_assets_schema.py` ile aynı desen."""

from app.db.scans import CREATE_SCANS_TABLE_SQL


def test_schema_sql_contains_scans_table_definition():
    assert "CREATE TABLE IF NOT EXISTS scans" in CREATE_SCANS_TABLE_SQL


def test_schema_sql_contains_expected_columns():
    for column in (
        "cidr",
        "started_at",
        "completed_at",
        "duration_ms",
        "hosts_scanned",
        "hosts_discovered",
        "open_ports",
        "status",
    ):
        assert column in CREATE_SCANS_TABLE_SQL


def test_schema_sql_declares_required_indexes():
    assert "idx_scans_started_at" in CREATE_SCANS_TABLE_SQL
    assert "idx_scans_status" in CREATE_SCANS_TABLE_SQL


def test_schema_sql_does_not_declare_created_or_updated_at_for_scans():
    # scans tablosu bilinçli olarak created_at/updated_at icermez (gereksiz
    # alan). assets tablosunun kendi created_at/updated_at'i olduğu için
    # bu assertion, scans blogunu spesifik olarak kontrol eder.
    scans_block_start = CREATE_SCANS_TABLE_SQL.index("CREATE TABLE IF NOT EXISTS scans")
    scans_block = CREATE_SCANS_TABLE_SQL[scans_block_start:]
    scans_block_end = scans_block.index(");")
    scans_definition = scans_block[:scans_block_end]

    assert "created_at" not in scans_definition
    assert "updated_at" not in scans_definition

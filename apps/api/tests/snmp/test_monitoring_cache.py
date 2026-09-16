"""`app/snmp/monitoring_cache.py` için birim testleri — gerçek bir SNMP
ağ isteği/DB bağlantısı hiç kullanılmaz, yalnızca süreç-içi önbellek
mantığı test edilir. Global (module-level) state olduğu için her testte
`reset()` ile temizlenir — testler arası sızıntı YOK."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.snmp import monitoring_cache
from app.snmp.models import InterfaceInfo, SNMPPollResult, SystemInfo
from app.snmp.poller import PollBatchResult


@pytest.fixture(autouse=True)
def _reset_cache():
    monitoring_cache.reset()
    yield
    monitoring_cache.reset()


def _now():
    return datetime.now(timezone.utc)


def _batch(*results: SNMPPollResult) -> PollBatchResult:
    now = _now()
    return PollBatchResult(
        started_at=now,
        completed_at=now,
        duration_ms=12.5,
        total=len(results),
        polled=sum(1 for r in results if r.status != "not_configured"),
        not_configured=sum(1 for r in results if r.status == "not_configured"),
        results=list(results),
    )


def test_starts_empty():
    assert monitoring_cache.get_latest_batch() is None
    assert monitoring_cache.get_poll_log() == []
    assert monitoring_cache.get_bandwidth_history() == []


def test_record_batch_sets_latest_batch():
    result = SNMPPollResult(asset_id=uuid4(), polled_at=_now(), status="not_configured")
    batch = _batch(result)

    monitoring_cache.record_batch(batch)

    assert monitoring_cache.get_latest_batch() == batch


def test_record_batch_appends_one_log_entry_per_result_newest_first():
    r1 = SNMPPollResult(asset_id=uuid4(), polled_at=_now(), status="success", duration_ms=5.0)
    r2 = SNMPPollResult(asset_id=uuid4(), polled_at=_now(), status="not_configured")
    monitoring_cache.record_batch(_batch(r1, r2))

    log = monitoring_cache.get_poll_log()

    assert len(log) == 2
    assert {entry.asset_id for entry in log} == {r1.asset_id, r2.asset_id}


def test_log_entry_oid_count_is_derived_from_real_structure():
    system = SystemInfo(sys_name="core-sw-01")
    iface = InterfaceInfo(if_index=1, if_name="Gi0/1")
    result = SNMPPollResult(
        asset_id=uuid4(), polled_at=_now(), status="success", system=system, interfaces=[iface]
    )
    monitoring_cache.record_batch(_batch(result))

    entry = monitoring_cache.get_poll_log()[0]

    from app.snmp.oid_map import INTERFACE_OIDS, SYSTEM_OIDS

    assert entry.oid_count == len(SYSTEM_OIDS) + len(INTERFACE_OIDS)


def test_log_entry_oid_count_is_zero_when_not_configured():
    result = SNMPPollResult(asset_id=uuid4(), polled_at=_now(), status="not_configured")
    monitoring_cache.record_batch(_batch(result))

    assert monitoring_cache.get_poll_log()[0].oid_count == 0


def test_get_poll_log_respects_limit():
    results = [SNMPPollResult(asset_id=uuid4(), polled_at=_now(), status="not_configured") for _ in range(5)]
    monitoring_cache.record_batch(_batch(*results))

    assert len(monitoring_cache.get_poll_log(limit=2)) == 2


def test_bandwidth_history_sums_real_bps_across_interfaces_and_assets():
    iface_a = InterfaceInfo(if_index=1, if_in_bps=1000.0, if_out_bps=500.0)
    iface_b = InterfaceInfo(if_index=2, if_in_bps=2000.0, if_out_bps=1500.0)
    result_1 = SNMPPollResult(
        asset_id=uuid4(), polled_at=_now(), status="success", interfaces=[iface_a]
    )
    result_2 = SNMPPollResult(
        asset_id=uuid4(), polled_at=_now(), status="success", interfaces=[iface_b]
    )
    monitoring_cache.record_batch(_batch(result_1, result_2))

    sample = monitoring_cache.get_bandwidth_history()[0]

    assert sample.total_in_bps == 3000.0
    assert sample.total_out_bps == 2000.0


def test_bandwidth_history_is_none_when_no_interface_has_real_bps():
    # ilk poll (henüz baseline yok) -> if_in_bps/if_out_bps her zaman None
    iface = InterfaceInfo(if_index=1, if_in_bps=None, if_out_bps=None)
    result = SNMPPollResult(
        asset_id=uuid4(), polled_at=_now(), status="success", interfaces=[iface]
    )
    monitoring_cache.record_batch(_batch(result))

    sample = monitoring_cache.get_bandwidth_history()[0]

    assert sample.total_in_bps is None
    assert sample.total_out_bps is None


def test_multiple_batches_accumulate_bandwidth_history_as_a_time_series():
    result = SNMPPollResult(asset_id=uuid4(), polled_at=_now(), status="not_configured")
    monitoring_cache.record_batch(_batch(result))
    monitoring_cache.record_batch(_batch(result))
    monitoring_cache.record_batch(_batch(result))

    assert len(monitoring_cache.get_bandwidth_history()) == 3


def test_reset_clears_all_state():
    result = SNMPPollResult(asset_id=uuid4(), polled_at=_now(), status="not_configured")
    monitoring_cache.record_batch(_batch(result))

    monitoring_cache.reset()

    assert monitoring_cache.get_latest_batch() is None
    assert monitoring_cache.get_poll_log() == []
    assert monitoring_cache.get_bandwidth_history() == []

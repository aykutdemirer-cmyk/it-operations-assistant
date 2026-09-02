from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.snmp.models import InterfaceInfo, SNMPPollResult, SystemInfo


def test_system_info_all_fields_optional():
    info = SystemInfo()
    assert info.sys_name is None
    assert info.sys_descr is None
    assert info.sys_object_id is None
    assert info.sys_uptime_ticks is None


def test_interface_info_requires_if_index_only():
    iface = InterfaceInfo(if_index=1)
    assert iface.if_index == 1
    assert iface.if_name is None
    assert iface.if_oper_status is None


def test_interface_info_rejects_invalid_status():
    with pytest.raises(ValidationError):
        InterfaceInfo(if_index=1, if_oper_status="banana")


def test_poll_result_not_configured_has_no_fabricated_data():
    result = SNMPPollResult(
        asset_id=uuid4(),
        polled_at=datetime.now(timezone.utc),
        status="not_configured",
    )
    assert result.system is None
    assert result.interfaces == []
    assert result.status == "not_configured"


def test_poll_result_success_can_carry_real_system_and_interfaces():
    result = SNMPPollResult(
        asset_id=uuid4(),
        polled_at=datetime.now(timezone.utc),
        status="success",
        system=SystemInfo(sys_name="core-sw-01"),
        interfaces=[InterfaceInfo(if_index=1, if_name="Gi0/1", if_oper_status="up")],
    )
    assert result.system.sys_name == "core-sw-01"
    assert result.interfaces[0].if_oper_status == "up"

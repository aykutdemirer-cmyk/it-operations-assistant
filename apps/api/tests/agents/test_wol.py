"""`app/agents/wol.py` için testler — gerçek bir UDP paketi ASLA ağa
gönderilmez, `socket.socket` mock'lanır."""

from unittest.mock import MagicMock, patch

import pytest

from app.agents.wol import InvalidMacAddressError, build_magic_packet, send_magic_packet


def test_build_magic_packet_starts_with_six_ff_bytes():
    packet = build_magic_packet("00:50:56:92:6D:A3")
    assert packet[:6] == b"\xff" * 6


def test_build_magic_packet_repeats_mac_sixteen_times():
    packet = build_magic_packet("00:50:56:92:6D:A3")
    expected_mac = bytes.fromhex("005056926DA3")
    assert packet[6:] == expected_mac * 16
    assert len(packet) == 6 + 16 * 6


def test_build_magic_packet_accepts_dash_separated_mac():
    packet = build_magic_packet("00-50-56-92-6D-A3")
    assert packet[6:12] == bytes.fromhex("005056926DA3")


def test_build_magic_packet_rejects_invalid_mac():
    with pytest.raises(InvalidMacAddressError):
        build_magic_packet("not-a-mac-address")


def test_send_magic_packet_enables_broadcast_and_sends_udp():
    fake_socket = MagicMock()
    with patch("app.agents.wol.socket.socket", return_value=fake_socket):
        send_magic_packet("00:50:56:92:6D:A3", broadcast_ip="10.0.213.255")

    fake_socket.setsockopt.assert_called_once()
    fake_socket.sendto.assert_called_once()
    args = fake_socket.sendto.call_args.args
    assert args[1] == ("10.0.213.255", 9)
    fake_socket.close.assert_called_once()


def test_send_magic_packet_closes_socket_even_on_failure():
    fake_socket = MagicMock()
    fake_socket.sendto.side_effect = OSError("network unreachable")
    with patch("app.agents.wol.socket.socket", return_value=fake_socket):
        with pytest.raises(OSError):
            send_magic_packet("00:50:56:92:6D:A3")

    fake_socket.close.assert_called_once()


def test_send_magic_packet_never_sends_when_mac_invalid():
    with patch("app.agents.wol.socket.socket") as mock_socket_cls:
        with pytest.raises(InvalidMacAddressError):
            send_magic_packet("garbage")

    mock_socket_cls.assert_not_called()

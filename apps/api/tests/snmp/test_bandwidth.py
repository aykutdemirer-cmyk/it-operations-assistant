from app.snmp.bandwidth import CounterSample, calculate_bandwidth_bps


def test_calculates_bps_for_normal_increasing_counters():
    previous = CounterSample(octets=1_000_000, timestamp_ms=0)
    current = CounterSample(octets=2_000_000, timestamp_ms=1000)

    bps = calculate_bandwidth_bps(previous, current)

    assert bps == 8_000_000  # (2_000_000 - 1_000_000) bytes * 8 / 1s


def test_returns_none_when_time_did_not_advance():
    previous = CounterSample(octets=1000, timestamp_ms=5000)
    current = CounterSample(octets=2000, timestamp_ms=5000)

    assert calculate_bandwidth_bps(previous, current) is None


def test_returns_none_when_timestamps_go_backwards():
    previous = CounterSample(octets=1000, timestamp_ms=5000)
    current = CounterSample(octets=2000, timestamp_ms=4000)

    assert calculate_bandwidth_bps(previous, current) is None


def test_returns_none_on_counter_rollover_never_fabricates_a_rate():
    # counter 32-bit taştı / ajan yeniden başladı — negatif delta.
    previous = CounterSample(octets=4_294_000_000, timestamp_ms=0)
    current = CounterSample(octets=1000, timestamp_ms=1000)

    assert calculate_bandwidth_bps(previous, current) is None


def test_zero_delta_octets_yields_zero_bps_not_none():
    previous = CounterSample(octets=5000, timestamp_ms=0)
    current = CounterSample(octets=5000, timestamp_ms=1000)

    assert calculate_bandwidth_bps(previous, current) == 0

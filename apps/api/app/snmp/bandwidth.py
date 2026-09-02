"""İki ardışık SNMP interface counter örneğinden (`ifInOctets`/
`ifOutOctets`) gerçek bant genişliği (bps) hesabı.

Bu modül saf bir hesaplama katmanıdır — hiçbir ağ/DB erişimi yapmaz,
girdi olarak yalnızca gerçekten poll edilmiş iki örnek alır. Henüz canlı
bir SNMP ajanı olmadığından şu an hiçbir yerden çağrılmıyor; Faz 4.16'nın
poll döngüsü gerçek arka arkaya iki örnek biriktirmeye başladığında
kullanılacak sözleşmeyi şimdiden sabitler."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CounterSample:
    octets: int
    timestamp_ms: float


def calculate_bandwidth_bps(previous: CounterSample, current: CounterSample) -> float | None:
    """`previous` -> `current` arasındaki ortalama bit/saniye hızını
    döner.

    `None` dönen durumlar (hiçbiri uydurma bir sayıyla doldurulmaz):
    - `current.timestamp_ms <= previous.timestamp_ms`: zaman ilerlemedi,
      geçerli bir hız hesaplanamaz.
    - `current.octets < previous.octets`: counter geriye gitti. Bu, ya
      ajan yeniden başladı ya da 32-bit `ifInOctets`/`ifOutOctets`
      counter'ı taştı (rollover) demektir. İki durumu ayırt etmenin
      güvenilir bir yolu yok (taşma miktarı bilinmiyor) — bu yüzden
      tahmin üretmek yerine `None` döndürülür; çağıran taraf bunu "veri
      yok" olarak göstermeli, asla 0 veya negatif bir hız değil."""
    delta_time_ms = current.timestamp_ms - previous.timestamp_ms
    if delta_time_ms <= 0:
        return None

    delta_octets = current.octets - previous.octets
    if delta_octets < 0:
        return None

    delta_seconds = delta_time_ms / 1000
    delta_bits = delta_octets * 8
    return delta_bits / delta_seconds

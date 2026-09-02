import type { Asset } from "@/lib/api";

export type InfrastructureHealth = {
  total: number;
  online: number;
  offline: number;
  unknown: number;
  onlinePercent: number | null;
  offlinePercent: number | null;
  unknownPercent: number | null;
  availabilityPercent: number | null;
};

function percentOf(count: number, total: number): number | null {
  if (total === 0) return null;
  return Math.round((count / total) * 1000) / 10;
}

/**
 * Gerçek `assets` verisinden UP/DOWN/UNKNOWN dağılımını ve genel
 * erişilebilirlik (availability) yüzdesini hesaplar. `status` şu anki veri
 * modelinde her zaman "up" veya "down" olsa da, "unknown" kategorisi
 * ileride farklı bir değer gelirse (ör. henüz sınıflandırılmamış bir
 * durum) diye savunmacı biçimde hesaplanır — asla sabit/varsayılan bir
 * değer üretmez, yalnızca gerçek `assets` listesinden türetir.
 *
 * `total === 0` ise yüzdeler `null` döner — "0%" gibi yanıltıcı bir
 * sağlık skoru göstermek yerine çağıran taraf "No data available"
 * göstermelidir.
 */
export function computeInfrastructureHealth(assets: Asset[]): InfrastructureHealth {
  const total = assets.length;
  const online = assets.filter((asset) => asset.status === "up").length;
  const offline = assets.filter((asset) => asset.status === "down").length;
  const unknown = total - online - offline;

  return {
    total,
    online,
    offline,
    unknown,
    onlinePercent: percentOf(online, total),
    offlinePercent: percentOf(offline, total),
    unknownPercent: percentOf(unknown, total),
    availabilityPercent: percentOf(online, total),
  };
}

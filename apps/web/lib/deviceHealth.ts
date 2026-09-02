import type { Alert } from "@/lib/alerts";
import type { Asset } from "@/lib/api";

export type DeviceHealthCounts = {
  critical: number;
  warning: number;
  healthy: number;
  unmonitored: number;
  total: number;
};

/**
 * Cihaz başına UP/DOWN/WARNING sınıflandırması — yalnızca gerçek
 * verilerden: `critical` = discovery'nin `down` bulduğu cihazlar,
 * `warning` = `up` olup en az bir WARNING seviyeli alert'i olan
 * cihazlar (bkz. `lib/alerts.ts`), `healthy` = geri kalan `up`
 * cihazlar. `unmonitored` her zaman toplam asset sayısına eşittir —
 * henüz hiçbir asset için SNMP yapılandırılmadığından (bkz.
 * `apps/api/app/snmp/`), bu sayı uydurulmaz, gerçek mimari durumu
 * yansıtır.
 */
export function computeDeviceHealth(
  assets: Asset[],
  alerts: Alert[],
): DeviceHealthCounts {
  const warningAssetIds = new Set(
    alerts.filter((alert) => alert.severity === "WARNING").map((a) => a.assetId),
  );

  let critical = 0;
  let warning = 0;
  let healthy = 0;

  for (const asset of assets) {
    if (asset.status === "down") {
      critical += 1;
      continue;
    }
    if (warningAssetIds.has(asset.id)) {
      warning += 1;
    } else {
      healthy += 1;
    }
  }

  return {
    critical,
    warning,
    healthy,
    unmonitored: assets.length,
    total: assets.length,
  };
}

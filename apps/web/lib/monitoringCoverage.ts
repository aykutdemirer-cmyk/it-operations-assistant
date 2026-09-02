import type { Asset } from "@/lib/api";

export type MonitoringCoverage = {
  total: number;
  snmpEnabled: number;
  snmpDisabled: number;
  unreachable: number;
};

/**
 * SNMP kapsama özeti. `snmpEnabled`, çağıran tarafın (bkz.
 * `MonitoringCoverage.tsx`) gerçek `asset_snmp_profiles` ilişkisinden
 * (`GET /api/snmp/profiles`'ın `assigned_asset_count` alanlarının
 * toplamı) getirdiği `snmpAssignedCount` parametresine dayanır (Faz
 * 29.5) — hiçbir zaman bu modül İÇİNDE uydurulmaz. Parametre
 * verilmezse (geriye dönük uyumluluk) 0 kabul edilir. `Math.min` ile
 * `total`'a sınırlanır — silinmiş bir asset'in ataması henüz
 * temizlenmemişse (teorik olarak imkansız, FK CASCADE korur) bile
 * `snmpEnabled` gerçek asset sayısını aşamaz.
 */
export function computeMonitoringCoverage(
  assets: Asset[],
  snmpAssignedCount = 0,
): MonitoringCoverage {
  const total = assets.length;
  const snmpEnabled = Math.min(snmpAssignedCount, total);
  return {
    total,
    snmpEnabled,
    snmpDisabled: total - snmpEnabled,
    unreachable: assets.filter((asset) => asset.status === "down").length,
  };
}

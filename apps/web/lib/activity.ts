import type { Asset, Scan } from "@/lib/api";

export type ActivityType =
  | "asset_discovered"
  | "asset_updated"
  | "scan_completed"
  | "scan_failed";

export type ActivityItem = {
  id: string;
  type: ActivityType;
  detail: string;
  timestamp: string;
};

/**
 * Gerçek `assets` ve `scans` verisinden türetilen bir aktivite akışı
 * oluşturur. Veritabanında ayrı bir "event log" tablosu olmadığı için
 * uydurma event üretilmez — yalnızca mevcut verinin kendisinden
 * (created_at/updated_at karşılaştırması, scan sonuç durumu)
 * çıkarılabilen gerçek olaylar listelenir.
 *
 * `label` alanı kasıtlı olarak burada YOK — bu saf hesaplama katmanı
 * dile bağlı bir metin taşımaz; UI (`RecentActivity.tsx`) `type`'ı
 * kendi çeviri sözlüğüyle eşler (bkz. `lib/i18n/`).
 */
export function buildActivityFeed(assets: Asset[], scans: Scan[]): ActivityItem[] {
  const items: ActivityItem[] = [];

  for (const asset of assets) {
    // created_at ve updated_at ilk eklemede birebir aynı zaman
    // damgasıdır (bkz. backend upsert_asset) — bu, satırın o zamandan
    // beri hiç güncellenmediğini, yani "yeni keşfedildiğini" gösterir.
    const isNewlyDiscovered = asset.created_at === asset.updated_at;
    items.push({
      id: `asset-${asset.id}`,
      type: isNewlyDiscovered ? "asset_discovered" : "asset_updated",
      detail: asset.hostname ?? asset.ip_address,
      timestamp: asset.updated_at,
    });
  }

  for (const scan of scans) {
    if (!scan.completed_at) continue;
    if (scan.status !== "completed" && scan.status !== "failed") continue;

    const type: ActivityType =
      scan.status === "completed" ? "scan_completed" : "scan_failed";
    items.push({
      id: `scan-${scan.id}`,
      type,
      detail: scan.cidr,
      timestamp: scan.completed_at,
    });
  }

  return items.sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  );
}

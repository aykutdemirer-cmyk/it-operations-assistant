/**
 * `lib/alerts.ts`'in kullandığı tüm sayısal eşikler — hiçbiri kural
 * gövdesinde hardcode edilmez (Faz 26). Çağıran taraf `computeAlerts`'e
 * `Partial<AlertThresholds>` geçerek istediği eşiği ezebilir;
 * geçmezse `DEFAULT_ALERT_THRESHOLDS` kullanılır.
 */
export type AlertThresholds = {
  /** WARNING seviyesi high_latency eşiği (ms). */
  latencyWarningMs: number;
  /** CRITICAL seviyesi latency eşiği (ms) — latencyWarningMs'ten büyük olmalı. */
  latencyCriticalMs: number;
  /** WARNING seviyesi interface kullanım oranı eşiği (%). */
  interfaceUtilizationWarningPercent: number;
  /** CRITICAL seviyesi interface kullanım oranı eşiği (%). */
  interfaceUtilizationCriticalPercent: number;
  /** high_bandwidth kuralının mutlak bps eşiği. */
  highBandwidthBps: number;
};

export const DEFAULT_ALERT_THRESHOLDS: AlertThresholds = {
  latencyWarningMs: 100,
  latencyCriticalMs: 500,
  interfaceUtilizationWarningPercent: 70,
  interfaceUtilizationCriticalPercent: 90,
  highBandwidthBps: 800_000_000, // 800 Mbps
};

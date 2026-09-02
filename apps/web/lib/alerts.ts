import type { translations } from "@/lib/i18n/translations";
import { classifyPortRisk } from "@/lib/portRisk";
import type { Asset, SnmpInterfaceInfo, SnmpPollResult } from "@/lib/api";
import { DEFAULT_ALERT_THRESHOLDS, type AlertThresholds } from "@/lib/alertThresholds";

export type AlertSeverity = "INFO" | "WARNING" | "CRITICAL";

/**
 * `device_unreachable`/`snmp_poll_failure`/`interface_down`/
 * `interface_error`/`high_bandwidth`/`high_utilization` yalnızca
 * gerçek SNMP verisi (`options.monitoring`, bkz. `computeAlerts`)
 * geçildiğinde tetiklenebilir — geçilmezse (bugün frontend'in hiçbir
 * çağrı noktası henüz geçmiyor, bkz. Faz 24/26) bu kurallar hiç
 * çalışmaz, asla uydurma bir alert üretilmez.
 */
export type AlertRule =
  | "device_down"
  | "high_latency"
  | "interface_down"
  | "interface_error"
  | "snmp_poll_failure"
  | "device_unreachable"
  | "high_bandwidth"
  | "high_utilization"
  | "high_risk_port";

export type Alert = {
  id: string;
  rule: AlertRule;
  severity: AlertSeverity;
  assetId: string;
  assetLabel: string;
  message: string;
  detectedAt: string;
};

const SEVERITY_ORDER: Record<AlertSeverity, number> = {
  CRITICAL: 0,
  WARNING: 1,
  INFO: 2,
};

function assetLabel(asset: Asset): string {
  return asset.hostname ?? asset.ip_address;
}

function interfaceLabel(iface: SnmpInterfaceInfo): string {
  return iface.if_name ?? iface.if_descr ?? `#${iface.if_index}`;
}

type AlertMessages = (typeof translations)["tr"]["alertMessages"];

export type ComputeAlertsOptions = {
  /**
   * asset id -> en son gerçek `SNMPPollResult` (bkz. `GET /api/
   * monitoring`, Faz 24). Verilmezse tüm SNMP-tabanlı kurallar
   * atlanır — hiçbir alert uydurulmaz.
   */
  monitoring?: Record<string, SnmpPollResult>;
  /** Verilmeyen alanlar `DEFAULT_ALERT_THRESHOLDS`'tan gelir. */
  thresholds?: Partial<AlertThresholds>;
};

/**
 * Gerçek `assets` (+ opsiyonel gerçek SNMP `monitoring`) verisinden
 * alert üretir — hiçbir alert uydurulmaz; bir kural için gerçek veri
 * yoksa o kural için hiç alert üretilmez. `messages`, mesaj metnini
 * seçili dilde üretmek için çağıran taraftan (bkz. `useLocale().t.
 * alertMessages`) enjekte edilir — bu saf hesaplama katmanı doğrudan
 * bir dile bağımlı değildir.
 */
export function computeAlerts(
  assets: Asset[],
  messages: AlertMessages,
  options: ComputeAlertsOptions = {},
): Alert[] {
  const thresholds: AlertThresholds = { ...DEFAULT_ALERT_THRESHOLDS, ...options.thresholds };
  const alerts: Alert[] = [];

  for (const asset of assets) {
    const label = assetLabel(asset);

    if (asset.status === "down") {
      alerts.push({
        id: `device_down:${asset.id}`,
        rule: "device_down",
        severity: "CRITICAL",
        assetId: asset.id,
        assetLabel: label,
        message: messages.deviceDown(label),
        detectedAt: asset.last_seen,
      });
    }

    if (asset.latency_ms != null) {
      if (asset.latency_ms > thresholds.latencyCriticalMs) {
        alerts.push({
          id: `high_latency:${asset.id}`,
          rule: "high_latency",
          severity: "CRITICAL",
          assetId: asset.id,
          assetLabel: label,
          message: messages.highLatency(label, asset.latency_ms, thresholds.latencyCriticalMs),
          detectedAt: asset.last_seen,
        });
      } else if (asset.latency_ms > thresholds.latencyWarningMs) {
        alerts.push({
          id: `high_latency:${asset.id}`,
          rule: "high_latency",
          severity: "WARNING",
          assetId: asset.id,
          assetLabel: label,
          message: messages.highLatency(label, asset.latency_ms, thresholds.latencyWarningMs),
          detectedAt: asset.last_seen,
        });
      }
    }

    for (const port of asset.open_ports) {
      if (classifyPortRisk(port.port) === "HIGH") {
        alerts.push({
          id: `high_risk_port:${asset.id}:${port.port}`,
          rule: "high_risk_port",
          severity: "WARNING",
          assetId: asset.id,
          assetLabel: label,
          message: messages.highRiskPort(label, port.port),
          detectedAt: asset.last_seen,
        });
      }
    }

    const snmp = options.monitoring?.[asset.id];
    if (snmp) {
      alerts.push(...computeSnmpAlerts(asset, label, snmp, messages, thresholds));
    }
  }

  return alerts.sort((a, b) => {
    const severityDiff = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
    if (severityDiff !== 0) return severityDiff;
    return new Date(b.detectedAt).getTime() - new Date(a.detectedAt).getTime();
  });
}

function computeSnmpAlerts(
  asset: Asset,
  label: string,
  snmp: SnmpPollResult,
  messages: AlertMessages,
  thresholds: AlertThresholds,
): Alert[] {
  const alerts: Alert[] = [];
  const detectedAt = snmp.polled_at;

  if (snmp.status === "unreachable") {
    alerts.push({
      id: `device_unreachable:${asset.id}`,
      rule: "device_unreachable",
      severity: "CRITICAL",
      assetId: asset.id,
      assetLabel: label,
      message: messages.deviceUnreachable(label),
      detectedAt,
    });
  } else if (snmp.status === "timeout" || snmp.status === "authentication_failed") {
    alerts.push({
      id: `snmp_poll_failure:${asset.id}`,
      rule: "snmp_poll_failure",
      severity: "WARNING",
      assetId: asset.id,
      assetLabel: label,
      message: messages.snmpPollFailure(label, snmp.status),
      detectedAt,
    });
  }

  for (const iface of snmp.interfaces) {
    const ifaceLabel = interfaceLabel(iface);

    if (iface.if_admin_status === "up" && iface.if_oper_status === "down") {
      alerts.push({
        id: `interface_down:${asset.id}:${iface.if_index}`,
        rule: "interface_down",
        severity: "WARNING",
        assetId: asset.id,
        assetLabel: label,
        message: messages.interfaceDown(label, ifaceLabel),
        detectedAt,
      });
    }

    const errorCount = (iface.if_in_errors ?? 0) + (iface.if_out_errors ?? 0);
    if (errorCount > 0) {
      alerts.push({
        id: `interface_error:${asset.id}:${iface.if_index}`,
        rule: "interface_error",
        severity: "WARNING",
        assetId: asset.id,
        assetLabel: label,
        message: messages.interfaceError(label, ifaceLabel, errorCount),
        detectedAt,
      });
    }

    for (const [direction, bps] of [
      ["in", iface.if_in_bps] as const,
      ["out", iface.if_out_bps] as const,
    ]) {
      if (bps != null && bps > thresholds.highBandwidthBps) {
        alerts.push({
          id: `high_bandwidth:${asset.id}:${iface.if_index}:${direction}`,
          rule: "high_bandwidth",
          severity: "WARNING",
          assetId: asset.id,
          assetLabel: label,
          message: messages.highBandwidth(label, ifaceLabel, Math.round(bps / 1_000_000)),
          detectedAt,
        });
      }
    }

    if (iface.if_speed_bps && iface.if_speed_bps > 0) {
      for (const [direction, bps] of [
        ["in", iface.if_in_bps] as const,
        ["out", iface.if_out_bps] as const,
      ]) {
        if (bps == null) continue;
        const percent = (bps / iface.if_speed_bps) * 100;
        const severity: AlertSeverity | null =
          percent >= thresholds.interfaceUtilizationCriticalPercent
            ? "CRITICAL"
            : percent >= thresholds.interfaceUtilizationWarningPercent
              ? "WARNING"
              : null;
        if (severity) {
          alerts.push({
            id: `high_utilization:${asset.id}:${iface.if_index}:${direction}`,
            rule: "high_utilization",
            severity,
            assetId: asset.id,
            assetLabel: label,
            message: messages.highUtilization(label, ifaceLabel, Math.round(percent)),
            detectedAt,
          });
        }
      }
    }
  }

  return alerts;
}

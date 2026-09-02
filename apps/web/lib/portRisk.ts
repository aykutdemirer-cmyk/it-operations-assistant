import type { Asset } from "@/lib/api";

export type PortRisk = "LOW" | "MEDIUM" | "HIGH";

/**
 * Tek doğruluk kaynağı — port risk sınıflandırması. UI içinde dağınık
 * hard-code edilmesin diye tüm port→risk kararları burada toplanır.
 *
 * HIGH: uzaktan yönetim/dosya paylaşım protokolleri, güçlü kimlik
 * doğrulaması olmadan genellikle riskli kabul edilir (SMB/RDP/WinRM/
 * Telnet/FTP/RPC/NetBIOS).
 * MEDIUM: veritabanı/uzak-erişim servisleri — genelde ağ içine kapalı
 * tutulması beklenir ama HIGH kadar acil değildir.
 * LOW: diğer her port (standart web/uygulama portları dahil).
 */
const HIGH_RISK_PORTS = new Set([21, 23, 135, 139, 445, 3389, 5985, 5986]);
const MEDIUM_RISK_PORTS = new Set([22, 25, 110, 143, 1433, 3306, 5432, 6379, 27017]);

export function classifyPortRisk(port: number): PortRisk {
  if (HIGH_RISK_PORTS.has(port)) return "HIGH";
  if (MEDIUM_RISK_PORTS.has(port)) return "MEDIUM";
  return "LOW";
}

export type PortSummary = {
  port: number;
  deviceCount: number;
  risk: PortRisk;
};

/**
 * `assets.open_ports` üzerinden gerçek port kullanımını port bazında
 * gruplar. Yalnızca gerçekten en az bir cihazda görülen portlar
 * döner (sabit/varsayımsal bir port listesi kullanılmaz).
 */
export function aggregateOpenPorts(assets: Asset[]): PortSummary[] {
  const deviceCountByPort = new Map<number, number>();

  for (const asset of assets) {
    const portsOnThisAsset = new Set(asset.open_ports.map((p) => p.port));
    for (const port of portsOnThisAsset) {
      deviceCountByPort.set(port, (deviceCountByPort.get(port) ?? 0) + 1);
    }
  }

  return Array.from(deviceCountByPort.entries())
    .map(([port, deviceCount]) => ({
      port,
      deviceCount,
      risk: classifyPortRisk(port),
    }))
    .sort((a, b) => b.deviceCount - a.deviceCount || a.port - b.port);
}

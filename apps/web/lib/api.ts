const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type HealthResponse = {
  status: string;
};

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_URL}/api/health`);

  if (!response.ok) {
    throw new Error(`Backend health check failed: ${response.status}`);
  }

  return response.json();
}

export type PortResult = {
  port: number;
  status: "open" | "closed" | "timeout";
  latency_ms: number | null;
};

export type DeviceType =
  | "firewall"
  | "router"
  | "switch"
  | "server"
  | "workstation"
  | "printer"
  | "access_point"
  | "camera"
  | "nas"
  | "network_device"
  | "unknown";

export type PingResult = {
  ip: string;
  status: "up" | "down";
  latency_ms: number | null;
  mac_address: string | null;
  vendor: string | null;
  hostname: string | null;
  open_ports: PortResult[];
  device_type: DeviceType;
  confidence: "high" | "medium" | "low";
  evidence: string[];
};

export type ScanResult = {
  cidr: string;
  total_hosts: number;
  alive_hosts: number;
  hosts: PingResult[];
};

export async function scanNetwork(cidr: string): Promise<ScanResult> {
  const response = await fetch(`${API_URL}/api/discovery/icmp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cidr }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Tarama başarısız: ${response.status}`);
  }

  return response.json();
}

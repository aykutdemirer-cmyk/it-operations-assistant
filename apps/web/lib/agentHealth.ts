import type { AgentSummary } from "@/lib/api";

export type AgentHealth = {
  total: number;
  online: number;
  offline: number;
  unknown: number;
  linkedToAsset: number;
};

/**
 * Dashboard'ın "Agent Health" widget'ı için saf hesaplama (Faz 30).
 * Girdi her zaman gerçek `GET /api/agents` sonucu — hiçbir sayı
 * uydurulmaz, agent hiç yoksa hepsi 0 kalır.
 */
export function computeAgentHealth(agents: AgentSummary[]): AgentHealth {
  return {
    total: agents.length,
    online: agents.filter((a) => a.status === "online").length,
    offline: agents.filter((a) => a.status === "offline").length,
    unknown: agents.filter((a) => a.status === "unknown").length,
    linkedToAsset: agents.filter((a) => a.asset_id != null).length,
  };
}

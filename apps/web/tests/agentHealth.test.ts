import { describe, expect, it } from "vitest";

import { computeAgentHealth } from "@/lib/agentHealth";
import type { AgentSummary } from "@/lib/api";

function agent(status: AgentSummary["status"], assetId: string | null = null): AgentSummary {
  return {
    id: crypto.randomUUID(),
    hostname: "h",
    os: "linux",
    os_version: null,
    agent_version: "1.0.0",
    local_ip: null,
    asset_id: assetId,
    status,
    registered_at: "2026-01-01T00:00:00Z",
    last_heartbeat_at: null,
    update_available: false,
    latest_available_version: null,
  };
}

describe("computeAgentHealth", () => {
  it("returns zeros for an empty fleet", () => {
    expect(computeAgentHealth([])).toEqual({ total: 0, online: 0, offline: 0, unknown: 0, linkedToAsset: 0 });
  });

  it("counts each real status independently", () => {
    const agents = [agent("online"), agent("online"), agent("offline"), agent("unknown")];

    const health = computeAgentHealth(agents);

    expect(health.total).toBe(4);
    expect(health.online).toBe(2);
    expect(health.offline).toBe(1);
    expect(health.unknown).toBe(1);
  });

  it("counts agents linked to an asset", () => {
    const agents = [agent("online", "asset-1"), agent("online", null), agent("offline", "asset-2")];

    const health = computeAgentHealth(agents);

    expect(health.linkedToAsset).toBe(2);
  });
});

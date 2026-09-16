import { Suspense } from "react";

import { NetworkTopology } from "@/components/NetworkTopology";
import { RequirePermission } from "@/components/RequirePermission";

export default function TopologyPage() {
  return (
    <RequirePermission permission="TOPOLOGY_VIEW">
      <Suspense fallback={null}>
        <NetworkTopology />
      </Suspense>
    </RequirePermission>
  );
}

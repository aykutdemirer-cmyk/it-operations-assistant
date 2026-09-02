import { Suspense } from "react";

import { NetworkTopology } from "@/components/NetworkTopology";

export default function TopologyPage() {
  return (
    <Suspense fallback={null}>
      <NetworkTopology />
    </Suspense>
  );
}

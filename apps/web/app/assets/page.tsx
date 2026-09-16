import { Suspense } from "react";

import { AssetInventory } from "@/components/AssetInventory";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "../shared.module.css";

export default function AssetsPage() {
  return (
    <RequirePermission permission="ASSETS_VIEW">
      <main className={styles.page}>
        <Suspense fallback={null}>
          <AssetInventory />
        </Suspense>
      </main>
    </RequirePermission>
  );
}

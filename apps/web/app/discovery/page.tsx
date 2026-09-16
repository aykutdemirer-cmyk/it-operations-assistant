import { NetworkDiscovery } from "@/components/NetworkDiscovery";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "../shared.module.css";

export default function DiscoveryPage() {
  return (
    <RequirePermission permission="DISCOVERY_VIEW">
      <main className={styles.page}>
        <NetworkDiscovery />
      </main>
    </RequirePermission>
  );
}

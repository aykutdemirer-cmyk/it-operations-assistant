import { MonitoringOverview } from "@/components/MonitoringOverview";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "../shared.module.css";

export default function MonitoringPage() {
  return (
    <RequirePermission permission="MONITORING_VIEW">
      <main className={styles.page}>
        <MonitoringOverview />
      </main>
    </RequirePermission>
  );
}

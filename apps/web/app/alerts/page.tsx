import { AlertsList } from "@/components/AlertsList";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "../shared.module.css";

export default function AlertsPage() {
  return (
    <RequirePermission permission="ALERTS_VIEW">
      <main className={styles.page}>
        <AlertsList />
      </main>
    </RequirePermission>
  );
}

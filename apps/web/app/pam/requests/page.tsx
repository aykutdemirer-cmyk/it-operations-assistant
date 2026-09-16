import { PamAccessRequestsPanel } from "@/components/PamAccessRequestsPanel";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "../../shared.module.css";

export default function PamAccessRequestsPage() {
  return (
    <main className={styles.page}>
      <RequirePermission permission="PAM_ADMIN">
        <PamAccessRequestsPanel />
      </RequirePermission>
    </main>
  );
}

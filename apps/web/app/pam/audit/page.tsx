import { PamAuditPanel } from "@/components/PamAuditPanel";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "../../shared.module.css";

export default function PamAuditPage() {
  return (
    <main className={styles.page}>
      <RequirePermission permission="PAM_ADMIN">
        <PamAuditPanel />
      </RequirePermission>
    </main>
  );
}

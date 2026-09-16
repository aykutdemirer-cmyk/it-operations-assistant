import { PamRulesPanel } from "@/components/PamRulesPanel";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "../../shared.module.css";

export default function PamRulesPage() {
  return (
    <main className={styles.page}>
      <RequirePermission permission="PAM_ADMIN">
        <PamRulesPanel />
      </RequirePermission>
    </main>
  );
}

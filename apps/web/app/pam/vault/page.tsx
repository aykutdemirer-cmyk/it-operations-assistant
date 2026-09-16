import { PamVaultPanel } from "@/components/PamVaultPanel";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "../../shared.module.css";

export default function PamVaultPage() {
  return (
    <main className={styles.page}>
      <RequirePermission permission="PAM_ADMIN">
        <PamVaultPanel />
      </RequirePermission>
    </main>
  );
}

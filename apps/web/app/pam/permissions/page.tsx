import { PermissionMatrixPanel } from "@/components/PermissionMatrixPanel";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "../../shared.module.css";

export default function PermissionMatrixPage() {
  return (
    <main className={styles.page}>
      <RequirePermission permission="PAM_ADMIN">
        <PermissionMatrixPanel />
      </RequirePermission>
    </main>
  );
}

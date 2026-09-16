import { PamUsersPanel } from "@/components/PamUsersPanel";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "../../shared.module.css";

export default function PamUsersPage() {
  return (
    <main className={styles.page}>
      <RequirePermission permission="PAM_ADMIN">
        <PamUsersPanel />
      </RequirePermission>
    </main>
  );
}

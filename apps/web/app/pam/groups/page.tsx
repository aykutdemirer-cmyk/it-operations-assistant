import { PamServerGroupsPanel } from "@/components/PamServerGroupsPanel";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "../../shared.module.css";

export default function PamServerGroupsPage() {
  return (
    <main className={styles.page}>
      <RequirePermission permission="PAM_ADMIN">
        <PamServerGroupsPanel />
      </RequirePermission>
    </main>
  );
}

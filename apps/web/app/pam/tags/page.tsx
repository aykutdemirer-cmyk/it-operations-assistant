import { PamTagsPanel } from "@/components/PamTagsPanel";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "../../shared.module.css";

export default function PamTagsPage() {
  return (
    <main className={styles.page}>
      <RequirePermission permission="PAM_ADMIN">
        <PamTagsPanel />
      </RequirePermission>
    </main>
  );
}

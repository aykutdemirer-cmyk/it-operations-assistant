import { RecentScans } from "@/components/RecentScans";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "../shared.module.css";

const FULL_HISTORY_LIMIT = 500;

export default function ScansPage() {
  return (
    <RequirePermission permission="SCANS_VIEW">
      <main className={styles.page}>
        <RecentScans limit={FULL_HISTORY_LIMIT} />
      </main>
    </RequirePermission>
  );
}

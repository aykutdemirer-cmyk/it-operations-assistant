import { RequirePermission } from "@/components/RequirePermission";
import { TicketsPanel } from "@/components/TicketsPanel";
import styles from "../shared.module.css";

export default function TicketsPage() {
  return (
    <main className={styles.page}>
      <RequirePermission permission="TICKETS_VIEW">
        <TicketsPanel />
      </RequirePermission>
    </main>
  );
}

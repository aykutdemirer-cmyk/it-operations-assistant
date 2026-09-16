import { AgentsList } from "@/components/AgentsList";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "../shared.module.css";

export default function AgentsPage() {
  return (
    <RequirePermission permission="AGENTS_VIEW">
      <main className={styles.page}>
        <AgentsList />
      </main>
    </RequirePermission>
  );
}

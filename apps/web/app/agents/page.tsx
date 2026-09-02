import { AgentsList } from "@/components/AgentsList";
import styles from "../shared.module.css";

export default function AgentsPage() {
  return (
    <main className={styles.page}>
      <AgentsList />
    </main>
  );
}

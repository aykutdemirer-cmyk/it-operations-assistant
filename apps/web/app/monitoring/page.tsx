import { MonitoringOverview } from "@/components/MonitoringOverview";
import styles from "../shared.module.css";

export default function MonitoringPage() {
  return (
    <main className={styles.page}>
      <MonitoringOverview />
    </main>
  );
}

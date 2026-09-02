import { AlertsList } from "@/components/AlertsList";
import styles from "../shared.module.css";

export default function AlertsPage() {
  return (
    <main className={styles.page}>
      <AlertsList />
    </main>
  );
}

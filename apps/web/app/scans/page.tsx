import { RecentScans } from "@/components/RecentScans";
import styles from "../shared.module.css";

const FULL_HISTORY_LIMIT = 500;

export default function ScansPage() {
  return (
    <main className={styles.page}>
      <RecentScans limit={FULL_HISTORY_LIMIT} />
    </main>
  );
}

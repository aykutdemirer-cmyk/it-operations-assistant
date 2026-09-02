import { SettingsPanel } from "@/components/SettingsPanel";
import styles from "../shared.module.css";

export default function SettingsPage() {
  return (
    <main className={styles.page}>
      <SettingsPanel />
    </main>
  );
}

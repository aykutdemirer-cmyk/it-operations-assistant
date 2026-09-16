import { RequirePermission } from "@/components/RequirePermission";
import { SettingsPanel } from "@/components/SettingsPanel";
import styles from "../shared.module.css";

export default function SettingsPage() {
  return (
    <RequirePermission permission="SETTINGS_VIEW">
      <main className={styles.page}>
        <SettingsPanel />
      </main>
    </RequirePermission>
  );
}

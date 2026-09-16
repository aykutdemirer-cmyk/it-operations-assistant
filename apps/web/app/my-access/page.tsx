import { MyAccessPanel } from "@/components/MyAccessPanel";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "../shared.module.css";

export default function MyAccessPage() {
  return (
    <main className={styles.page}>
      <RequirePermission permission="PAM_ACCESS">
        <MyAccessPanel />
      </RequirePermission>
    </main>
  );
}

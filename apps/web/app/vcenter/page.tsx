import { RequirePermission } from "@/components/RequirePermission";
import { VCenterPanel } from "@/components/vcenter/VCenterPanel";
import styles from "../shared.module.css";

export default function VCenterPage() {
  return (
    <main className={styles.page}>
      <RequirePermission permission="VCENTER_VIEW">
        <VCenterPanel />
      </RequirePermission>
    </main>
  );
}

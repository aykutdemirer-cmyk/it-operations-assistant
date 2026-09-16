import { DashboardGrid } from "@/components/dashboard/DashboardGrid";
import { RequirePermission } from "@/components/RequirePermission";
import styles from "./page.module.css";

// Faz 59 — statik 2-kolon layout, `react-grid-layout` tabanlı
// sürüklenebilir/özelleştirilebilir grid'e dönüştü (`DashboardGrid`).
// Widget component'lerinin hiçbiri değişmedi; görünüm seçici + düzen
// kaydet/sıfırla + widget ekle araç çubuğu eklendi. `DashboardData
// Provider` (layout.tsx) aynen sarmaya devam ediyor.
export default function Home() {
  return (
    <RequirePermission permission="DASHBOARD_VIEW">
      <main className={styles.main}>
        <DashboardGrid />
      </main>
    </RequirePermission>
  );
}

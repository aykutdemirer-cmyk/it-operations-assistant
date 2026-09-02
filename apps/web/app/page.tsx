import { AgentHealthSummary } from "@/components/AgentHealthSummary";
import { AlertsPanel } from "@/components/AlertsPanel";
import { DashboardSummary } from "@/components/DashboardSummary";
import { DeviceDistribution } from "@/components/DeviceDistribution";
import { DeviceHealthSummary } from "@/components/DeviceHealthSummary";
import { InfrastructureHealth } from "@/components/InfrastructureHealth";
import { MonitoringCoverage } from "@/components/MonitoringCoverage";
import { NetworkPerformance } from "@/components/NetworkPerformance";
import { OpenPortsOverview } from "@/components/OpenPortsOverview";
import { RecentActivity } from "@/components/RecentActivity";
import { RecentScans } from "@/components/RecentScans";
import styles from "./page.module.css";

export default function Home() {
  return (
    <main className={styles.main}>
      <DashboardSummary />

      {/* Faz 36 — Dashboard 2 ana kolona ayrıldı: sol = altyapı ve cihaz
          dağılım grafikleri, sağ = güvenlik uyarıları ve canlı olay akışı. */}
      <div className={styles.mainGrid}>
        <div className={styles.column}>
          <InfrastructureHealth />
          <DeviceHealthSummary />
          <div className={styles.analyticsRow}>
            <DeviceDistribution />
            <OpenPortsOverview />
          </div>
        </div>

        <div className={styles.column}>
          <AlertsPanel />
          <RecentActivity />
        </div>
      </div>

      <div className={styles.secondary}>
        <AgentHealthSummary />
        <MonitoringCoverage />
        <NetworkPerformance />
        <RecentScans />
      </div>
    </main>
  );
}

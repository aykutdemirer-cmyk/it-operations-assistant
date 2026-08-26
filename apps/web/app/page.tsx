import { BackendStatus } from "@/components/BackendStatus";
import { NetworkDiscovery } from "@/components/NetworkDiscovery";
import styles from "./page.module.css";

export default function Home() {
  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <h1>IT Operations Assistant</h1>
        <BackendStatus />
        <NetworkDiscovery />
      </main>
    </div>
  );
}

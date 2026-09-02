import { NetworkDiscovery } from "@/components/NetworkDiscovery";
import styles from "../shared.module.css";

export default function DiscoveryPage() {
  return (
    <main className={styles.page}>
      <NetworkDiscovery />
    </main>
  );
}

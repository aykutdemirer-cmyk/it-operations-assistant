import { AssetInventory } from "@/components/AssetInventory";
import styles from "../shared.module.css";

export default function AssetsPage() {
  return (
    <main className={styles.page}>
      <AssetInventory />
    </main>
  );
}

"use client";

import { useParams } from "next/navigation";

import { AgentDetailView } from "@/components/AgentDetailView";
import styles from "../../shared.module.css";

export default function AgentDetailPage() {
  const params = useParams<{ id: string }>();
  return (
    <main className={styles.page}>
      <AgentDetailView agentId={params.id} />
    </main>
  );
}

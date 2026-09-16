"use client";

import { useParams } from "next/navigation";
import Link from "next/link";

import { RequirePermission } from "@/components/RequirePermission";
import { SshTerminal } from "@/components/SshTerminal";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "../../../shared.module.css";

export default function SshTerminalPage() {
  const { t } = useLocale();
  const params = useParams<{ agentId: string }>();

  return (
    <RequirePermission permission="AGENTS_VIEW">
      <main className={styles.page}>
        <Link href={`/agents/${params.agentId}`}>{t.sshTerminal.backToAgent}</Link>
        <SshTerminal agentId={params.agentId} />
      </main>
    </RequirePermission>
  );
}

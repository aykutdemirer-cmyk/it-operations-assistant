"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { PamSshTerminal } from "@/components/PamSshTerminal";
import { RequirePermission } from "@/components/RequirePermission";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "../../../shared.module.css";

export default function PamSshTerminalPage() {
  const { t } = useLocale();
  const params = useParams<{ assetId: string }>();

  return (
    <RequirePermission permission="PAM_ACCESS">
      <main className={styles.page}>
        <Link href="/my-access">{t.pam.myAccessTitle}</Link>
        <PamSshTerminal assetId={params.assetId} />
      </main>
    </RequirePermission>
  );
}

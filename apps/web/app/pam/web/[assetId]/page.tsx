"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { PamWebConsoleViewer } from "@/components/PamWebConsoleViewer";
import { RequirePermission } from "@/components/RequirePermission";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "../../../shared.module.css";

export default function PamWebConsolePage() {
  const { t } = useLocale();
  const params = useParams<{ assetId: string }>();

  return (
    <RequirePermission permission="PAM_ACCESS">
      <main className={styles.page}>
        <Link href="/my-access">{t.pam.myAccessTitle}</Link>
        <PamWebConsoleViewer assetId={params.assetId} />
      </main>
    </RequirePermission>
  );
}

"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { RequirePermission } from "@/components/RequirePermission";
import { UserDeviceAccessPanel } from "@/components/UserDeviceAccessPanel";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "../../../shared.module.css";

export default function PamUserDeviceAccessPage() {
  const { t } = useLocale();
  const params = useParams<{ userId: string }>();

  return (
    <main className={styles.page}>
      <RequirePermission permission="PAM_ADMIN">
        <Link href="/pam/users">{t.pam.backToUsers}</Link>
        <UserDeviceAccessPanel userId={params.userId} />
      </RequirePermission>
    </main>
  );
}

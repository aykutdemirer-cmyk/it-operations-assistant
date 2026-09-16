"use client";

import { AuthStatus } from "@/components/AuthStatus";
import { BackendStatus } from "@/components/BackendStatus";
import { GlobalSearch } from "@/components/GlobalSearch";
import { LanguageToggle } from "@/components/LanguageToggle";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./TopHeader.module.css";

export function TopHeader() {
  const { t } = useLocale();

  return (
    <header className={styles.topNav}>
      <div>
        <h1 className={styles.title}>IT Operations Assistant</h1>
        <p className={styles.subtitle}>{t.common.appSubtitle}</p>
      </div>
      <div className={styles.searchWrap}>
        <GlobalSearch />
      </div>
      <div className={styles.right}>
        <ThemeSwitcher />
        <LanguageToggle />
        <BackendStatus />
        <AuthStatus />
      </div>
    </header>
  );
}

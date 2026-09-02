"use client";

import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./LanguageToggle.module.css";

export function LanguageToggle() {
  const { locale, setLocale } = useLocale();

  return (
    <div className={styles.group} role="group" aria-label="TR / EN">
      <button
        type="button"
        className={`${styles.option} ${locale === "tr" ? styles.optionActive : ""}`}
        aria-pressed={locale === "tr"}
        onClick={() => setLocale("tr")}
      >
        TR
      </button>
      <span className={styles.divider} aria-hidden="true">
        |
      </span>
      <button
        type="button"
        className={`${styles.option} ${locale === "en" ? styles.optionActive : ""}`}
        aria-pressed={locale === "en"}
        onClick={() => setLocale("en")}
      >
        EN
      </button>
    </div>
  );
}

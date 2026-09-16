"use client";

import { useLocale } from "@/lib/i18n/LocaleProvider";
import { ALL_THEMES, useTheme, type Theme } from "@/lib/theme/ThemeProvider";
import styles from "./ThemeSwitcher.module.css";

// Faz 59 — header'daki tema seçici (LanguageToggle'ın yanında). 4 tema
// tek bir `<select>` ile; ayrı bir açık/kapalı dropdown state'i tutmaya
// gerek yok, native `<select>` erişilebilir ve testlenebilir.
const THEME_LABEL_KEY: Record<Theme, "themeFortiosDark" | "themeCyberNeon" | "themeMidnightBlue" | "themeEnterpriseLight"> = {
  "fortios-dark": "themeFortiosDark",
  "cyber-neon": "themeCyberNeon",
  "midnight-blue": "themeMidnightBlue",
  "enterprise-light": "themeEnterpriseLight",
};

export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  const { t } = useLocale();

  return (
    <select
      className={styles.select}
      aria-label={t.settings.theme}
      value={theme}
      onChange={(e) => setTheme(e.target.value as Theme)}
    >
      {ALL_THEMES.map((option) => (
        <option key={option} value={option}>
          {t.settings[THEME_LABEL_KEY[option]]}
        </option>
      ))}
    </select>
  );
}

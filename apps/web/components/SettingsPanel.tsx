"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { fetchAgents, fetchHealth, fetchHealthDb, fetchHealthSnmp } from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import type { Locale } from "@/lib/i18n/translations";
import { ALL_THEMES, useTheme, type Theme } from "@/lib/theme/ThemeProvider";
import { AgentDownloadPanel } from "./AgentDownloadPanel";
import { AgentEnrollmentPanel } from "./AgentEnrollmentPanel";
import { LdapConfigurationCenter } from "./LdapConfigurationCenter";
import { ScheduledScansPanel } from "./ScheduledScansPanel";
import { SmtpConfigurationCenter } from "./SmtpConfigurationCenter";
import { SnmpConfigurationCenter } from "./SnmpConfigurationCenter";
import { VCenterConfigPanel } from "./vcenter/VCenterConfigPanel";
import styles from "./SettingsPanel.module.css";

type CheckStatus = "checking" | "ok" | "unreachable";
type SnmpCheckStatus = "checking" | "configured" | "not_configured" | "unreachable";

// Faz 59 — tema id → i18n etiketi (aynı eşleme `ThemeSwitcher.tsx`'te de var).
function themeLabel(theme: Theme, s: ReturnType<typeof useLocale>["t"]["settings"]): string {
  switch (theme) {
    case "fortios-dark":
      return s.themeFortiosDark;
    case "cyber-neon":
      return s.themeCyberNeon;
    case "midnight-blue":
      return s.themeMidnightBlue;
    case "enterprise-light":
      return s.themeEnterpriseLight;
  }
}

export function SettingsPanel() {
  const { locale, setLocale, t } = useLocale();
  const { theme, setTheme } = useTheme();
  const { currentUser } = useAuth();
  const canManageLdap = currentUser?.permissions.includes("PAM_ADMIN") ?? false;
  const canManageSmtp = currentUser?.role === "ADMIN";
  const canManageVcenter = currentUser?.permissions.includes("VCENTER_ADMIN") ?? false;

  const [backendStatus, setBackendStatus] = useState<CheckStatus>("checking");
  const [dbStatus, setDbStatus] = useState<CheckStatus>("checking");
  const [snmpStatus, setSnmpStatus] = useState<SnmpCheckStatus>("checking");
  const [agentCount, setAgentCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchHealth()
      .then(() => {
        if (!cancelled) setBackendStatus("ok");
      })
      .catch(() => {
        if (!cancelled) setBackendStatus("unreachable");
      });

    fetchHealthDb()
      .then(() => {
        if (!cancelled) setDbStatus("ok");
      })
      .catch(() => {
        if (!cancelled) setDbStatus("unreachable");
      });

    // Faz: artık gerçek `snmp_profiles` durumunu yansıtıyor — en az bir
    // profil gerçekten "ready" (etkin + credential çözülmüş) ise
    // "configured", değilse dürüstçe "not_configured" (bkz.
    // app/routes/health.py).
    fetchHealthSnmp()
      .then((result) => {
        if (!cancelled) setSnmpStatus(result.snmp === "configured" ? "configured" : "not_configured");
      })
      .catch(() => {
        if (!cancelled) setSnmpStatus("unreachable");
      });

    fetchAgents()
      .then((agents) => {
        if (!cancelled) setAgentCount(agents.length);
      })
      .catch(() => {
        if (!cancelled) setAgentCount(null);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  function statusLabel(status: CheckStatus): string {
    if (status === "checking") return t.common.backendChecking;
    if (status === "ok") return t.settings.connected;
    return t.settings.disconnected;
  }

  function statusClass(status: CheckStatus): string {
    if (status === "ok") return styles.statusOk;
    if (status === "unreachable") return styles.statusDown;
    return styles.statusChecking;
  }

  return (
    <div className={styles.wrap}>
      <section className={styles.card}>
        <h2 className={styles.title}>{t.settings.title}</h2>
        <p className={styles.subtitle}>{t.settings.subtitle}</p>
      </section>

      <p className={styles.groupLabel}>{t.settings.sectionGeneral}</p>

      <section className={styles.card}>
        <h3 className={styles.sectionTitle}>{t.settings.theme}</h3>
        {/* Faz 59 — 2 düğmeli dark/light toggle 4 temalı seçiciye
            dönüştü; header'daki `ThemeSwitcher` ile AYNI `useTheme()`
            state'ini paylaşır. */}
        <div className={styles.toggleGroup} role="group" aria-label={t.settings.theme}>
          {ALL_THEMES.map((option) => (
            <button
              key={option}
              type="button"
              className={`${styles.toggleButton} ${
                theme === option ? styles.toggleButtonActive : ""
              }`}
              aria-pressed={theme === option}
              onClick={() => setTheme(option)}
            >
              {themeLabel(option, t.settings)}
            </button>
          ))}
        </div>
      </section>

      <section className={styles.card}>
        <h3 className={styles.sectionTitle}>{t.settings.language}</h3>
        <div className={styles.toggleGroup} role="group" aria-label={t.settings.language}>
          {(["tr", "en"] as Locale[]).map((option) => (
            <button
              key={option}
              type="button"
              className={`${styles.toggleButton} ${
                locale === option ? styles.toggleButtonActive : ""
              }`}
              aria-pressed={locale === option}
              onClick={() => setLocale(option)}
            >
              {option === "tr" ? t.settings.languageTr : t.settings.languageEn}
            </button>
          ))}
        </div>
      </section>

      <p className={styles.groupLabel}>{t.settings.sectionAgentConfiguration}</p>

      <section className={styles.card}>
        <h3 className={styles.sectionTitle}>{t.settings.sectionAgentConfiguration}</h3>
        <p className={styles.subtitle}>{t.settings.agentConfigDescription}</p>
        <div className={styles.statGrid}>
          <div className={styles.stat}>
            <span className={styles.statValue}>{agentCount ?? "—"}</span>
            <span className={styles.statLabel}>{t.settings.agentCount}</span>
          </div>
        </div>
        <p className={styles.hint}>{t.settings.agentConfigNote}</p>
        <Link className={styles.linkButton} href="/agents">
          {t.settings.viewAllAgents} →
        </Link>
        <AgentEnrollmentPanel />
        <AgentDownloadPanel />
      </section>

      <p className={styles.groupLabel}>{t.settings.snmpConfig.sectionTitle}</p>

      <SnmpConfigurationCenter />

      {canManageLdap && (
        <>
          <p className={styles.groupLabel}>{t.settings.ldapConfig.sectionTitle}</p>
          <LdapConfigurationCenter />
        </>
      )}

      {canManageSmtp && (
        <>
          <p className={styles.groupLabel}>{t.settings.smtpConfig.sectionTitle}</p>
          <SmtpConfigurationCenter />
        </>
      )}

      {canManageSmtp && (
        <>
          <p className={styles.groupLabel}>{t.settings.scheduledScans.title}</p>
          <ScheduledScansPanel />
        </>
      )}

      {canManageVcenter && (
        <>
          <p className={styles.groupLabel}>{t.settings.vcenterConfig.sectionTitle}</p>
          <VCenterConfigPanel />
        </>
      )}

      <p className={styles.groupLabel}>{t.settings.sectionSystem}</p>

      <section className={styles.card}>
        <h3 className={styles.sectionTitle}>{t.settings.backendStatus}</h3>
        <span className={`${styles.statusBadge} ${statusClass(backendStatus)}`}>
          {statusLabel(backendStatus)}
        </span>
      </section>

      <section className={styles.card}>
        <h3 className={styles.sectionTitle}>{t.settings.databaseStatus}</h3>
        <span className={`${styles.statusBadge} ${statusClass(dbStatus)}`}>
          {statusLabel(dbStatus)}
        </span>
      </section>

      <section className={styles.card}>
        <h3 className={styles.sectionTitle}>{t.settings.snmpStatus}</h3>
        <span
          className={`${styles.statusBadge} ${
            snmpStatus === "configured"
              ? styles.statusOk
              : snmpStatus === "unreachable"
                ? styles.statusDown
                : styles.statusChecking
          }`}
        >
          {snmpStatus === "checking"
            ? t.common.backendChecking
            : snmpStatus === "configured"
              ? t.settings.snmpConfigured
              : snmpStatus === "unreachable"
                ? t.settings.disconnected
                : t.settings.notConfigured}
        </span>
      </section>
    </div>
  );
}

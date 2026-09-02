"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { fetchAgents, fetchHealth, fetchHealthDb, fetchHealthSnmp } from "@/lib/api";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import type { Locale } from "@/lib/i18n/translations";
import { useTheme, type Theme } from "@/lib/theme/ThemeProvider";
import { AgentDownloadPanel } from "./AgentDownloadPanel";
import { AgentEnrollmentPanel } from "./AgentEnrollmentPanel";
import { SnmpConfigurationCenter } from "./SnmpConfigurationCenter";
import styles from "./SettingsPanel.module.css";

type CheckStatus = "checking" | "ok" | "unreachable";

export function SettingsPanel() {
  const { locale, setLocale, t } = useLocale();
  const { theme, setTheme } = useTheme();

  const [backendStatus, setBackendStatus] = useState<CheckStatus>("checking");
  const [dbStatus, setDbStatus] = useState<CheckStatus>("checking");
  const [snmpStatus, setSnmpStatus] = useState<CheckStatus>("checking");
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

    // /api/health/snmp her zaman 200 + not_configured döner (gerçek
    // ajan yok) — burada yalnızca backend'e gerçekten ulaşılabildiğini
    // doğruluyoruz; "ok" durumu bile SNMP Durumu satırında her zaman
    // "Yapılandırılmadı" olarak gösterilir (bkz. render kısmı).
    fetchHealthSnmp()
      .then(() => {
        if (!cancelled) setSnmpStatus("ok");
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
        <h3 className={styles.sectionTitle}>{t.settings.appearance}</h3>
        <div className={styles.toggleGroup} role="group" aria-label={t.settings.appearance}>
          {(["dark", "light"] as Theme[]).map((option) => (
            <button
              key={option}
              type="button"
              className={`${styles.toggleButton} ${
                theme === option ? styles.toggleButtonActive : ""
              }`}
              aria-pressed={theme === option}
              onClick={() => setTheme(option)}
            >
              {option === "dark" ? t.settings.appearanceDark : t.settings.appearanceLight}
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
        <span className={`${styles.statusBadge} ${styles.statusChecking}`}>
          {snmpStatus === "checking" ? t.common.backendChecking : t.settings.notConfigured}
        </span>
      </section>
    </div>
  );
}

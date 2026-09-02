"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./Sidebar.module.css";

type NavItem = {
  key: string;
  label: string;
  href: string;
  icon: string;
};

type NavGroup = {
  key: string;
  label: string;
  items: NavItem[];
};

export function Sidebar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { t } = useLocale();

  const groups: NavGroup[] = [
    {
      key: "overview",
      label: t.nav.groupOverview,
      items: [{ key: "dashboard", label: t.nav.dashboard, href: "/", icon: "📊" }],
    },
    {
      key: "discovery",
      label: t.nav.groupDiscovery,
      items: [
        { key: "discovery", label: t.nav.discovery, href: "/discovery", icon: "🔍" },
        { key: "assets", label: t.nav.assets, href: "/assets", icon: "🗂️" },
        { key: "topology", label: t.nav.topology, href: "/topology", icon: "🕸️" },
        { key: "scans", label: t.nav.scans, href: "/scans", icon: "🕓" },
      ],
    },
    {
      key: "operations",
      label: t.nav.groupOperations,
      items: [
        { key: "alerts", label: t.nav.alerts, href: "/alerts", icon: "🚨" },
        { key: "monitoring", label: t.nav.monitoring, href: "/monitoring", icon: "📈" },
        { key: "agents", label: t.nav.agents, href: "/agents", icon: "🖥️" },
      ],
    },
    {
      key: "system",
      label: t.nav.groupSystem,
      items: [{ key: "settings", label: t.nav.settings, href: "/settings", icon: "⚙️" }],
    },
  ];

  function isActive(href: string): boolean {
    // `/agents/[id]` gibi alt route'lar da (Faz 30) kendi ana menü
    // öğesini aktif göstermeli — hiçbir mevcut `href`'in alt route'u
    // olmadığı için bu genelleme geriye dönük DAVRANIŞ değiştirmez.
    return pathname === href || (href !== "/" && pathname.startsWith(`${href}/`));
  }

  return (
    <>
      <button
        className={styles.mobileToggle}
        onClick={() => setMobileOpen((open) => !open)}
        aria-label={mobileOpen ? t.nav.closeMenu : t.nav.openMenu}
        aria-expanded={mobileOpen}
      >
        <span className={styles.hamburgerIcon} aria-hidden="true">
          {mobileOpen ? "✕" : "☰"}
        </span>
        <span className={styles.appName}>IT Operations Assistant</span>
      </button>

      <aside
        className={`${styles.sidebar} ${mobileOpen ? styles.sidebarOpen : ""}`}
        style={mobileOpen ? { transform: "translateX(0)" } : undefined}
      >
        <div className={styles.brand}>
          <span className={styles.brandIcon} aria-hidden="true">
            🛰️
          </span>
          <div>
            <p className={styles.brandName}>{t.nav.brandName}</p>
            <p className={styles.brandTagline}>{t.nav.brandTagline}</p>
          </div>
        </div>

        <nav className={styles.nav} aria-label={t.nav.primaryLabel}>
          {groups.map((group) => (
            <div key={group.key} className={styles.group}>
              <p className={styles.groupLabel}>{group.label}</p>
              {group.items.map((item) => (
                <Link
                  key={item.key}
                  href={item.href}
                  title={item.label}
                  aria-current={isActive(item.href) ? "page" : undefined}
                  className={`${styles.navLink} ${isActive(item.href) ? styles.navLinkActive : ""}`}
                  onClick={() => setMobileOpen(false)}
                >
                  <span className={styles.navIcon} aria-hidden="true">
                    {item.icon}
                  </span>
                  {item.label}
                </Link>
              ))}
            </div>
          ))}
        </nav>
      </aside>

      {mobileOpen && (
        <div
          className={styles.backdrop}
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}
    </>
  );
}

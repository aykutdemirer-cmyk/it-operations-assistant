"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/lib/auth/AuthProvider";
import type { Permission } from "@/lib/auth/permissions";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./Sidebar.module.css";

type NavItem = {
  key: string;
  label: string;
  href: string;
  icon: string;
  permission: Permission;
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
  const { currentUser } = useAuth();

  // Faz 47 — kullanıcının açık isteği: menü artık statik DEĞİL, her
  // öğe kullanıcının `permissions` listesine göre dinamik filtrelenir
  // ("yalnızca PAM_ACCESS'i olan bir kullanıcı Dashboard dahil hiçbir
  // menüyü görmesin"). `currentUser` `null` iken (giriş yapılmamış/
  // token doğrulanıyor) HİÇBİR öğe gösterilmez.
  const allGroups: NavGroup[] = [
    {
      key: "overview",
      label: t.nav.groupOverview,
      items: [{ key: "dashboard", label: t.nav.dashboard, href: "/", icon: "📊", permission: "DASHBOARD_VIEW" }],
    },
    {
      key: "discovery",
      label: t.nav.groupDiscovery,
      items: [
        { key: "discovery", label: t.nav.discovery, href: "/discovery", icon: "🔍", permission: "DISCOVERY_VIEW" },
        { key: "assets", label: t.nav.assets, href: "/assets", icon: "🗂️", permission: "ASSETS_VIEW" },
        { key: "topology", label: t.nav.topology, href: "/topology", icon: "🕸️", permission: "TOPOLOGY_VIEW" },
        { key: "scans", label: t.nav.scans, href: "/scans", icon: "🕓", permission: "SCANS_VIEW" },
        { key: "vcenter", label: t.nav.vcenter, href: "/vcenter", icon: "☁️", permission: "VCENTER_VIEW" },
      ],
    },
    {
      key: "operations",
      label: t.nav.groupOperations,
      items: [
        { key: "alerts", label: t.nav.alerts, href: "/alerts", icon: "🚨", permission: "ALERTS_VIEW" },
        { key: "monitoring", label: t.nav.monitoring, href: "/monitoring", icon: "📈", permission: "MONITORING_VIEW" },
        { key: "agents", label: t.nav.agents, href: "/agents", icon: "🖥️", permission: "AGENTS_VIEW" },
        { key: "tickets", label: t.nav.tickets, href: "/tickets", icon: "🎫", permission: "TICKETS_VIEW" },
        { key: "my-access", label: t.pam.myAccessTitle, href: "/my-access", icon: "🔑", permission: "PAM_ACCESS" },
      ],
    },
    {
      key: "system",
      label: t.nav.groupSystem,
      items: [{ key: "settings", label: t.nav.settings, href: "/settings", icon: "⚙️", permission: "SETTINGS_VIEW" }],
    },
    {
      key: "pam",
      label: t.nav.groupPam,
      items: [
        { key: "pam-users", label: t.nav.pamUsers, href: "/pam/users", icon: "👤", permission: "PAM_ADMIN" },
        { key: "pam-permissions", label: t.nav.pamPermissions, href: "/pam/permissions", icon: "📊", permission: "PAM_ADMIN" },
        { key: "pam-vault", label: t.nav.pamVault, href: "/pam/vault", icon: "🔐", permission: "PAM_ADMIN" },
        { key: "pam-rules", label: t.nav.pamRules, href: "/pam/rules", icon: "🗝️", permission: "PAM_ADMIN" },
        { key: "pam-requests", label: t.nav.pamRequests, href: "/pam/requests", icon: "📩", permission: "PAM_ADMIN" },
        { key: "pam-tags", label: t.nav.pamTags, href: "/pam/tags", icon: "🏷️", permission: "PAM_ADMIN" },
        { key: "pam-groups", label: t.nav.pamGroups, href: "/pam/groups", icon: "🗂️", permission: "PAM_ADMIN" },
        { key: "pam-audit", label: t.nav.pamAudit, href: "/pam/audit", icon: "📜", permission: "PAM_ADMIN" },
      ],
    },
  ];

  const permissions = currentUser?.permissions ?? [];
  const groups = allGroups
    .map((group) => ({ ...group, items: group.items.filter((item) => permissions.includes(item.permission)) }))
    .filter((group) => group.items.length > 0);

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

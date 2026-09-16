import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

import { DashboardDataProvider } from "@/lib/DashboardDataProvider";
import { AuthProvider, TOKEN_STORAGE_KEY } from "@/lib/auth/AuthProvider";
import type { Permission } from "@/lib/auth/permissions";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";

// Faz 47 — sayfa/route-guard testleri artık `AuthProvider`'ın gerçekten
// giriş yapmış bir kullanıcı görmesini gerektiriyor (bkz. `RequirePermission`).
// `FAKE_TOKEN`'ın kendisi GERÇEK bir JWT değil (yalnızca `localStorage`'da
// varlığı `AuthProvider`'a `GET /api/auth/me`'yi çağırtır) — o çağrının
// yanıtı her testin kendi fetch mock'unda `mockCurrentUser(...)` ile
// üretilir.
export const FAKE_TOKEN = "test-fake-token";

export function setLoggedInToken() {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, FAKE_TOKEN);
}

export function mockCurrentUser(permissions: Permission[], overrides: Record<string, unknown> = {}) {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    username: "test-user",
    role: "ADMIN",
    full_name: null,
    is_active: true,
    ad_username: null,
    permissions,
    // Faz 65 — bilet RBAC (varsayılan tam yetkili; testler `overrides`
    // ile REQUESTER'a çevirebilir).
    ticket_role: "ADMIN",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

const EMPTY_MONITORING_BATCH = {
  started_at: "2026-08-26T00:00:00Z",
  completed_at: "2026-08-26T00:00:00Z",
  duration_ms: 0,
  total: 0,
  polled: 0,
  not_configured: 0,
  results: [],
};

// `GET /api/monitoring/history` (Faz: arka plan poller önbelleği) —
// `PollBatchResult` ile AYNI şekil DEĞİL, bu yüzden ayrı bir varsayılan.
const EMPTY_MONITORING_HISTORY = {
  latest_batch: null,
  poll_log: [],
  bandwidth_history: [],
};

/**
 * `DashboardDataProvider` her zaman hem `GET /api/assets` hem
 * `GET /api/scans` çağırır (bkz. `lib/DashboardDataProvider.tsx`) —
 * dashboard component'lerini test ederken tek bir endpoint'i mock'lamak
 * yetmiyor, ikisi de URL'e göre ayrı ayrı yanıtlanmalı. `monitoring`
 * opsiyoneldir (Faz 27) — verilmezse boş bir `PollBatchResult` döner,
 * `MonitoringOverview` dışındaki testler bu davranışa hiç bağımlı
 * değildir.
 */
export function mockAssetsAndScans(
  assets: unknown[],
  scans: unknown[],
  monitoring: unknown = EMPTY_MONITORING_BATCH,
  snmpProfiles: unknown[] = [],
  agents: unknown[] = [],
  monitoringHistory: unknown = EMPTY_MONITORING_HISTORY,
  currentUserPermissions: Permission[] | null = null,
) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      // Faz 47 — yalnızca `setLoggedInToken()` ile bir token varsa
      // `AuthProvider` bunu çağırır; token yoksa bu dal hiç tetiklenmez.
      if (url.includes("/api/auth/me")) {
        return Promise.resolve({ ok: true, json: async () => mockCurrentUser(currentUserPermissions ?? []) });
      }
      // Daha ÖZEL örüntüler önce kontrol edilir — `/api/assets/{id}/
      // snmp-profile` de `/api/assets` alt dizesini içerir, bu yüzden
      // genel `/api/assets` kontrolünden ÖNCE gelmeli (Faz 29.5).
      // Aynı şekilde `/api/monitoring/history`, genel `/api/monitoring`
      // kontrolünden ÖNCE kontrol edilmeli.
      if (url.includes("/snmp-profile")) {
        return Promise.resolve({ ok: true, json: async () => ({ configured: false, profile: null }) });
      }
      if (/\/api\/snmp\/profiles(\?|$)/.test(url)) {
        return Promise.resolve({ ok: true, json: async () => snmpProfiles });
      }
      // Lifecycle Management — özel yollar genel `/api/agents` örüntüsünden
      // ÖNCE kontrol edilmeli (bkz. yukarıdaki `/snmp-profile` ile aynı
      // gerekçe). Testlerin çoğu bu ekranları hiç kullanmıyor — dürüst,
      // gerçekçi varsayılanlar (politika kapalı, arşiv boş).
      if (url.includes("/api/agents/retention-policy")) {
        return Promise.resolve({ ok: true, json: async () => ({ enabled: false, retention_days: 30 }) });
      }
      if (url.includes("/api/agents/archived")) {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      if (/\/api\/agents(\?|$)/.test(url)) {
        return Promise.resolve({ ok: true, json: async () => agents });
      }
      if (url.includes("/api/assets")) {
        return Promise.resolve({ ok: true, json: async () => assets });
      }
      if (url.includes("/api/scans")) {
        return Promise.resolve({ ok: true, json: async () => scans });
      }
      if (url.includes("/api/monitoring/history")) {
        return Promise.resolve({ ok: true, json: async () => monitoringHistory });
      }
      if (url.includes("/api/monitoring")) {
        return Promise.resolve({ ok: true, json: async () => monitoring });
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    }),
  );
}

/**
 * Dashboard verisi tüketen component'ler için ortak render yardımcısı —
 * `DashboardDataProvider` + `LocaleProvider` + `ThemeProvider` ile
 * sarmalar (gerçek `app/layout.tsx` sıralamasıyla aynı; Faz 59'dan beri
 * `TopHeader` → `ThemeSwitcher` bir `ThemeProvider` gerektiriyor).
 * Varsayılan dil `tr`, varsayılan tema `fortios-dark`.
 */
export function renderWithProviders(ui: ReactElement): RenderResult {
  return render(
    <LocaleProvider>
      <ThemeProvider>
        <AuthProvider>
          <DashboardDataProvider>{ui}</DashboardDataProvider>
        </AuthProvider>
      </ThemeProvider>
    </LocaleProvider>,
  );
}

// Geriye dönük uyumluluk — yeni testlerde `renderWithProviders` tercih edin.
export const renderWithDashboardData = renderWithProviders;

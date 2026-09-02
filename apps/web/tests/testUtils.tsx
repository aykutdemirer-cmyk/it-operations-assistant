import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

import { DashboardDataProvider } from "@/lib/DashboardDataProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";

const EMPTY_MONITORING_BATCH = {
  started_at: "2026-08-26T00:00:00Z",
  completed_at: "2026-08-26T00:00:00Z",
  duration_ms: 0,
  total: 0,
  polled: 0,
  not_configured: 0,
  results: [],
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
) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      // Daha ÖZEL örüntüler önce kontrol edilir — `/api/assets/{id}/
      // snmp-profile` de `/api/assets` alt dizesini içerir, bu yüzden
      // genel `/api/assets` kontrolünden ÖNCE gelmeli (Faz 29.5).
      if (url.includes("/snmp-profile")) {
        return Promise.resolve({ ok: true, json: async () => ({ configured: false, profile: null }) });
      }
      if (/\/api\/snmp\/profiles(\?|$)/.test(url)) {
        return Promise.resolve({ ok: true, json: async () => snmpProfiles });
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
      if (url.includes("/api/monitoring")) {
        return Promise.resolve({ ok: true, json: async () => monitoring });
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    }),
  );
}

/**
 * Dashboard verisi tüketen component'ler için ortak render yardımcısı —
 * `DashboardDataProvider` + `LocaleProvider` ile sarmalar (neredeyse her
 * component artık `useLocale()` kullanıyor). Varsayılan dil `tr`'dir.
 */
export function renderWithProviders(ui: ReactElement): RenderResult {
  return render(
    <LocaleProvider>
      <DashboardDataProvider>{ui}</DashboardDataProvider>
    </LocaleProvider>,
  );
}

// Geriye dönük uyumluluk — yeni testlerde `renderWithProviders` tercih edin.
export const renderWithDashboardData = renderWithProviders;

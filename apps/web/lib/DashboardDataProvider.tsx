"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { fetchAssets, fetchMonitoringHistory, fetchScans, type Asset, type Scan, type SnmpPollResult } from "@/lib/api";
import { useAutoRefresh } from "@/lib/useAutoRefresh";

export type FetchStatus = "loading" | "done" | "error";

// Dashboard/Monitoring ekranlarının "5-10 saniyede bir, layout
// sıçraması olmadan sessizce güncellensin" isteği — bu sağlayıcı
// tüketen HER component (DashboardSummary, InfrastructureHealth,
// AlertsPanel, AssetInventory, ...) otomatik olarak faydalanır.
const AUTO_REFRESH_INTERVAL_MS = 8000;

type DashboardDataValue = {
  assets: Asset[];
  assetsStatus: FetchStatus;
  assetsError: string;
  refetchAssets: (options?: { silent?: boolean }) => void;
  scans: Scan[];
  scansStatus: FetchStatus;
  scansError: string;
  refetchScans: (options?: { silent?: boolean }) => void;
  // Faz 70 — asset id -> en son gerçek SNMP poll sonucu (bkz.
  // `GET /api/monitoring/history`, Faz 39). `computeAlerts`'in
  // `options.monitoring`'ine geçilir — SNMP-tabanlı alert kuralları
  // (interface_down/high_bandwidth/...) bunu OLMADAN hiç tetiklenmez.
  monitoring: Record<string, SnmpPollResult>;
};

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

const DashboardDataContext = createContext<DashboardDataValue | null>(null);

/**
 * Dashboard component'lerinin (DashboardSummary, InfrastructureHealth,
 * AlertsPanel, DeviceDistribution, OpenPortsOverview, RecentActivity,
 * RecentScans, AssetInventory) bağımsız bağımsız `GET /api/assets` /
 * `GET /api/scans` çağırmasını önlemek için tek bir yerden fetch eden
 * paylaşımlı veri katmanı (bkz. `docs/decisions.md` §9/§10 — ölçüldü,
 * burada ele alındı). Yeni bir dependency (SWR/React Query) eklenmedi;
 * mevcut React context + `useState`/`useEffect` yeterli.
 *
 * `network-scan-completed` event dinleyicisi burada, tek yerde
 * yaşıyor — daha önce `RecentScans` kendi başına dinliyordu, artık her
 * tüketici otomatik olarak taze veri alıyor.
 */
export function DashboardDataProvider({ children }: { children: ReactNode }) {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [assetsStatus, setAssetsStatus] = useState<FetchStatus>("loading");
  const [assetsErrorMsg, setAssetsErrorMsg] = useState("");
  const [scans, setScans] = useState<Scan[]>([]);
  const [scansStatus, setScansStatus] = useState<FetchStatus>("loading");
  const [scansErrorMsg, setScansErrorMsg] = useState("");
  const [monitoring, setMonitoring] = useState<Record<string, SnmpPollResult>>({});

  const refetchAssets = useCallback((options?: { silent?: boolean }) => {
    // `silent`: arka plan otomatik yenilemesi (bkz. `useAutoRefresh`
    // aşağıda) — `status`'u "loading"a GERİ ALMAZ, ekran mevcut veriyi
    // göstermeye devam eder (layout sıçraması yok). Manuel "Yenile"
    // butonu `silent` GEÇMEZ — kullanıcı görünür bir geri bildirim
    // bekler, bu yüzden normal "loading" akışı korunur.
    if (!options?.silent) setAssetsStatus("loading");
    fetchAssets()
      .then((data) => {
        setAssets(data);
        setAssetsStatus("done");
      })
      .catch((error) => {
        if (options?.silent) return; // arka planda sessizce yut, mevcut veri kalsın
        setAssetsErrorMsg(errorMessage(error, "Asset listesi alınamadı"));
        setAssetsStatus("error");
      });
  }, []);

  const refetchScans = useCallback((options?: { silent?: boolean }) => {
    if (!options?.silent) setScansStatus("loading");
    fetchScans()
      .then((data) => {
        setScans(data);
        setScansStatus("done");
      })
      .catch((error) => {
        if (options?.silent) return;
        setScansErrorMsg(errorMessage(error, "Scan listesi alınamadı"));
        setScansStatus("error");
      });
  }, []);

  // Faz 70 — poll TETİKLEMEZ, yalnızca arka plan worker'ının önbelleğini
  // okur (bkz. `fetchMonitoringHistory` docstring'i) — sessiz auto-
  // refresh döngüsünde sık çağrılması güvenlidir. Hata durumunda mevcut
  // haritayı korur (bir alert kaynağının geçici olarak erişilemez
  // olması diğer dashboard verisini bozmamalı).
  const refetchMonitoring = useCallback(() => {
    fetchMonitoringHistory()
      .then((data) => {
        const next: Record<string, SnmpPollResult> = {};
        for (const result of data.latest_batch?.results ?? []) {
          next[result.asset_id] = result;
        }
        setMonitoring(next);
      })
      .catch(() => {
        /* sessizce yut — SNMP alert kuralları bu tur atlanır */
      });
  }, []);

  useEffect(() => {
    let cancelled = false;

    fetchAssets()
      .then((data) => {
        if (!cancelled) {
          setAssets(data);
          setAssetsStatus("done");
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setAssetsErrorMsg(errorMessage(error, "Asset listesi alınamadı"));
          setAssetsStatus("error");
        }
      });

    fetchScans()
      .then((data) => {
        if (!cancelled) {
          setScans(data);
          setScansStatus("done");
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setScansErrorMsg(errorMessage(error, "Scan listesi alınamadı"));
          setScansStatus("error");
        }
      });

    refetchMonitoring();

    function handleScanCompleted() {
      refetchAssets();
      refetchScans();
    }

    window.addEventListener("network-scan-completed", handleScanCompleted);

    return () => {
      cancelled = true;
      window.removeEventListener("network-scan-completed", handleScanCompleted);
    };
  }, [refetchAssets, refetchScans, refetchMonitoring]);

  const silentRefetchAll = useCallback(() => {
    refetchAssets({ silent: true });
    refetchScans({ silent: true });
    refetchMonitoring();
  }, [refetchAssets, refetchScans, refetchMonitoring]);

  useAutoRefresh(silentRefetchAll, AUTO_REFRESH_INTERVAL_MS);

  return (
    <DashboardDataContext.Provider
      value={{
        assets,
        assetsStatus,
        assetsError: assetsErrorMsg,
        refetchAssets,
        scans,
        scansStatus,
        scansError: scansErrorMsg,
        refetchScans,
        monitoring,
      }}
    >
      {children}
    </DashboardDataContext.Provider>
  );
}

export function useDashboardData(): DashboardDataValue {
  const ctx = useContext(DashboardDataContext);
  if (!ctx) {
    throw new Error("useDashboardData must be used within a DashboardDataProvider");
  }
  return ctx;
}

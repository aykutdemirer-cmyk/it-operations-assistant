"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { fetchAssets, fetchScans, type Asset, type Scan } from "@/lib/api";

export type FetchStatus = "loading" | "done" | "error";

type DashboardDataValue = {
  assets: Asset[];
  assetsStatus: FetchStatus;
  assetsError: string;
  refetchAssets: () => void;
  scans: Scan[];
  scansStatus: FetchStatus;
  scansError: string;
  refetchScans: () => void;
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

  function refetchAssets() {
    setAssetsStatus("loading");
    fetchAssets()
      .then((data) => {
        setAssets(data);
        setAssetsStatus("done");
      })
      .catch((error) => {
        setAssetsErrorMsg(errorMessage(error, "Asset listesi alınamadı"));
        setAssetsStatus("error");
      });
  }

  function refetchScans() {
    setScansStatus("loading");
    fetchScans()
      .then((data) => {
        setScans(data);
        setScansStatus("done");
      })
      .catch((error) => {
        setScansErrorMsg(errorMessage(error, "Scan listesi alınamadı"));
        setScansStatus("error");
      });
  }

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

    function handleScanCompleted() {
      refetchAssets();
      refetchScans();
    }

    window.addEventListener("network-scan-completed", handleScanCompleted);

    return () => {
      cancelled = true;
      window.removeEventListener("network-scan-completed", handleScanCompleted);
    };
  }, []);

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

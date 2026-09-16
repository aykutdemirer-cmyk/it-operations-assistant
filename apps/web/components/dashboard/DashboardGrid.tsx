"use client";

import { useEffect, useMemo, useRef, useState, type ComponentType } from "react";
import { Responsive, WidthProvider, type Layout } from "react-grid-layout";

import { AgentHealthSummary } from "@/components/AgentHealthSummary";
import { AlertsPanel } from "@/components/AlertsPanel";
import { DashboardSummary } from "@/components/DashboardSummary";
import { DeviceDistribution } from "@/components/DeviceDistribution";
import { DeviceHealthSummary } from "@/components/DeviceHealthSummary";
import { InfrastructureHealth } from "@/components/InfrastructureHealth";
import { MonitoringCoverage } from "@/components/MonitoringCoverage";
import { NetworkPerformance } from "@/components/NetworkPerformance";
import { OpenPortsOverview } from "@/components/OpenPortsOverview";
import { RecentActivity } from "@/components/RecentActivity";
import { RecentScans } from "@/components/RecentScans";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./DashboardGrid.module.css";

const ResponsiveGrid = WidthProvider(Responsive);

// ── Widget kayıt defteri ─────────────────────────────────────────────
// Faz 59 — HİÇBİR widget component'i değişmedi (Faz 36'dan beri var
// olanlar); yalnızca bir id ⋅ i18n başlık anahtarı ⋅ kategori ⋅
// varsayılan grid boyutuyla kaydedildiler.
type WidgetCategory = "system" | "network" | "pam-security";
type LabelKey = keyof ReturnType<typeof useLocale>["t"]["dashboard"]["grid"];

type WidgetDef = {
  id: string;
  Component: ComponentType;
  labelKey: LabelKey;
  category: WidgetCategory;
  defaultSize: { w: number; h: number };
};

const WIDGETS: WidgetDef[] = [
  { id: "dashboard-summary", Component: DashboardSummary, labelKey: "widgetDashboardSummary", category: "system", defaultSize: { w: 12, h: 5 } },
  { id: "infrastructure-health", Component: InfrastructureHealth, labelKey: "widgetInfrastructureHealth", category: "system", defaultSize: { w: 8, h: 9 } },
  { id: "device-health", Component: DeviceHealthSummary, labelKey: "widgetDeviceHealth", category: "system", defaultSize: { w: 4, h: 9 } },
  { id: "device-distribution", Component: DeviceDistribution, labelKey: "widgetDeviceDistribution", category: "network", defaultSize: { w: 6, h: 8 } },
  { id: "open-ports", Component: OpenPortsOverview, labelKey: "widgetOpenPorts", category: "network", defaultSize: { w: 6, h: 8 } },
  { id: "alerts", Component: AlertsPanel, labelKey: "widgetAlerts", category: "pam-security", defaultSize: { w: 6, h: 9 } },
  { id: "recent-activity", Component: RecentActivity, labelKey: "widgetRecentActivity", category: "pam-security", defaultSize: { w: 6, h: 9 } },
  { id: "agent-health", Component: AgentHealthSummary, labelKey: "widgetAgentHealth", category: "system", defaultSize: { w: 6, h: 7 } },
  { id: "monitoring-coverage", Component: MonitoringCoverage, labelKey: "widgetMonitoringCoverage", category: "network", defaultSize: { w: 6, h: 7 } },
  { id: "network-performance", Component: NetworkPerformance, labelKey: "widgetNetworkPerformance", category: "network", defaultSize: { w: 6, h: 7 } },
  { id: "recent-scans", Component: RecentScans, labelKey: "widgetRecentScans", category: "pam-security", defaultSize: { w: 6, h: 7 } },
];

const WIDGET_BY_ID = new Map(WIDGETS.map((w) => [w.id, w]));

// ── Hazır görünümler ────────────────────────────────────────────────
type ViewId = "overview" | "system" | "network" | "pam-security" | "custom";

function layoutFor(ids: string[]): Layout[] {
  // Basit iki-sütun akış yerleşimi; kullanıcı sürükleyip kaydedince bu
  // yalnızca "varsayılan" olarak kalır.
  let x = 0;
  let y = 0;
  let rowH = 0;
  return ids.map((id) => {
    const def = WIDGET_BY_ID.get(id)!;
    const { w, h } = def.defaultSize;
    if (x + w > 12) {
      x = 0;
      y += rowH;
      rowH = 0;
    }
    const item: Layout = { i: id, x, y, w, h };
    x += w;
    rowH = Math.max(rowH, h);
    return item;
  });
}

const VIEW_WIDGETS: Record<Exclude<ViewId, "custom">, string[]> = {
  overview: [
    "dashboard-summary",
    "infrastructure-health",
    "device-health",
    "device-distribution",
    "open-ports",
    "alerts",
    "recent-activity",
    "agent-health",
    "monitoring-coverage",
    "network-performance",
    "recent-scans",
  ],
  system: ["dashboard-summary", "infrastructure-health", "device-health", "agent-health", "monitoring-coverage"],
  network: ["device-distribution", "open-ports", "network-performance", "monitoring-coverage"],
  "pam-security": ["alerts", "recent-activity", "recent-scans"],
};

const VIEW_LABEL_KEY: Record<ViewId, LabelKey> = {
  overview: "viewOverview",
  system: "viewSystem",
  network: "viewNetwork",
  "pam-security": "viewPamSecurity",
  custom: "viewCustom",
};

const VIEW_IDS: ViewId[] = ["overview", "system", "network", "pam-security", "custom"];

const LS_VIEW_KEY = "itops-dashboard-view";
const lsLayoutKey = (view: ViewId) => `itops-dashboard-layout-${view}`;

type StoredLayout = { widgets: string[]; layout: Layout[] };

function defaultStoredLayout(view: ViewId): StoredLayout {
  const widgets = view === "custom" ? [] : [...VIEW_WIDGETS[view]];
  return { widgets, layout: layoutFor(widgets) };
}

function loadStoredLayout(view: ViewId): StoredLayout {
  try {
    const raw = window.localStorage.getItem(lsLayoutKey(view));
    if (raw) {
      const parsed = JSON.parse(raw) as StoredLayout;
      if (Array.isArray(parsed.widgets) && Array.isArray(parsed.layout)) {
        // Kayıt defterinden kalkmış bir widget id'si varsa süz.
        const widgets = parsed.widgets.filter((id) => WIDGET_BY_ID.has(id));
        return { widgets, layout: parsed.layout.filter((l) => widgets.includes(l.i)) };
      }
    }
  } catch {
    // bozuk/erişilemez → varsayılana düş.
  }
  return defaultStoredLayout(view);
}

/** Faz 59 — `react-grid-layout` tabanlı sürüklenebilir/boyutlandırılabilir
 * dashboard. Widget component'lerinin hiçbiri değişmedi — `DashboardData
 * Provider` (layout.tsx) hâlâ hepsini sarıyor, veri paylaşımı aynen
 * çalışıyor. Düzen `localStorage`'a görünüm başına ayrı bir anahtarla
 * yazılır (backend/DB YOK — bkz. `docs/roadmap.md` Faz 59). */
export function DashboardGrid() {
  const { t } = useLocale();
  const g = t.dashboard.grid;

  const [mounted, setMounted] = useState(false);
  const [view, setView] = useState<ViewId>("overview");
  const [store, setStore] = useState<StoredLayout>(() => defaultStoredLayout("overview"));
  const [dirty, setDirty] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  // Faz 59 sonrası düzeltme — düzenleme araç çubuğu (Widget Ekle/Kaydet/
  // Sıfırla + sürükle-bırak) varsayılan olarak GİZLİ; günlük kullanımda
  // dashboard'u kirletmesin diye yalnızca "Düzenle"ye tıklanınca açılır,
  // kaydedince (veya "Bitti" ile) otomatik kapanır. Kalıcı DEĞİL —
  // sayfa her açıldığında normal (salt-izleme) görünümle başlar.
  const [editMode, setEditMode] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Mount sonrası: kayıtlı görünümü + o görünümün düzenini oku (SSR
  // hydration uyumsuzluğunu önlemek için ilk render her zaman "overview"
  // varsayılanı, gerçek okuma burada).
  useEffect(() => {
    let storedView: ViewId = "overview";
    try {
      const v = window.localStorage.getItem(LS_VIEW_KEY);
      if (v && (VIEW_IDS as string[]).includes(v)) storedView = v as ViewId;
    } catch {
      storedView = "overview";
    }
    const initial = loadStoredLayout(storedView);
    // setState çağrıları bir microtask'a ertelendi — bkz. `lib/i18n/
    // LocaleProvider.tsx`/`lib/theme/ThemeProvider.tsx`'teki aynı desen
    // (react-hooks/set-state-in-effect).
    Promise.resolve().then(() => {
      setView(storedView);
      setStore(initial);
      setDirty(false);
      setMounted(true);
    });
  }, []);

  function switchView(next: ViewId) {
    setView(next);
    setStore(loadStoredLayout(next));
    setDirty(false);
    try {
      window.localStorage.setItem(LS_VIEW_KEY, next);
    } catch {
      // sorun değil.
    }
  }

  function flashToast(message: string) {
    setToast(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  }

  function handleLayoutChange(next: Layout[]) {
    if (!mounted) return;
    setStore((prev) => ({ ...prev, layout: next }));
    setDirty(true);
  }

  function saveLayout() {
    try {
      window.localStorage.setItem(lsLayoutKey(view), JSON.stringify(store));
      flashToast(g.layoutSaved);
      setDirty(false);
    } catch {
      // yazılamazsa yalnızca bu oturum için geçerli kalır.
    }
    // Kaydedince düzenleme araç çubuğu kapanır — dashboard günlük
    // kullanıma temiz döner (kullanıcı isteği).
    setEditMode(false);
  }

  function resetLayout() {
    const fresh = defaultStoredLayout(view);
    setStore(fresh);
    setDirty(false);
    try {
      window.localStorage.removeItem(lsLayoutKey(view));
    } catch {
      // sorun değil.
    }
    flashToast(g.layoutReset);
  }

  function addWidget(id: string) {
    if (store.widgets.includes(id)) return;
    const def = WIDGET_BY_ID.get(id)!;
    const nextWidgets = [...store.widgets, id];
    const maxY = store.layout.reduce((m, l) => Math.max(m, l.y + l.h), 0);
    setStore({
      widgets: nextWidgets,
      layout: [...store.layout, { i: id, x: 0, y: maxY, w: def.defaultSize.w, h: def.defaultSize.h }],
    });
    setDirty(true);
  }

  function removeWidget(id: string) {
    setStore((prev) => ({
      widgets: prev.widgets.filter((w) => w !== id),
      layout: prev.layout.filter((l) => l.i !== id),
    }));
    setDirty(true);
  }

  const layouts = useMemo(() => ({ lg: store.layout, md: store.layout }), [store.layout]);

  // İlk (SSR + hydration) render: grid'i çizme — `WidthProvider` window
  // ölçümü yapıyor. Yükleniyor metnine gerek yok, kısa bir boşluk.
  if (!mounted) {
    return <div style={{ minHeight: 200 }} aria-hidden="true" />;
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <label className={styles.select} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          {g.viewLabel}
          <select
            aria-label={g.viewLabel}
            value={view}
            onChange={(e) => switchView(e.target.value as ViewId)}
            style={{ background: "transparent", color: "inherit", border: "none", fontWeight: 600 }}
          >
            {VIEW_IDS.map((id) => (
              <option key={id} value={id}>
                {g[VIEW_LABEL_KEY[id]]}
              </option>
            ))}
          </select>
        </label>
        <span className={styles.spacer} />
        {editMode ? (
          <>
            <button type="button" className={styles.button} onClick={() => setAddOpen(true)}>
              + {g.addWidget}
            </button>
            <button
              type="button"
              className={`${styles.button} ${styles.buttonPrimary}`}
              onClick={saveLayout}
              disabled={!dirty}
            >
              💾 {g.saveLayout}
            </button>
            <button type="button" className={styles.button} onClick={resetLayout}>
              🔄 {g.resetLayout}
            </button>
            <button type="button" className={styles.button} onClick={() => setEditMode(false)}>
              {g.doneEditing}
            </button>
          </>
        ) : (
          <button type="button" className={styles.button} onClick={() => setEditMode(true)}>
            {g.editLayout}
          </button>
        )}
      </div>

      {toast && (
        <p role="status" className={styles.button} style={{ display: "inline-block", marginBottom: 12 }}>
          {toast}
        </p>
      )}

      {store.widgets.length === 0 ? (
        <p className={styles.empty}>{g.emptyCustom}</p>
      ) : (
        <ResponsiveGrid
          className="layout"
          layouts={layouts}
          breakpoints={{ lg: 996, md: 0 }}
          cols={{ lg: 12, md: 12 }}
          rowHeight={40}
          margin={[20, 20]}
          isDraggable={editMode}
          isResizable={editMode}
          draggableCancel="button, a, input, select"
          onLayoutChange={(current) => handleLayoutChange(current)}
        >
          {store.widgets.map((id) => {
            const def = WIDGET_BY_ID.get(id)!;
            const Widget = def.Component;
            return (
              <div key={id} className={styles.gridItem}>
                <div className={styles.gridItemWrap}>
                  {editMode && (
                    <button type="button" className={styles.removeButton} onClick={() => removeWidget(id)}>
                      {g.remove}
                    </button>
                  )}
                  <Widget />
                </div>
              </div>
            );
          })}
        </ResponsiveGrid>
      )}

      {addOpen && (
        <AddWidgetModal
          activeIds={store.widgets}
          onAdd={(id) => addWidget(id)}
          onClose={() => setAddOpen(false)}
        />
      )}
    </div>
  );
}

function AddWidgetModal({
  activeIds,
  onAdd,
  onClose,
}: {
  activeIds: string[];
  onAdd: (id: string) => void;
  onClose: () => void;
}) {
  const { t } = useLocale();
  const g = t.dashboard.grid;
  const [category, setCategory] = useState<"all" | WidgetCategory>("all");

  const available = WIDGETS.filter(
    (w) => !activeIds.includes(w.id) && (category === "all" || w.category === category),
  );

  const CATEGORIES: { id: "all" | WidgetCategory; labelKey: LabelKey }[] = [
    { id: "all", labelKey: "categoryAll" },
    { id: "system", labelKey: "categorySystem" },
    { id: "network", labelKey: "categoryNetwork" },
    { id: "pam-security", labelKey: "categoryPamSecurity" },
  ];

  return (
    <div className={styles.overlay} role="presentation" onClick={onClose}>
      <div className={styles.dialog} role="dialog" aria-modal="true" aria-label={g.addWidgetTitle} onClick={(e) => e.stopPropagation()}>
        <h3 className={styles.dialogTitle}>{g.addWidgetTitle}</h3>
        <div className={styles.categoryRow}>
          {CATEGORIES.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`${styles.categoryChip} ${category === c.id ? styles.categoryChipActive : ""}`}
              onClick={() => setCategory(c.id)}
            >
              {g[c.labelKey]}
            </button>
          ))}
        </div>
        {available.length === 0 ? (
          <p className={styles.empty}>{g.allWidgetsAdded}</p>
        ) : (
          <div className={styles.widgetList}>
            {available.map((w) => (
              <div key={w.id} className={styles.widgetRow}>
                <span className={styles.widgetName}>{g[w.labelKey]}</span>
                <button type="button" className={`${styles.button} ${styles.buttonPrimary}`} onClick={() => onAdd(w.id)}>
                  + {g.addWidget}
                </button>
              </div>
            ))}
          </div>
        )}
        <div className={styles.dialogActions}>
          <button type="button" className={styles.button} onClick={onClose}>
            {t.common.close}
          </button>
        </div>
      </div>
    </div>
  );
}

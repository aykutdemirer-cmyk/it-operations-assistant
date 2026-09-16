"use client";

import { useMemo, useState } from "react";

import {
  performVCenterVmPowerAction,
  type VCenterPowerAction,
  type VCenterPowerState,
  type VCenterVmSummary,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import { CreateTicketModal } from "../CreateTicketModal";
import styles from "./VCenterPanel.module.css";
import { powerBadgeClass, powerStateLabel } from "./vcenterBadges";
import { VMDetailModal } from "./VMDetailModal";

type Props = {
  vms: VCenterVmSummary[];
  canManagePower: boolean;
  onPowerActionDone: () => void;
};

// Faz 73 — VMware'in kendi cluster-altyapı VM'leri (vSphere Lifecycle
// Manager) her zaman bu önekle gelir — kullanıcının kendi iş yükü
// DEĞİL. Backend'den GİZLENMİYOR (hâlâ döndürülüyor), yalnızca
// varsayılan tabloda süzülüyor — "Sistem VM'leri" sekmesinden görülebilir.
const SYSTEM_VM_PREFIX = "vCLS-";

/** Faz 72/73 — VM listesi: arama/filtre, vCLS sistem VM ayrımı,
 * "İşlemler" sütunu (güç dropdown'u + bilet). Detay `VMDetailModal`'a
 * devredilir. */
export function VMListTable({ vms, canManagePower, onPowerActionDone }: Props) {
  const { token } = useAuth();
  const { t } = useLocale();
  const v = t.vcenter;

  const [search, setSearch] = useState("");
  const [powerFilter, setPowerFilter] = useState<VCenterPowerState | "">("");
  const [showSystemVms, setShowSystemVms] = useState(false);
  const [selectedVmId, setSelectedVmId] = useState<string | null>(null);
  const [ticketVm, setTicketVm] = useState<VCenterVmSummary | null>(null);
  const [pendingActionVmId, setPendingActionVmId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ vmId: string; message: string } | null>(null);

  const systemVmCount = useMemo(() => vms.filter((vm) => vm.name.startsWith(SYSTEM_VM_PREFIX)).length, [vms]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return vms.filter((vm) => {
      const isSystemVm = vm.name.startsWith(SYSTEM_VM_PREFIX);
      if (isSystemVm !== showSystemVms) return false;
      if (powerFilter && vm.power_state !== powerFilter) return false;
      if (!q) return true;
      return vm.name.toLowerCase().includes(q) || (vm.ip_address ?? "").toLowerCase().includes(q);
    });
  }, [vms, search, powerFilter, showSystemVms]);

  const selectedVm = vms.find((vm) => vm.id === selectedVmId);

  async function handleRowPowerAction(vm: VCenterVmSummary, action: VCenterPowerAction) {
    if (!token) return;
    setPendingActionVmId(vm.id);
    setRowError(null);
    try {
      await performVCenterVmPowerAction(token, vm.id, action);
      onPowerActionDone();
    } catch (err) {
      setRowError({ vmId: vm.id, message: err instanceof Error ? err.message : v.powerActionError });
    } finally {
      setPendingActionVmId(null);
    }
  }

  return (
    <>
      <div className={styles.toolbar}>
        <input
          className={styles.searchInput}
          type="text"
          placeholder={v.searchPlaceholder}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select className={styles.filterSelect} value={powerFilter} onChange={(e) => setPowerFilter(e.target.value as VCenterPowerState | "")}>
          <option value="">{v.allPowerStates}</option>
          <option value="POWERED_ON">{v.powerOn}</option>
          <option value="POWERED_OFF">{v.powerOff}</option>
          <option value="SUSPENDED">{v.powerSuspended}</option>
        </select>
        <div className={styles.vmScopeToggle}>
          <button
            type="button"
            className={!showSystemVms ? styles.vmScopeButtonActive : styles.vmScopeButton}
            onClick={() => setShowSystemVms(false)}
          >
            {v.userVms}
          </button>
          <button
            type="button"
            className={showSystemVms ? styles.vmScopeButtonActive : styles.vmScopeButton}
            onClick={() => setShowSystemVms(true)}
          >
            {v.systemVms} ({systemVmCount})
          </button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className={styles.noData}>{v.noVms}</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{v.columns.name}</th>
                <th>{v.columns.powerState}</th>
                <th>{v.columns.ipAddress}</th>
                <th>{v.columns.guestOs}</th>
                <th>{v.columns.allocation}</th>
                <th>{v.columns.actions}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((vm) => (
                <tr key={vm.id}>
                  <td>
                    <button type="button" className={styles.vmNameButton} onClick={() => setSelectedVmId(vm.id)}>
                      {vm.name}
                    </button>
                  </td>
                  <td>
                    <span className={`${styles.powerBadge} ${powerBadgeClass(styles, vm.power_state)}`}>
                      {powerStateLabel(v, vm.power_state)}
                    </span>
                  </td>
                  <td className={styles.mono}>{vm.ip_address ?? "—"}</td>
                  <td>{vm.guest_os ?? "—"}</td>
                  <td>
                    <span className={styles.allocationBadge}>
                      {vm.cpu_count ?? "—"} vCPU / {vm.memory_mb != null ? `${(vm.memory_mb / 1024).toFixed(1)} GB` : "—"}
                    </span>
                  </td>
                  <td>
                    <div className={styles.actions}>
                      {canManagePower && (
                        <select
                          className={styles.powerActionSelect}
                          aria-label={`${v.powerMenuLabel}: ${vm.name}`}
                          value=""
                          disabled={pendingActionVmId === vm.id}
                          onChange={(e) => {
                            const action = e.target.value as VCenterPowerAction;
                            if (action) handleRowPowerAction(vm, action);
                          }}
                        >
                          <option value="">⚡ {pendingActionVmId === vm.id ? t.common.loading : v.powerMenuLabel}</option>
                          <option value="start" disabled={vm.power_state === "POWERED_ON"}>
                            {v.powerStart}
                          </option>
                          <option value="guest_reboot" disabled={vm.power_state !== "POWERED_ON"}>
                            {v.powerGuestReboot}
                          </option>
                          <option value="reset" disabled={vm.power_state !== "POWERED_ON"}>
                            {v.powerReset}
                          </option>
                          <option value="stop" disabled={vm.power_state !== "POWERED_ON"}>
                            {v.powerStop}
                          </option>
                        </select>
                      )}
                      <button type="button" className={styles.actionButton} onClick={() => setTicketVm(vm)}>
                        🎫
                      </button>
                    </div>
                    {rowError?.vmId === vm.id && <p className={styles.formError}>{rowError.message}</p>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedVm && (
        <VMDetailModal
          vmId={selectedVm.id}
          vmName={selectedVm.name}
          canManagePower={canManagePower}
          onClose={() => setSelectedVmId(null)}
          onPowerActionDone={onPowerActionDone}
        />
      )}

      {ticketVm && (
        <CreateTicketModal
          onClose={() => setTicketVm(null)}
          onCreated={() => setTicketVm(null)}
          initialTitle={v.ticketPrefillTitle(ticketVm.name)}
          initialDescription={v.ticketPrefillDescriptionWithIp(ticketVm.name, ticketVm.id, ticketVm.ip_address)}
        />
      )}
    </>
  );
}

import type { VCenterPowerState } from "@/lib/api";

/** Faz 72 — güç durumu rozeti için CSS sınıfı + etiket. `styles`
 * çağıranın kendi CSS-module nesnesi (`VMListTable.tsx`/`VMDetailModal.
 * tsx` aynı `VCenterPanel.module.css`'i import ediyor, burada tekrar
 * import etmek yerine parametre olarak alınıyor — CSS Modules sınıf
 * adları yalnızca kendi component'inin import ettiği modülde geçerli). */
export function powerBadgeClass(styles: Record<string, string>, state: VCenterPowerState): string {
  if (state === "POWERED_ON") return styles.powerOn;
  if (state === "SUSPENDED") return styles.powerSuspended;
  return styles.powerOff;
}

export function powerStateLabel(v: { powerOn: string; powerOff: string; powerSuspended: string; powerUnknown: string }, state: VCenterPowerState): string {
  if (state === "POWERED_ON") return v.powerOn;
  if (state === "POWERED_OFF") return v.powerOff;
  if (state === "SUSPENDED") return v.powerSuspended;
  return v.powerUnknown;
}

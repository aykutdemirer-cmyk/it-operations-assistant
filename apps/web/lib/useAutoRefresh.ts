"use client";

import { useEffect, useRef } from "react";

/**
 * Arka planda sessizce (mevcut veriyi/loading state'ini sıfırlamadan)
 * periyodik olarak `refetch`'i çağırır — Dashboard/İzleme sayfalarının
 * "5-10 saniyede bir, layout sıçraması yapmadan güncellensin" isteği
 * için. İlk yükleme bu hook'un DIŞINDA, çağıran component'in kendi ilk
 * `useEffect`'i tarafından yapılır — bu yalnızca PERİYODİK tekrarları
 * tetikler. Sekme arka plandaysa (`document.hidden`) turu atlar —
 * kullanıcı bakmıyorken gereksiz istek göndermez.
 */
export function useAutoRefresh(refetch: () => void, intervalMs: number, enabled = true) {
  const refetchRef = useRef(refetch);

  useEffect(() => {
    refetchRef.current = refetch;
  }, [refetch]);

  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) return;
      refetchRef.current();
    }, intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, enabled]);
}

"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import type { Permission } from "@/lib/auth/permissions";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./RequirePermission.module.css";

/** Faz 47 — sistemdeki HER sayfayı sarmalayan genel route guard.
 * Giriş yapılmamışsa `/login?next=<mevcut yol>`'a yönlendirir; giriş
 * yapılmış ama `permission` yoksa (kullanıcının menüde görmediği bir
 * URL'yi elle yazması dahil — bkz. kullanıcının açık isteği) sayfayı
 * hiç render etmez, dürüst bir 403 ekranı gösterir. Asıl yetki kontrolü
 * PAM API'lerinde zaten backend'de (`require_permission(...)`); genel
 * sayfalar (Dashboard/Assets/...) için backend'e AUTH EKLENMEDİ (bkz.
 * docs/roadmap.md Faz 47 notu — bilinçli, belgelenmiş bir kapsam
 * sınırı), bu yüzden bu guard o sayfalar için TEK savunma katmanıdır. */
export function RequirePermission({ permission, children }: { permission: Permission; children: ReactNode }) {
  const { currentUser, loading } = useAuth();
  const { t } = useLocale();
  const router = useRouter();

  // GERÇEK bir üretim hatası: `router.replace(...)` önceden render
  // GÖVDESİNDE doğrudan çağrılıyordu ("Cannot update a component
  // (Router) while rendering a different component" — bu proje
  // `LoginForm.tsx`'te AYNI hatayı daha önce de yakalayıp düzeltmişti,
  // bkz. o düzeltmenin gerekçesi). Yönlendirme yan etkisi bir
  // `useEffect`'e taşındı; render gövdesi hâlâ (yönlendirme
  // TAMAMLANANA kadar) `null`/bekleme metni döner, ama artık render
  // SIRASINDA state DEĞİŞTİRMİYOR.
  useEffect(() => {
    if (!loading && !currentUser && typeof window !== "undefined") {
      router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
  }, [loading, currentUser, router]);

  if (loading) {
    return <p className={styles.status}>{t.common.loading}</p>;
  }

  if (!currentUser) {
    return <p className={styles.status}>{t.auth.signInRequired}</p>;
  }

  if (!currentUser.permissions.includes(permission)) {
    return (
      <div className={styles.forbidden}>
        <p className={styles.forbiddenCode}>403</p>
        <p className={styles.forbiddenTitle}>{t.auth.unauthorizedTitle}</p>
        <p className={styles.forbiddenText}>{t.auth.unauthorizedText}</p>
      </div>
    );
  }

  return <>{children}</>;
}

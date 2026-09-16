"use client";

import Link from "next/link";

import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AuthStatus.module.css";

/** Faz 46 — `TopHeader`'a eklenen minimal oturum göstergesi. Giriş
 * yapılmamışsa `/login`'e link; yapılmışsa kullanıcı adı + rol rozeti +
 * çıkış butonu. Uygulamanın geri kalanı KASITLI olarak bir login
 * duvarının arkasına ALINMADI (bkz. docs/roadmap.md Faz 46 — canlı,
 * aktif kullanılan bir sistemde riskli bir erişim değişikliği) — bu
 * gösterge yalnızca bilgilendirici, PAM sayfalarının kendisi gerçek
 * auth ile korunuyor. */
export function AuthStatus() {
  const { currentUser, logout } = useAuth();
  const { t } = useLocale();

  if (!currentUser) {
    return (
      <Link href="/login" className={styles.link}>
        {t.auth.loginTitle}
      </Link>
    );
  }

  return (
    <div className={styles.wrap}>
      <span className={styles.userBadge}>
        {currentUser.username}
        <span className={styles.roleTag}>{currentUser.role}</span>
      </span>
      <button
        type="button"
        className={styles.link}
        onClick={() => {
          logout();
          // `useRouter()` YERİNE tam sayfa yönlendirme — bu component
          // her sayfada (TopHeader) render edildiği için `next/
          // navigation`'ın app router context'i gerektirmesi test
          // ortamını gereksiz yere karmaşıklaştırırdı; çıkışın kendisi
          // zaten nadir/tam bir state sıfırlaması, hafif bir tam
          // yenileme kabul edilebilir.
          // eslint-disable-next-line @next/next/no-location-assign-relative-destination
          window.location.assign("/");
        }}
      >
        {t.auth.logout}
      </button>
    </div>
  );
}

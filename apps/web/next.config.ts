import type { NextConfig } from "next";

// Backend'in dev sunucusuyla AYNI makinede çalıştığı varsayımıyla —
// yalnızca `rewrites()` (sunucu tarafı proxy) için kullanılır, tarayıcıya
// hiç gönderilmez. `NEXT_PUBLIC_API_URL` set edilmişse (bkz. lib/api.ts)
// bu proxy'nin devreye girmesine gerek kalmaz.
const BACKEND_INTERNAL_URL = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

// Next.js dev sunucusu, başlatıldığı hostname (varsayılan: localhost)
// DIŞINDA bir origin'den gelen istekleri (dev-only `.next/static`
// asset'leri + HMR WebSocket'i dahil) güvenlik amacıyla 403 ile
// reddeder. Bu makine LAN üzerinden başka bir IP'den (ör. tarayıcı
// `http://10.0.213.30:3000` ile açıldığında) erişildiğinde bu origin'i
// de açıkça izin listesine eklemek gerekir — bkz. Next.js
// `allowedDevOrigins` dokümantasyonu.
const ADDITIONAL_DEV_ORIGINS = (process.env.NEXT_ALLOWED_DEV_ORIGINS ?? "10.0.213.30")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  // Setup & Deployment — Docker imajının `node_modules`'ın tamamını
  // değil, yalnızca gerçekten kullanılan bağımlılıkları içeren küçük
  // bir `.next/standalone` çıktısı üretmesi için (bkz. `apps/web/
  // Dockerfile`). Dev sunucusunun (`next dev`) davranışını etkilemez.
  output: "standalone",
  allowedDevOrigins: ADDITIONAL_DEV_ORIGINS,

  async rewrites() {
    // Tarayıcı hangi IP/hostname üzerinden Next dev sunucusuna
    // eriştiyse erişsin — `/api/*` istekleri her zaman AYNI origin'e
    // (same-origin, CORS gerektirmez) gider ve burada, sunucu
    // tarafında, backend'e proxy'lenir. `lib/api.ts`'teki `fetch`
    // çağrıları bu yüzden `NEXT_PUBLIC_API_URL` set edilmediği sürece
    // mutlak bir host DEĞİL, göreli `/api/...` yolu kullanır — "Backend:
    // Kontrol ediliyor..." durumunda takılı kalma sorununun kök nedeni
    // buydu (tarayıcı `localhost:8000`'i KENDİ makinesi sanıyordu).
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_INTERNAL_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;

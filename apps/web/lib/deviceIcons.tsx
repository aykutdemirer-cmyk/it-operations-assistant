import type { JSX } from "react";

/** Faz 38 — cihaz tipine göre gerçek SVG ikonlar. Önceki emoji tabanlı
 * gösterim (`❓` dahil "BİLİNMİYOR" etiketleriyle birlikte) yerine
 * geçer — `unknown` için de sakin, nötr bir ikon kullanılır (kırmızı/
 * alarm rengi DEĞİL, yalnızca "sınıflandırılamadı" anlamına gelir). */

type IconProps = { className?: string };

function Server({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3" y="4" width="18" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="3" y="14" width="18" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="7" cy="7" r="1" fill="currentColor" />
      <circle cx="7" cy="17" r="1" fill="currentColor" />
    </svg>
  );
}

function Workstation({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3" y="4" width="18" height="12" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M9 20h6M12 16v4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function Switch({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3" y="8" width="18" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M6.5 8v-2M10.5 8v-2M14.5 8v-2M18.5 8v-2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="6.5" cy="12" r="0.8" fill="currentColor" />
      <circle cx="10.5" cy="12" r="0.8" fill="currentColor" />
      <circle cx="14.5" cy="12" r="0.8" fill="currentColor" />
      <circle cx="18.5" cy="12" r="0.8" fill="currentColor" />
    </svg>
  );
}

function Firewall({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M9 12h6M12 9v6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function Router({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3" y="11" width="18" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M7 11c0-3 1.5-5 5-5s5 2 5 5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <circle cx="8" cy="14.5" r="0.8" fill="currentColor" />
      <circle cx="12" cy="14.5" r="0.8" fill="currentColor" />
    </svg>
  );
}

function AccessPoint({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="16" r="1.4" fill="currentColor" />
      <path d="M8.5 13a5 5 0 0 1 7 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M5.5 10a9 9 0 0 1 13 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function Printer({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="5" y="9" width="14" height="7" rx="1" stroke="currentColor" strokeWidth="1.6" />
      <path d="M7 9V4h10v5" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <rect x="7" y="15" width="10" height="5" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

function Camera({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3" y="8" width="13" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M16 11.5l5-2.5v8l-5-2.5" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <circle cx="9.5" cy="12.5" r="2" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

function Nas({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="5" y="3" width="14" height="18" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 8h8M8 13h8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="16" cy="17.5" r="1" fill="currentColor" />
    </svg>
  );
}

function NetworkDevice({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
      <path d="M3 12h18M12 3a13 13 0 0 1 0 18M12 3a13 13 0 0 0 0 18" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  );
}

function Unknown({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" strokeDasharray="2.5 2.5" />
      <path
        d="M10 9.5a2 2 0 1 1 3 1.7c-.7.5-1 .9-1 1.8"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <circle cx="12" cy="16" r="0.9" fill="currentColor" />
    </svg>
  );
}

function Gateway({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="1.7" />
      <path
        d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

const ICONS: Record<string, (props: IconProps) => JSX.Element> = {
  server: Server,
  workstation: Workstation,
  switch: Switch,
  firewall: Firewall,
  router: Router,
  access_point: AccessPoint,
  printer: Printer,
  camera: Camera,
  nas: Nas,
  network_device: NetworkDevice,
  unknown: Unknown,
};

export function DeviceIcon({ deviceType, className }: { deviceType: string; className?: string }) {
  const Icon = ICONS[deviceType] ?? Unknown;
  return <Icon className={className} />;
}

export function GatewayIcon({ className }: IconProps) {
  return <Gateway className={className} />;
}

import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
// Faz 59 — sürüklenebilir dashboard grid'i (react-grid-layout) için
// zorunlu global stiller. Kütüphane MIT lisanslı; tek bağımlılıkları
// react-draggable + react-resizable (ikisi de MIT), yeni bir güvenlik
// açığı EKLEMİYOR (bkz. `docs/roadmap.md` Faz 59).
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

import { Sidebar } from "@/components/Sidebar";
import { TopHeader } from "@/components/TopHeader";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { DashboardDataProvider } from "@/lib/DashboardDataProvider";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";
import styles from "./layout.module.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "IT Operations Assistant",
  description: "IT altyapı keşif ve yönetim platformu",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="tr" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body>
        <LocaleProvider>
          <ThemeProvider>
            <AuthProvider>
              <DashboardDataProvider>
                <div className={styles.shell}>
                  <Sidebar />
                  <div className={styles.content}>
                    <TopHeader />
                    {children}
                  </div>
                </div>
              </DashboardDataProvider>
            </AuthProvider>
          </ThemeProvider>
        </LocaleProvider>
      </body>
    </html>
  );
}

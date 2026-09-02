import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { Sidebar } from "@/components/Sidebar";
import { TopHeader } from "@/components/TopHeader";
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
            <DashboardDataProvider>
              <div className={styles.shell}>
                <Sidebar />
                <div className={styles.content}>
                  <TopHeader />
                  {children}
                </div>
              </div>
            </DashboardDataProvider>
          </ThemeProvider>
        </LocaleProvider>
      </body>
    </html>
  );
}

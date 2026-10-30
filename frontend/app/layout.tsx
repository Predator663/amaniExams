import type { Metadata, Viewport } from "next";
import { ReactNode } from "react";
import { SessionProvider } from "@/lib/session";
import SwRegister from "@/components/SwRegister";
import MaintenanceGate from "@/components/MaintenanceGate";
import "./globals.css";

export const metadata: Metadata = {
  title: "Amani Exams",
  description: "Amani Girls Secondary School online examinations",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "Amani Exams", statusBarStyle: "default" },
  icons: { icon: "/icons/icon-192.png", apple: "/icons/apple-touch-icon.png" },
};
export const viewport: Viewport = { themeColor: "#0b6b4f", width: "device-width", initialScale: 1, viewportFit: "cover" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SessionProvider>{children}</SessionProvider>
        <MaintenanceGate />
        <SwRegister />
      </body>
    </html>
  );
}

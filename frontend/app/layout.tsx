import type { Metadata } from "next";

import { AuthProvider } from "@/components/AuthProvider";
import { Sidebar } from "@/components/Sidebar";

import "./globals.css";

export const metadata: Metadata = {
  title: "AdOps Signal",
  description: "AI agent for CTV and addressable TV campaign troubleshooting"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <div className="min-h-screen bg-surface text-ink">
            <Sidebar />
            <main className="min-h-screen px-4 pb-5 pt-20 md:ml-64 md:px-8 md:py-5 lg:px-10">{children}</main>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}

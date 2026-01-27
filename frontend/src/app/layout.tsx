import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ToastProvider } from "@/components/ui/toast";

const inter = Inter({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Nouva Dashboard - AI Agent Platform",
  description: "Painel de métricas e monitoramento de agentes de IA da Nouva",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" className="dark">
      <body className={`${inter.variable} antialiased bg-slate-950`}>
        <ToastProvider>
          {children}
        </ToastProvider>
      </body>
    </html>
  );
}


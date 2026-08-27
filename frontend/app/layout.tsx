"use client";

import "./globals.css";
import Sidebar from "@/components/Sidebar";
import ServiceWorkerRegister from "@/components/ServiceWorkerRegister";
import SessionProvider from "@/components/SessionProvider";
import VersionCheck from "@/components/VersionCheck";
import { EstadoProvider } from "@/hooks/useEstado";
import { usePathname } from "next/navigation";
import ToastContainer from "@/components/Toast";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const pathname = usePathname();
  
  // Verifica se a página atual é a de login ou raiz pública
  const isLoginPage = pathname === "/" || pathname === "/login" || pathname === "/login.html" || pathname === "/forgot-password" || pathname === "/reset-password";

  return (
    <html lang="pt-BR" className="dark" suppressHydrationWarning>
      <body className="antialiased selection-none bg-slate-950 text-white">
        <ToastContainer />
        <ServiceWorkerRegister />
        <VersionCheck />
        <EstadoProvider>
          <SessionProvider>
            <div className="flex min-h-screen w-full relative">
              
              {/* A Sidebar só renderiza se NÃO for página de login/pública */}
              {!isLoginPage && <Sidebar />}
              
              {/* Container principal flexível */}
              <main className="flex-1 w-full min-h-screen transition-all duration-300 ease-in-out relative z-10">
                {children}
              </main>
            </div>
          </SessionProvider>
        </EstadoProvider>
      </body>
    </html>
  );
}
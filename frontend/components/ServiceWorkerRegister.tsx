"use client";

import { useEffect } from "react";

export default function ServiceWorkerRegister() {
  useEffect(() => {
    // Garante que o código só rode no navegador e se o navegador suportar SW
    if (typeof window !== "undefined" && "serviceWorker" in navigator) {
      window.addEventListener("load", () => {
        navigator.serviceWorker
          .register("/sw.js")
          .then((registration) => {
            console.log("⚙️ RDE Service Worker registrado com sucesso:", registration.scope);
          })
          .catch((error) => {
            console.error("❌ Erro ao registrar o Service Worker:", error);
          });
      });
    }
  }, []);

  return null;
}
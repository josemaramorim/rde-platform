"use client";

import { useEffect } from "react";

export default function HomePage() {
  useEffect(() => {
    if (typeof window !== "undefined") {
      const token = sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token");
      if (token) {
        window.location.replace("/dashboard");
      } else {
        window.location.replace("/login");
      }
    }
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-slate-400 font-medium text-sm">Carregando RDE...</p>
      </div>
    </div>
  );
}
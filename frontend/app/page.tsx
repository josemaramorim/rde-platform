"use client";

import { useEffect } from "react";

export default function Home() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    const token = sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token");
    window.location.replace(token ? "/dashboard" : "/login");
  }, []); // Sem dependências — executa UMA vez apenas

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Redirecionando...</p>
      </div>
    </div>
  );
}
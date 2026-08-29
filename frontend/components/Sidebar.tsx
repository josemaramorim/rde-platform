"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo } from "react";
import { useEstado } from "@/hooks/useEstado";

export default function Sidebar() {
  const pathname = usePathname();
  const { estado } = useEstado();
  const isAdmin = estado?.is_admin ?? false;

  const isLiberado = estado?.liberado || isAdmin;

  // Memoriza os itens para evitar recriação de array a cada render
  const menuItems = useMemo(() => {
    const baseItems = [
      { name: "Dashboard", href: "/dashboard", icon: "📊" },
      { name: "Planilha", href: "/planilha", icon: "📈" },
      { name: "Estatísticas", href: "/estatisticas", icon: "📉" },
      { name: "Risco", href: "/risco", icon: "🛡️" },
      { name: "Carteira", href: "/carteira", icon: "💳" },
      { name: "Setup", href: "/setup", icon: "🔌" },
      { name: "Configurações", href: "/configuracao", icon: "⚙️" },
      { name: "Perfil", href: "/perfil", icon: "👤" },
    ];

    if (isAdmin) {
      baseItems.push({ name: "Admin", href: "/admin", icon: "👑" });
    }

    return baseItems;
  }, [isAdmin]);

  // Bloqueia a exibição em páginas públicas ou de autenticação
  if (
    pathname === "/" || 
    pathname === "/login" || 
    pathname.startsWith("/reset-password") || 
    pathname.startsWith("/atualizar")
  ) {
    return null;
  }

  return (
    <aside className="w-64 glass border-r border-slate-800/40 flex flex-col sticky top-0 h-screen select-none z-50">
      {/* Brand/Header */}
      <Link href="/" className="p-8 block hover:opacity-80 transition-opacity">
        <h1 className="text-2xl font-black text-white tracking-widest text-gradient">RDE</h1>
        <p className="text-[10px] text-slate-500 uppercase tracking-[0.3em] font-bold mt-1">
          {isAdmin ? "Administrador" : isLiberado ? "Cliente VIP" : "Pendente de Liberação"}
        </p>
      </Link>

      {/* Navegação Principal */}
      <nav className="flex-1 px-4 space-y-1">
        {menuItems.map((item) => {
          const isActive = pathname === item.href;
          const isAllowedForPending = item.href === "/setup" || item.href === "/perfil" || item.href === "/carteira";
          const isLocked = !isLiberado && !isAllowedForPending;

          return (
            <Link
              key={item.name}
              href={isLocked ? "/setup" : item.href}
              className={`flex items-center justify-between px-4 py-3 rounded-xl text-sm font-semibold transition-all cursor-pointer ${
                isLocked
                  ? "opacity-50 text-slate-500 hover:bg-slate-900/40 cursor-not-allowed"
                  : isActive
                  ? "bg-blue-600 text-white shadow-lg glow-blue"
                  : "text-slate-400 hover:bg-slate-800/60 hover:text-white"
              }`}
            >
              <div className="flex items-center gap-3">
                <span className="text-base">{item.icon}</span>
                {item.name}
              </div>
              {isLocked && <span className="text-xs text-amber-500 font-bold">🔒</span>}
            </Link>
          );
        })}

        {/* Botão de Suporte Externo */}
        <a
          href="https://t.me/AmigosTraderBrasil"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 px-4 py-3 bg-slate-950/40 border border-slate-800/60 hover:bg-blue-600 rounded-xl text-slate-400 hover:text-white transition-all text-sm font-bold group mt-4 cursor-pointer"
        >
          <span className="group-hover:scale-110 transition-transform text-base">💬</span>
          Suporte Telegram
        </a>
      </nav>

      {/* Rodapé de Logout */}
      <div className="p-4 border-t border-slate-900/40">
        <button
          onClick={() => {
            sessionStorage.clear();
            localStorage.removeItem("rde_token");
            localStorage.removeItem("rde_email");
            localStorage.removeItem("rde_pass");
            localStorage.removeItem("rde_role");
            localStorage.removeItem("rde_estado");
            window.location.href = "/login";
          }}
          className="flex items-center gap-3 px-4 py-3 text-slate-500 hover:text-red-400 transition-colors text-sm font-bold w-full cursor-pointer rounded-xl hover:bg-red-500/5"
        >
          <span className="text-base">🚪</span> Sair da Operação
        </button>
      </div>
    </aside>
  );
}
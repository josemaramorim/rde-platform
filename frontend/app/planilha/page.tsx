"use client";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { useEstado } from "@/hooks/useEstado";
import { API_URL } from "@/lib/constants";

interface BrokerState {
  balance: number;
  mode: string;
  is_demo: boolean;
  connected: boolean;
  loading: boolean;
  error: string;
}

interface PlanilhaRow {
  dia: number;
  base: number;
  meta: number;
  sessao: number;
  final: number;
  pct: number;
  batida: boolean;
}

const BROKERS = [
  { id: "iqoption",     label: "IQ Option",     icon: "🟢" },
  { id: "quotex",       label: "Quotex",         icon: "🔵" },
  { id: "pocketoption", label: "Pocket Option",  icon: "🟣" },
  { id: "deriv",        label: "Deriv / Binary", icon: "🔷" },
];

const fmt = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const getToken = () => typeof window !== "undefined" ? (sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token") || "") : "";

const BROKER_DEFAULT: BrokerState = { balance: 0, mode: "-", is_demo: true, connected: false, loading: false, error: "" };

export default function PlanilhaPage() {
  const router = useRouter();
  const { estado, salvarCapital, setBrokerConectado, recarregar } = useEstado();

  const [brokers, setBrokers] = useState<Record<string, BrokerState>>({
    iqoption:     { ...BROKER_DEFAULT },
    quotex:       { ...BROKER_DEFAULT },
    pocketoption: { ...BROKER_DEFAULT },
    deriv:        { ...BROKER_DEFAULT },
  });
  const [modos, setModos] = useState<Record<string, boolean>>({
    iqoption: true, quotex: true, pocketoption: true, deriv: true,
  });
  const [progresso, setProgresso] = useState<Record<number, boolean>>({});
  const [capitalInput, setCapitalInput] = useState("100");

  // Verificar termo de risco
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    fetch(`${API_URL}/risk-term/status`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(5000),
    })
      .then(r => r.json())
      .then(data => { if (!data.accepted) router.push("/termo-risco"); })
      .catch(() => {});
  }, []);

  // Sincronizar saldo do estado global (atualizado pelo useEstado a cada 30s)
  useEffect(() => {
    if (estado?.broker_ativo) {
      setBrokers(prev => ({
        ...prev,
        [estado.broker_ativo]: {
          ...prev[estado.broker_ativo],
          balance: estado.broker_balance || prev[estado.broker_ativo]?.balance || 0,
          mode: estado.broker_mode || prev[estado.broker_ativo]?.mode || "Demo",
          is_demo: estado.broker_is_demo ?? prev[estado.broker_ativo]?.is_demo ?? true,
          connected: estado.broker_connected ?? prev[estado.broker_ativo]?.connected ?? false,
        } as BrokerState,
      }));
    }
  }, [estado?.broker_balance, estado?.broker_ativo, estado?.broker_connected, estado?.broker_is_demo, estado?.broker_mode]);

  // Restaurar estado salvo ao carregar
  useEffect(() => {
    const saved = localStorage.getItem("rde_planilha_progresso");
    if (saved) {
      try { setProgresso(JSON.parse(saved)); } catch { /* corrupted */ }
    }

    const savedBrokers = localStorage.getItem("rde_brokers_conectados");
    if (savedBrokers) {
      try {
        const parsed = JSON.parse(savedBrokers);
        setBrokers(prev => {
          const novo = { ...prev };
          Object.keys(parsed).forEach(k => {
            if (novo[k]) novo[k] = { ...novo[k]!, ...parsed[k] } as BrokerState;
          });
          return novo;
        });
      } catch { /* silencioso */ }
    }

    // Carregar progresso do banco
    const token = getToken();
    if (token) {
      fetch(`${API_URL}/planilha/progress`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(5000),
      })
        .then(r => r.json())
        .then(data => {
          if (data.progress) {
            const dbProgress: Record<number, boolean> = {};
            Object.entries(data.progress).forEach(([day, info]: [string, any]) => {
              dbProgress[parseInt(day)] = info.completed;
            });
            setProgresso(prev => {
              const merged = { ...prev, ...dbProgress };
              localStorage.setItem("rde_planilha_progresso", JSON.stringify(merged));
              return merged;
            });
          }
        })
        .catch(() => {});
    }
  }, []);

  // Sincronizar capital com context com tratamento seguro contra undefined
  useEffect(() => {
    if (!estado) return;
    const cap = estado.broker_connected && estado.broker_balance > 0
      ? estado.broker_balance
      : (estado.capital_planilha || 100);
    setCapitalInput(cap.toFixed(2));
  }, [estado?.broker_balance, estado?.broker_connected, estado?.capital_planilha]);

  const capitalInicial = estado?.broker_connected && estado?.broker_balance > 0
    ? estado.broker_balance
    : (estado?.capital_planilha || 100);

  const handleConectar = useCallback(async (brokerId: string) => {
    const token = getToken();
    if (!token) return;
    const is_demo = modos[brokerId] ?? true;

    setBrokers(prev => ({ ...prev, [brokerId]: { ...prev[brokerId]!, loading: true, error: "" } as BrokerState }));

    try {
      const urlBase = API_URL || "";
      const urlFormatada = urlBase.endsWith("/") ? urlBase.slice(0, -1) : urlBase;

      // Atualizar modo
      await fetch(`/broker/toggle-mode`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ broker_name: brokerId, is_demo }),
      });

      // Testar conexão e buscar saldo
      const res = await fetch(`/broker/test-connection`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ broker_name: brokerId }),
        signal: AbortSignal.timeout(20000),
      });
      const data = await res.json();

      if (data.status === "ok") {
        const bal = parseFloat(data.balance.toFixed(2));
        const novoEstado: BrokerState = {
          balance: bal, mode: data.mode, is_demo,
          connected: true, loading: false, error: "",
        };
        setBrokers(prev => ({ ...prev, [brokerId]: novoEstado }));

        const savedBrokers = JSON.parse(localStorage.getItem("rde_brokers_conectados") || "{}");
        savedBrokers[brokerId] = novoEstado;
        localStorage.setItem("rde_brokers_conectados", JSON.stringify(savedBrokers));

        // Ativar como broker principal no servidor
        await fetch("/broker/activate", {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ broker_name: brokerId }),
        });

        // Ativar como broker principal no context
        if (setBrokerConectado) setBrokerConectado(brokerId, bal, data.mode, is_demo);
        if (salvarCapital) salvarCapital(bal);
        if (recarregar) recarregar();
      } else {
        setBrokers(prev => ({ ...prev, [brokerId]: { ...prev[brokerId]!, loading: false, error: data.message || "Falha na conexão" } as BrokerState }));
      }
    } catch {
      setBrokers(prev => ({ ...prev, [brokerId]: { ...prev[brokerId]!, loading: false, error: "Erro de conexão" } as BrokerState }));
    }
  }, [modos, setBrokerConectado, salvarCapital]);

  const handleDesconectar = useCallback((brokerId: string) => {
    setBrokers(prev => ({ ...prev, [brokerId]: { ...BROKER_DEFAULT } }));

    const savedBrokers = JSON.parse(localStorage.getItem("rde_brokers_conectados") || "{}");
    delete savedBrokers[brokerId];
    localStorage.setItem("rde_brokers_conectados", JSON.stringify(savedBrokers));

    if (estado?.broker_ativo === brokerId) {
      if (setBrokerConectado) setBrokerConectado("", 0, "-", true);
      localStorage.removeItem("rde_planilha_balance");
      localStorage.removeItem("rde_planilha_mode");
      localStorage.removeItem("rde_planilha_broker");
    }
    if (recarregar) recarregar();
  }, [estado?.broker_ativo, setBrokerConectado, recarregar]);

  const handleAtivar = useCallback(async (brokerId: string) => {
    const b = brokers[brokerId];
    if (!b?.connected) return;
    const token = getToken();
    try {
      await fetch("/broker/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ broker_name: brokerId }),
      });
    } catch { /* silencioso */ }
    if (setBrokerConectado) setBrokerConectado(brokerId, b.balance, b.mode, b.is_demo);
    if (salvarCapital) salvarCapital(b.balance);
    if (recarregar) recarregar();
  }, [brokers, setBrokerConectado, salvarCapital, recarregar]);

  const toggleDia = (dia: number) => {
    const novo = { ...progresso, [dia]: !progresso[dia] };
    setProgresso(novo);
    localStorage.setItem("rde_planilha_progresso", JSON.stringify(novo));

    // Salvar no banco
    const token = getToken();
    if (token) {
      const row = planilhaData[dia - 1];
      fetch(`${API_URL}/planilha/mark-day`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          day_number: dia,
          completed: novo[dia] || false,
          capital_base: row?.base || 0,
          daily_profit: row?.meta || 0,
        }),
        signal: AbortSignal.timeout(3000),
      }).catch(() => {});
    }
  };

  const resetProgresso = () => {
    if (!confirm("Deseja realmente apagar todo o progresso da planilha?")) return;
    setProgresso({});
    localStorage.removeItem("rde_planilha_progresso");
  };

  const handleCapitalManual = () => {
    const val = parseFloat(capitalInput) || 100;
    if (salvarCapital) salvarCapital(val);
  };

  const diasBatidos = Object.values(progresso).filter(Boolean).length;
  const diaAtual = Math.min(diasBatidos + 1, 200);

  const planilhaData = useMemo<PlanilhaRow[]>(() => {
    const rows: PlanilhaRow[] = [];
    let cap = capitalInicial;
    for (let dia = 1; dia <= 200; dia++) {
      const meta = cap * 0.03;
      const sessao = cap * 0.01;
      const final = cap + meta;
      rows.push({
        dia, base: cap, meta, sessao, final,
        pct: Math.round(((final - capitalInicial) / capitalInicial) * 100),
        batida: progresso[dia] || false,
      });
      cap = final;
    }
    return rows;
  }, [capitalInicial, progresso]);

  const rowAtual = planilhaData[diaAtual - 1];

  return (
    <div className="min-h-screen p-6 md:p-10 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 overflow-x-hidden">
      <header className="mb-8">
        <h1 className="text-3xl font-black text-white tracking-tight">Planilha de Gerenciamento</h1>
        <p className="text-slate-500 mt-2 font-light text-sm">
          Conecte sua corretora · Escolha Demo ou Real · Sincronização automática de banca integrada.
        </p>
      </header>

      {/* Cards de corretoras */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        {BROKERS.map(b => {
          const bs = brokers[b.id] ?? BROKER_DEFAULT;
          const conectadoContexto = estado?.brokers_conectados?.[b.id]?.connected;
          const isAtivo = (estado?.broker_ativo === b.id && estado?.broker_connected) || conectadoContexto === true;

          return (
            <div key={b.id} className={`bg-slate-900/60 backdrop-blur-md rounded-2xl p-5 border transition-all ${isAtivo ? "border-emerald-500/40 bg-emerald-500/5" : bs.connected ? "border-blue-500/20 bg-blue-500/5" : "border-slate-800/80"}`}>

              {/* Header */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{b.icon}</span>
                  <p className="text-white font-black text-sm">{b.label}</p>
                </div>
                <span className={`w-2.5 h-2.5 rounded-full ${isAtivo ? "bg-emerald-500 animate-pulse" : bs.connected ? "bg-blue-400" : bs.loading ? "bg-yellow-500 animate-pulse" : "bg-slate-700"}`}></span>
              </div>

              {/* Saldo */}
              <div className="mb-4 min-h-[52px]">
                {bs.loading ? (
                  <p className="text-yellow-400 text-xs font-bold animate-pulse">Conectando...</p>
                ) : bs.error ? (
                  <p className="text-rose-400 text-xs font-bold">{bs.error}</p>
                ) : bs.connected ? (
                  <>
                    <p className={`text-2xl font-black ${isAtivo ? "text-emerald-400" : "text-blue-400"}`}>{fmt(bs.balance)}</p>
                    <p className="text-[10px] text-slate-500 uppercase tracking-widest mt-1">{bs.mode}</p>
                    {isAtivo && <p className="text-[9px] text-emerald-400 font-bold mt-1">● Ativo na planilha</p>}
                  </>
                ) : (
                  <p className="text-slate-600 text-xs font-light">Não conectado</p>
                )}
              </div>

              {/* Modo Demo / Real */}
              {!bs.connected && (
                <div className="flex gap-1 p-1 bg-slate-950/50 border border-slate-800 rounded-xl mb-3">
                  <button
                    onClick={() => setModos(prev => ({ ...prev, [b.id]: true }))}
                    className={`flex-1 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${modos[b.id] !== false ? "bg-slate-800 text-white border border-slate-700/50" : "text-slate-500"}`}
                  >
                    Demo
                  </button>
                  <button
                    onClick={() => setModos(prev => ({ ...prev, [b.id]: false }))}
                    className={`flex-1 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${modos[b.id] === false ? "bg-rose-600/20 text-rose-400 border border-rose-500/30" : "text-slate-500"}`}
                  >
                    Real
                  </button>
                </div>
              )}

              {/* Botões */}
              {bs.connected ? (
                <div className="grid grid-cols-2 gap-2">
                  {!isAtivo && (
                    <button
                      onClick={() => handleAtivar(b.id)}
                      className="py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest bg-emerald-600 hover:bg-emerald-500 text-white transition-all shadow-md"
                    >
                      Usar
                    </button>
                  )}
                  <button
                    onClick={() => handleDesconectar(b.id)}
                    className={`py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 transition-all ${!isAtivo ? "" : "col-span-2"}`}
                  >
                    Desconectar
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => handleConectar(b.id)}
                  disabled={bs.loading}
                  className="w-full py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-40 transition-all shadow-md"
                >
                  {bs.loading ? "Conectando..." : "Conectar"}
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Visão de Metas Diárias */}
      {rowAtual && (
        <div className="bg-blue-600/5 border border-blue-500/10 backdrop-blur-md rounded-2xl p-6 mb-6">
          <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
            <p className="text-blue-400 text-[10px] font-black uppercase tracking-widest">
              Hoje — {diaAtual}º Dia · {diasBatidos}/200 dias batidos
            </p>
            {estado?.broker_connected && (
              <p className="text-[10px] text-emerald-400 font-black uppercase tracking-widest">
                {BROKERS.find(b => b.id === estado.broker_ativo)?.label} · {estado.broker_mode}
              </p>
            )}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div><p className="text-slate-500 text-[10px] uppercase tracking-widest mb-1">Capital Base</p><p className="text-white font-black text-lg">{fmt(rowAtual.base)}</p></div>
            <div><p className="text-slate-500 text-[10px] uppercase tracking-widest mb-1">Meta (3%)</p><p className="text-emerald-400 font-black text-lg">{fmt(rowAtual.meta)}</p></div>
            <div><p className="text-slate-500 text-[10px] uppercase tracking-widest mb-1">Por Sessão (1%)</p><p className="text-blue-400 font-black text-lg">3x {fmt(rowAtual.sessao)}</p></div>
            <div><p className="text-slate-500 text-[10px] uppercase tracking-widest mb-1">Capital Final</p><p className="text-white font-black text-lg">{fmt(rowAtual.final)}</p></div>
          </div>
        </div>
      )}

      {/* Controles Manuais */}
      <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-5 mb-6 flex flex-wrap items-end gap-4">
        <div>
          <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Capital Manual (R$)</p>
          <div className="flex gap-2">
            <input 
              type="number" 
              value={capitalInput} 
              onChange={e => setCapitalInput(e.target.value)}
              className="bg-slate-950/50 border border-slate-800 text-white rounded-xl px-4 py-2 w-32 outline-none focus:ring-2 focus:ring-blue-500/40 font-bold text-sm" 
            />
            <button 
              onClick={handleCapitalManual}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-black rounded-xl text-xs uppercase tracking-widest transition-all"
            >
              Aplicar
            </button>
          </div>
        </div>
        <button 
          onClick={resetProgresso}
          className="px-4 py-2 border border-rose-500/20 text-rose-400 hover:bg-rose-500/10 rounded-xl text-xs font-black uppercase tracking-widest transition-all ml-auto"
        >
          Limpar Progresso
        </button>
      </div>

      {/* Tabela Progressiva */}
      <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl overflow-hidden">
        <div className="max-h-[600px] overflow-y-auto">
          <table className="w-full text-left border-collapse">
            <thead className="sticky top-0 bg-slate-950/90 backdrop-blur-md z-10">
              <tr>
                {["Dia", "Capital Base", "Meta (3%)", "Sessão (1%)", "Capital Final", "Acum.", "Ação"].map(h => (
                  <th key={h} className="px-5 py-4 text-[10px] font-black uppercase tracking-widest text-slate-500 border-b border-slate-800/80">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {planilhaData.map(row => (
                <tr key={row.dia} className={`border-b border-slate-800/40 transition-colors ${row.batida ? "bg-emerald-500/5" : row.dia === diaAtual ? "bg-blue-500/5" : "hover:bg-slate-900/20"}`}>
                  <td className="px-5 py-3.5">
                    <span className={`font-black text-sm ${row.dia === diaAtual ? "text-blue-400" : row.batida ? "text-emerald-400" : "text-white"}`}>
                      {row.dia === diaAtual ? "📍 " : ""}{row.dia}º
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-slate-300 text-sm">{fmt(row.base)}</td>
                  <td className="px-5 py-3.5 text-emerald-400 font-black text-sm">{fmt(row.meta)}</td>
                  <td className="px-5 py-3.5 text-blue-400 text-sm">3x {fmt(row.sessao)}</td>
                  <td className="px-5 py-3.5 text-white font-bold text-sm">{fmt(row.final)}</td>
                  <td className="px-5 py-3.5">
                    <span className="px-2 py-0.5 bg-slate-800 text-slate-400 text-[10px] font-black rounded border border-slate-700/30">+{row.pct}%</span>
                  </td>
                  <td className="px-5 py-3.5">
                    <button 
                      onClick={() => toggleDia(row.dia)}
                      className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${row.batida ? "bg-emerald-500 text-slate-950 font-bold shadow-md" : "border border-slate-700 text-slate-500 hover:border-emerald-500/40 hover:text-emerald-400"}`}
                    >
                      {row.batida ? "Batida" : "Marcar"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
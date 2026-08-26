"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useEstado } from "@/hooks/useEstado";
import { API_URL, formatMoney, Currency } from "@/lib/constants";

export default function RiscoPage() {
  const router = useRouter();
  const { estado, salvar } = useEstado();
  const currency = (estado.currency || "USD") as Currency;
  const fmt = (v: number) => formatMoney(v, currency);
  const getToken = () => sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token") || "";

  const [stopLoss, setStopLoss] = useState(estado.stop_loss_pct ?? 5.0);
  const [meta, setMeta]         = useState(estado.daily_meta_pct ?? 3.0);
  const [stake, setStake]       = useState(estado.stake ?? 1.0);
  const [gale, setGale]         = useState(2.1);
  const [maxGales, setMaxGales] = useState(2);
  const [autoLockMeta, setAutoLockMeta] = useState(estado.auto_lock_meta ?? false);
  const [saved, setSaved]       = useState(false);
  const [saveError, setSaveError] = useState(false);
  const [loading, setLoading]   = useState(false);
  const [liveData, setLiveData] = useState<any>(null);

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

  // Sincronizar com context quando carregar
  useEffect(() => {
    setStopLoss(estado.stop_loss_pct ?? 5.0);
    setMeta(estado.daily_meta_pct ?? 3.0);
    setStake(estado.stake ?? 1.0);
    setAutoLockMeta(estado.auto_lock_meta ?? false);
  }, [estado.stop_loss_pct, estado.daily_meta_pct, estado.stake, estado.auto_lock_meta]);

  // Carregar dados ao vivo
  useEffect(() => {
    const token = getToken();
    if (!token) return;

    fetch(`/dashboard/live`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(4000),
    })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setLiveData(d); })
      .catch(() => {});
  }, []);

  const balance = estado.broker_connected && estado.broker_balance > 0
    ? estado.broker_balance
    : (estado.capital_planilha || 100);

  const balanceSource = estado.broker_connected && estado.broker_balance > 0
    ? estado.broker_ativo
    : "Planilha";

  const handleSalvar = async () => {
    setLoading(true);
    setSaveError(false);
    const ok = await salvar({ stop_loss_pct: stopLoss, daily_meta_pct: meta, stake, auto_lock_meta: autoLockMeta });
    if (ok) {
      setSaved(true);
      setSaveError(false);
      setTimeout(() => setSaved(false), 3000);
    } else {
      setSaveError(true);
      setTimeout(() => setSaveError(false), 4000);
    }
    setLoading(false);
  };

  // Cálculos corrigidos e otimizados da progressão de Gale
  const exposicao = (() => {
    let total = stake;
    for (let i = 1; i <= maxGales; i++) {
      total += stake * Math.pow(gale, i);
    }
    return total;
  })();

  const stopValor   = balance * (stopLoss / 100);
  const metaValor   = balance * (meta / 100);
  const entradaSeg  = metaValor / 3;
  const ciclosStop  = Math.floor(stopValor / (exposicao || 1));
  const safetyScore = Math.min(100, Math.max(0, Math.round((ciclosStop / 5) * 100)));

  const lucroPct = liveData?.profit_pct ?? 0;
  const perdaPct = liveData ? Math.max(0, ((liveData.initial_balance - liveData.balance) / (liveData.initial_balance || 1)) * 100) : 0;
  const travado  = lucroPct >= meta || perdaPct >= stopLoss;

  return (
    <div className="min-h-screen p-6 md:p-10 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 overflow-x-hidden">
      <header className="mb-8">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <h1 className="text-4xl font-black text-white tracking-tight text-gradient">Controle de Risco</h1>
            <p className="text-slate-400 mt-2 font-light text-sm">Algoritmo de proteção · Sobrevivência do capital</p>
          </div>
          {estado?.broker_ativo && estado.broker_ativo !== "-" && (
            <div className={`px-4 py-2 rounded-xl text-xs font-black uppercase tracking-widest ${
              estado?.broker_connected
                ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-400"
                : "bg-slate-800/50 border border-slate-700 text-slate-400"
            }`}>
              {estado?.broker_connected ? "🟢" : "🔴"} {estado.broker_ativo} ({estado?.broker_mode || "-"})
              <span className="ml-2 text-[10px] font-mono opacity-70">{fmt(balance)}</span>
            </div>
          )}
        </div>
      </header>

      {/* Status ao vivo */}
      {liveData && (
        <div className={`p-4 rounded-2xl mb-6 border flex items-center justify-between gap-4 transition-all ${travado ? "bg-rose-500/10 border-rose-500/30" : "bg-emerald-500/10 border-emerald-500/30"}`}>
          <div>
            <p className={`font-black text-sm ${travado ? "text-rose-400" : "text-emerald-400"}`}>
              {travado
                ? perdaPct >= stopLoss ? `STOP LOSS atingido — ${perdaPct.toFixed(1)}% de perda` : `META atingida — ${lucroPct.toFixed(1)}% de lucro`
                : `Operando — Lucro: ${lucroPct.toFixed(1)}% / Perda: ${perdaPct.toFixed(1)}%`}
            </p>
            <p className="text-slate-500 text-xs mt-1">
              {liveData.broker && liveData.broker !== "-" && (
                <span className="text-slate-400 font-bold">{liveData.broker} · </span>
              )}
              Saldo: {fmt(liveData.balance)} · Gale atual: {liveData.gale_level}G · Stake: {fmt(liveData.current_stake)}
            </p>
          </div>
          <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase ${travado ? "bg-rose-500/20 text-rose-400" : "bg-emerald-500/20 text-emerald-400"}`}>
            {travado ? "TRAVADO" : "LIVRE"}
          </span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-8 shadow-2xl">
            <h2 className="text-sm font-black text-white uppercase tracking-widest mb-6">Configuração do Algoritmo</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Meta Diária (%)</label>
                <input type="number" value={meta} min={0.5} max={10} step={0.5}
                  onChange={e => setMeta(parseFloat(e.target.value) || 0)}
                  className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl p-4 outline-none focus:ring-2 focus:ring-emerald-500/40 text-sm font-medium" />
                <p className="text-[9px] text-emerald-400 font-bold">= {fmt(metaValor)} no saldo atual</p>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Stop Loss Diário (%)</label>
                <input type="number" value={stopLoss} min={1} max={20} step={0.5}
                  onChange={e => setStopLoss(parseFloat(e.target.value) || 0)}
                  className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl p-4 outline-none focus:ring-2 focus:ring-rose-500/40 text-sm font-medium" />
                <p className="text-[9px] text-rose-400 font-bold">= {fmt(stopValor)} no saldo atual</p>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Stake Inicial ({currency === "BRL" ? "R$" : "$"})</label>
                <input type="number" value={stake} min={0.5} step={0.5}
                  onChange={e => setStake(parseFloat(e.target.value) || 0)}
                  className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl p-4 outline-none focus:ring-2 focus:ring-blue-500/40 text-sm font-medium" />
                <p className="text-[9px] text-blue-400 font-bold">{((stake / balance) * 100).toFixed(2)}% do capital</p>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Fator Gale</label>
                <select value={gale} onChange={e => setGale(parseFloat(e.target.value))}
                  className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl p-4 outline-none focus:ring-2 focus:ring-blue-500/40 text-sm font-medium">
                  <option value={2.1}>2.1x (Padrão RDE)</option>
                  <option value={2.0}>2.0x (Conservador)</option>
                  <option value={2.5}>2.5x (Agressivo)</option>
                </select>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Max. Gales</label>
                <select value={maxGales} onChange={e => setMaxGales(parseInt(e.target.value))}
                  className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl p-4 outline-none focus:ring-2 focus:ring-blue-500/40 text-sm font-medium">
                  <option value={1}>1 Gale</option>
                  <option value={2}>2 Gales (Padrão)</option>
                  <option value={3}>3 Gales</option>
                </select>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Travar ao Bater Meta</label>
                <div className="flex items-center gap-3 bg-slate-950/50 border border-slate-800 rounded-xl p-4">
                  <button onClick={() => setAutoLockMeta(!autoLockMeta)}
                    className={`relative w-12 h-6 rounded-full transition-colors ${autoLockMeta ? 'bg-emerald-500' : 'bg-slate-700'}`}>
                    <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${autoLockMeta ? 'translate-x-6' : ''}`} />
                  </button>
                  <span className="text-xs text-slate-400 font-medium">{autoLockMeta ? 'Auto-trava ativada' : 'Auto-trava desativada'}</span>
                </div>
                <p className="text-[9px] text-slate-500">Ao bater a meta diária, o copier trava até meia-noite (00:00).</p>
              </div>

              <div className="flex items-end">
                <button onClick={handleSalvar} disabled={loading}
                  className={`w-full py-4 rounded-xl text-xs font-black uppercase tracking-widest transition-all shadow-lg active:scale-[0.98] ${saveError ? "bg-red-600 text-white" : saved ? "bg-emerald-600 text-white" : "bg-blue-600 hover:bg-blue-500 text-white"}`}>
                  {loading ? "Salvando..." : saveError ? "Erro ao salvar!" : saved ? "Salvo!" : "Salvar Configurações"}
                </button>
              </div>
            </div>
          </div>

          {/* Cálculo de sobrevivência */}
          <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-8 shadow-2xl border-l-4 border-l-blue-500">
            <h2 className="text-sm font-black text-white uppercase tracking-widest mb-6">Cálculo de Sobrevivência</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              {[
                { label: "Exposição Max.", value: fmt(exposicao), sub: "por ciclo", color: "text-white" },
                { label: "Entrada Segura", value: fmt(entradaSeg), sub: "por sessão (1%)", color: "text-emerald-400" },
                { label: "Ciclos até Stop", value: `${ciclosStop}x`, sub: "perdas consecutivas", color: ciclosStop >= 3 ? "text-emerald-400" : ciclosStop >= 2 ? "text-yellow-400" : "text-rose-400" },
                { label: "Capital Mínimo", value: fmt(exposicao * 5), sub: "recomendado", color: "text-blue-400" },
              ].map(c => (
                <div key={c.label} className="bg-slate-950/40 rounded-xl p-4 border border-slate-800/60">
                  <p className="text-[9px] text-slate-500 uppercase tracking-widest mb-1">{c.label}</p>
                  <p className={`text-lg font-black ${c.color}`}>{c.value}</p>
                  <p className="text-[9px] text-slate-600">{c.sub}</p>
                </div>
              ))}
            </div>
            
            <div className="bg-slate-950/50 rounded-xl p-4 border border-slate-800">
              <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-3">Sequência de Entradas</p>
              <div className="flex items-center gap-3 flex-wrap">
                <div className="flex items-center gap-2 px-3 py-2 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                  <span className="text-[10px] text-slate-500">Entrada</span>
                  <span className="text-sm font-black text-white">{fmt(stake)}</span>
                </div>
                {Array.from({ length: maxGales }).map((_, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="text-slate-600">→</span>
                    <div className="flex items-center gap-2 px-3 py-2 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
                      <span className="text-[10px] text-slate-500">G{i + 1}</span>
                      <span className="text-sm font-black text-yellow-400">{fmt(stake * Math.pow(gale, i + 1))}</span>
                    </div>
                  </div>
                ))}
                <div className="flex items-center gap-2">
                  <span className="text-slate-600">=</span>
                  <div className="px-3 py-2 bg-rose-500/10 border border-rose-500/20 rounded-lg">
                    <span className="text-sm font-black text-rose-400">{fmt(exposicao)} total</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Score + Resumo */}
        <div className="space-y-6">
          <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-6 text-center shadow-2xl">
            <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-4">Safety Score</p>
            <div className="relative w-32 h-32 mx-auto mb-4">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                <circle cx="18" cy="18" r="15.9" fill="none" stroke="#0f172a" strokeWidth="3" />
                <circle cx="18" cy="18" r="15.9" fill="none"
                  stroke={safetyScore >= 70 ? "#10b981" : safetyScore >= 40 ? "#f59e0b" : "#ef4444"}
                  strokeWidth="3"
                  strokeDasharray={`${safetyScore} ${100 - safetyScore}`}
                  strokeLinecap="round" />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <p className={`text-3xl font-black ${safetyScore >= 70 ? "text-emerald-400" : safetyScore >= 40 ? "text-yellow-400" : "text-rose-400"}`}>{safetyScore}</p>
              </div>
            </div>
            <p className={`text-xs font-black uppercase tracking-widest ${safetyScore >= 70 ? "text-emerald-400" : safetyScore >= 40 ? "text-yellow-400" : "text-rose-400"}`}>
              {safetyScore >= 70 ? "Excelente" : safetyScore >= 40 ? "Moderado" : "Risco Alto"}
            </p>
          </div>

          <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-6 space-y-3 shadow-2xl">
            <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Resumo do Dia</p>
            <div className="flex justify-between items-center border-b border-slate-800/40 pb-2">
              <span className="text-[10px] text-slate-500 uppercase tracking-widest">Corretora</span>
              <span className="font-black text-sm text-blue-400">{estado?.broker_ativo && estado.broker_ativo !== "-" ? estado.broker_ativo : "Nenhuma"}</span>
            </div>
            <div className="flex justify-between items-center border-b border-slate-800/40 pb-2">
              <span className="text-[10px] text-slate-500 uppercase tracking-widest">Capital Base</span>
              <span className="font-black text-sm text-white">{fmt(balance)}</span>
            </div>
            {[
              { label: "Meta", value: fmt(metaValor), color: "text-emerald-400" },
              { label: "Stop Loss", value: fmt(stopValor), color: "text-rose-400" },
              { label: "Entrada/Sessão", value: fmt(entradaSeg), color: "text-blue-400" },
              { label: "Exposição Max.", value: fmt(exposicao), color: "text-yellow-400" },
              { label: "Capital Protegido", value: fmt(balance - stopValor), color: "text-white" },
            ].map(item => (
              <div key={item.label} className="flex justify-between items-center border-b border-slate-800/40 pb-2 last:border-0 last:pb-0">
                <span className="text-[10px] text-slate-500 uppercase tracking-widest">{item.label}</span>
                <span className={`font-black text-sm ${item.color}`}>{item.value}</span>
              </div>
            ))}
          </div>

          <div className="bg-rose-500/5 backdrop-blur-md border border-rose-500/10 rounded-2xl p-6 shadow-2xl">
            <p className="text-rose-400 text-[10px] font-black uppercase tracking-widest mb-3 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse"></span>
              Protocolo de Emergência
            </p>
            <p className="text-slate-400 text-xs leading-relaxed">
              Ao atingir <span className="text-rose-400 font-bold">{stopLoss}% de perda</span>, o copier interrompe as operações automaticamente.
            </p>
            <div className="mt-4 p-3 bg-slate-950/40 rounded-xl border border-slate-800/60">
              <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Capital após stop</p>
              <p className="text-lg font-black text-white">{fmt(balance - stopValor)}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
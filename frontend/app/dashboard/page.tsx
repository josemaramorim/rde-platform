'use client';

import React, { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEstado } from '@/hooks/useEstado';
import { API_URL, formatMoney, Currency, errToText } from '@/lib/constants';
import { toast } from '@/components/Toast';

interface Trade {
  id: string;
  symbol: string;
  direction: string;
  entrada: string;
  resultado: string;
  lucro: number;
}

interface DashboardLiveData {
  broker: string;
  account_mode: string;
  balance: number;
  initial_balance: number;
  profit: number;
  profit_pct: number;
  signals_today: number;
  success_count: number;
  success_rate: number;
  gale_level: number;
  current_stake: number;
  last_message: string;
  timestamp: string;
  copier_running: boolean;
  copier_source?: string;
  signal_source?: string;
  active_brokers?: { broker: string; balance: number; mode: string; connected: boolean }[];
  operations: unknown;
  meta_hit_today?: boolean;
  auto_lock_meta?: boolean;
  meta_hit_date?: string | null;
}

export default function DashboardPage() {
  const { estado, token } = useEstado();
  const currency = (estado.currency || "USD") as Currency;
  const router = useRouter();
  const [trades, setTrades] = useState<Trade[]>([]);
  
  const [liveData, setLiveData] = useState<DashboardLiveData | null>(null);
  const [carregandoDados, setCarregandoDados] = useState(false);
  const [alternandoCopier, setAlternandoCopier] = useState(false);
  const [telegramAuthState, setTelegramAuthState] = useState<"loading" | "idle" | "code_sent" | "password_needed" | "authenticated">("loading");
  const [telegramPhone, setTelegramPhone] = useState("");
  const [telegramCode, setTelegramCode] = useState("");
  const [telegramPassword, setTelegramPassword] = useState("");
  const [telegramAuthLoading, setTelegramAuthLoading] = useState(false);
  const [telegramAuthError, setTelegramAuthError] = useState<string | null>(null);
  const [telegramCodeHash, setTelegramCodeHash] = useState<string | null>(null);

  const requisitando = useRef(false);

  // Verificar termo de risco ao carregar
  useEffect(() => {
    if (!token) return;
    fetch(`${API_URL}/risk-term/status`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(5000),
    })
      .then(r => r.json())
      .then(data => {
        if (!data.accepted) router.push("/termo-risco");
      })
      .catch(() => {});
  }, [token]);

  const buscarDadosDashboard = async () => {
    if (requisitando.current) return;
    requisitando.current = true;
    setCarregandoDados(true);

    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const response = await fetch('/dashboard/live', {
        method: 'GET',
        headers,
      });

      if (response.ok) {
        const data: DashboardLiveData = await response.json();
        setLiveData(data);
        
        if (data.operations && Array.isArray(data.operations)) {
          const mappedTrades = data.operations.map((op: any, index: number) => ({
            id: (op.id !== undefined && op.id !== null) ? String(op.id) : String(index),
            symbol: op.symbol || '---',
            direction: op.direction || 'CALL',
            entrada: op.time || op.timestamp || '--:--',
            resultado: op.result || 'PENDENTE',
            lucro: op.profit !== undefined ? Number(op.profit) : 0.0,
          }));
          setTrades(mappedTrades.reverse());
        }
      }
    } catch (err) {
      console.error('Erro ao conectar com o backend:', err);
    } finally {
      setCarregandoDados(false);
      requisitando.current = false;
    }
  };

  // Checar status de autenticação da sessão do Telegram ao carregar o Dashboard
  useEffect(() => {
    if (!token) return;
    fetch("/telegram/auth-status", {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d && d.authenticated) {
          setTelegramAuthState("authenticated");
        } else {
          setTelegramAuthState("idle");
        }
        if (d && d.phone) {
          setTelegramPhone(d.phone);
        }
      })
      .catch(() => setTelegramAuthState("idle"));
  }, [token]);

  // Pooling de dados em tempo real (intervalo de 5 segundos)
  useEffect(() => {
    buscarDadosDashboard();
    const interval = setInterval(buscarDadosDashboard, 5000); 
    return () => clearInterval(interval);
  }, [token]);

  const handleToggleCopier = async () => {
    if (!token || alternandoCopier) return;
    setAlternandoCopier(true);

    try {
      const novoEstado = !liveData?.copier_running;

      const response = await fetch('/copier/toggle', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ active: novoEstado })
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const msg = data?.detail?.message || data?.message || 'Falha ao alterar o estado do Copier no servidor.';
        toast.error(msg, "Automação");
        return;
      }

      if (data?.status === 'error') {
        toast.error(data.message || 'Erro ao ativar copier.', "Automação");
        return;
      }

      // Wait for copier process to initialize before polling
      await new Promise(r => setTimeout(r, 2000));
      await buscarDadosDashboard();
    } catch (err) {
      console.error('Erro ao chavear o Copier:', err);
    } finally {
      setAlternandoCopier(false);
    }
  };

  const fetchTelegramAuthStatus = () => {
    if (!token) return;
    fetch("/telegram/auth-status", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        setTelegramAuthState(prev => {
          if (prev !== "loading") return prev;
          return d?.authenticated ? "authenticated" : "idle";
        });
      })
      .catch(() => setTelegramAuthState(prev => prev === "loading" ? "idle" : prev));
  };

  const handleSendCode = async () => {
    setTelegramAuthLoading(true);
    setTelegramAuthError(null);
    setTelegramCode("");
    setTelegramPassword("");
    try {
      const res = await fetch("/telegram/send-code", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ phone: telegramPhone.trim() }),
        signal: AbortSignal.timeout(15000),
      });
      const data = await res.json();
      if (res.ok) {
        if (data.status === "already_authorized") {
          setTelegramAuthState("authenticated");
        } else {
          setTelegramCodeHash(data.phone_code_hash);
          setTelegramAuthState("code_sent");
        }
      } else {
        setTelegramAuthError(errToText(data.detail) || "Erro ao enviar código");
      }
    } catch (err: any) {
      if (err?.name === "TimeoutError") {
        setTelegramAuthError("Tempo limite atingido. Tente enviar o código novamente.");
      } else {
        setTelegramAuthError("Erro de conexão ao enviar o código.");
      }
    } finally {
      setTelegramAuthLoading(false);
    }
  };

  const handleSignIn = async () => {
    setTelegramAuthLoading(true);
    setTelegramAuthError(null);
    try {
      const res = await fetch("/telegram/sign-in", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          phone: telegramPhone.trim(),
          code: telegramCode.trim(),
          phone_code_hash: telegramCodeHash,
          password: telegramPassword.trim() || null,
        }),
      });
      const data = await res.json();
      if (data.status === "success") {
        setTelegramAuthState("authenticated");
      } else if (data.status === "password_needed") {
        setTelegramAuthState("password_needed");
        setTelegramAuthError("Senha 2FA necessária");
      } else if (data.status === "code_expired") {
        setTelegramAuthState("idle");
        setTelegramAuthError(data.message || "Código expirado");
      } else if (data.status === "code_invalid") {
        setTelegramAuthError(data.message || "Código inválido");
      } else {
        setTelegramAuthError(errToText(data.detail) || data.message || "Erro ao autenticar");
      }
    } catch {
      setTelegramAuthError("Erro de conexão");
    } finally {
      setTelegramAuthLoading(false);
    }
  };

  useEffect(() => {
    fetchTelegramAuthStatus();
  }, [token]);

  const bancaCalculada = (liveData?.balance && liveData.balance > 0)
    ? liveData.balance
    : (estado?.broker_balance && estado.broker_balance > 0)
    ? estado.broker_balance
    : (liveData?.active_brokers?.[0]?.balance && liveData.active_brokers[0].balance > 0)
    ? liveData.active_brokers[0].balance
    : (liveData?.balance ?? 0);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      {/* Conteúdo Principal */}
        <div className="flex-1 p-6 md:p-10 overflow-auto">
          {/* Header */}
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-10">
            <div>
              <h1 className="text-3xl font-black text-white tracking-tight">Dashboard de Performance</h1>
              <p className="text-slate-400 text-sm font-light mt-1">
                Acompanhe o monitoramento do mercado e seus robôs de sinal.
              </p>
            </div>
            <div className="flex gap-2">
              {(estado?.broker_ativo && estado.broker_ativo !== '-') ? (
                <div className={`px-4 py-2 rounded-xl text-xs font-black uppercase tracking-widest ${
                  estado.broker_connected
                    ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
                    : 'bg-slate-800/50 border border-slate-700 text-slate-400'
                }`}>
                  {estado.broker_connected ? '🟢' : '🔴'} {estado.broker_ativo} ({estado.broker_mode || (estado.broker_is_demo ? 'Demo' : 'Real')})
                </div>
              ) : (liveData?.broker && liveData.broker !== '-') ? (
                <div className="px-4 py-2 bg-slate-800/50 border border-slate-700 rounded-xl text-slate-400 text-xs font-black uppercase tracking-widest">
                  🔴 {liveData.broker} ({liveData.account_mode})
                </div>
              ) : null}
            </div>
          </div>

          {/* Cards de Status */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6">
              <div className="text-slate-500 text-xs font-black uppercase tracking-widest mb-2">Banca Atual</div>
              <div className="text-2xl font-black text-slate-100 font-mono">
                    {formatMoney(Number(bancaCalculada), currency)}
              </div>
              <div className={`text-xs font-bold mt-2 ${(liveData?.profit ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {liveData?.profit_pct ? `${Number(liveData.profit_pct).toFixed(2)}%` : '0.00%'} hoje
              </div>
            </div>

            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6">
              <div className="text-slate-500 text-xs font-black uppercase tracking-widest mb-2">Lucro Líquido</div>
              <div className={`text-2xl font-black font-mono ${(liveData?.profit ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {formatMoney(Number(liveData?.profit ?? 0), currency)}
              </div>
              <div className="text-xs text-slate-400 font-medium mt-2">
                Entrada fixa: {formatMoney(Number(liveData?.current_stake ?? 0), currency)}
              </div>
            </div>

            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6">
              <div className="text-slate-500 text-xs font-black uppercase tracking-widest mb-2">Sinais Computados</div>
              <div className="text-2xl font-black text-cyan-400 font-mono">
                {liveData?.signals_today ?? 0}
              </div>
              <div className="text-xs text-slate-400 font-medium mt-2">
                Vitórias Consecutivas: {liveData?.success_count ?? 0}
              </div>
            </div>

            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6">
              <div className="text-slate-500 text-xs font-black uppercase tracking-widest mb-2">Assertividade</div>
              <div className="text-2xl font-black text-slate-100 font-mono">
                {liveData?.success_rate ? `${Number(liveData.success_rate).toFixed(1)}%` : '0%'}
              </div>
              <div className="text-xs text-amber-400 font-bold mt-2">
                Martingale Alocado: G{liveData?.gale_level ?? 0}
              </div>
            </div>
          </div>

          {/* Corretoras Ativas */}
          {(liveData?.active_brokers?.length || 0) > 0 && (
            <div className="mb-8 bg-slate-900/60 border border-slate-800 rounded-xl p-6">
              <h2 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-4">Corretoras Ativas ({liveData?.active_brokers?.length || 0})</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {liveData?.active_brokers?.map((b) => {
                  const isMainBroker = (b.broker.toLowerCase() === (estado?.broker_ativo || liveData?.broker || "iqoption").toLowerCase());
                  const brokerBal = (isMainBroker && Number(bancaCalculada) > 0) ? Number(bancaCalculada) : Number(b.balance ?? 0);
                  return (
                    <div key={b.broker} className={`rounded-xl p-4 border flex items-center justify-between ${
                      b.connected ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-slate-950 border-slate-800'
                    }`}>
                      <div>
                        <p className="text-white font-black text-xs uppercase tracking-widest">{b.broker}</p>
                        <p className={`text-[10px] font-bold mt-1 ${b.connected ? 'text-emerald-400' : 'text-slate-500'}`}>
                          {b.connected ? `🟢 ${b.mode}` : '🔴 Offline'}
                        </p>
                      </div>
                      <span className="text-sm font-black text-slate-100 font-mono">
                        {formatMoney(brokerBal, currency)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Gráfico + Status do Robô */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
            <div className="lg:col-span-2 bg-slate-900/60 border border-slate-800 rounded-xl p-6">
              <h2 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-4">Mapeamento Analítico</h2>
              <div className="bg-slate-950 border border-slate-900 rounded-xl h-64 flex items-center justify-center">
                <div className="text-slate-500 text-center p-4">
                  <p className="text-3xl mb-2">📈</p>
                  <p className="text-sm font-bold text-slate-400">Stream de Ativos em Tempo Real</p>
                  <p className="text-xs text-slate-500 italic mt-2 max-w-md truncate">
                    {liveData?.last_message || 'Aguardando publicação do canal...'}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 flex flex-col justify-between">
              {telegramAuthState === "loading" ? (
                <div className="p-4 text-center text-xs text-slate-500">Verificando...</div>
              ) : telegramAuthState !== "authenticated" ? (
                <div>
                  <h2 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-4">Conectar Telegram</h2>
                  <p className="text-xs text-slate-500 mb-4">
                    Autentique sua conta Telegram para ativar o copiador de sinais.
                  </p>
                  <input type="tel" placeholder="+5511999999999"
                    className="w-full bg-slate-950 border border-slate-800 text-white rounded-xl p-3 text-sm outline-none focus:border-blue-500 mb-3"
                    value={telegramPhone}
                    onChange={e => setTelegramPhone(e.target.value)} />
                  <button onClick={handleSendCode}
                    disabled={telegramAuthLoading || !telegramPhone.trim()}
                    className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-black rounded-xl text-xs uppercase tracking-widest transition-all mb-3">
                    {telegramAuthLoading ? "Enviando..." : "📨 Enviar Código"}
                  </button>
                  {(telegramAuthState === "code_sent" || telegramAuthState === "password_needed" || telegramCodeHash) && (
                    <div className="border-t border-slate-800/80 pt-3 mt-1 animate-fadeIn">
                      <label className="text-[11px] font-bold text-slate-400 block mb-1">Código recebido no Telegram:</label>
                      <input type="text" placeholder="Ex: 12345"
                        className="w-full bg-slate-950 border border-slate-800 text-white rounded-xl p-3 text-sm outline-none focus:border-emerald-500 mb-3 font-mono"
                        value={telegramCode}
                        onChange={e => setTelegramCode(e.target.value)} />
                      {telegramAuthState === "password_needed" && (
                        <input type="password" placeholder="Senha 2FA"
                          className="w-full bg-slate-950 border border-amber-500/30 text-white rounded-xl p-3 text-sm outline-none focus:border-amber-500 mb-3"
                          value={telegramPassword}
                          onChange={e => setTelegramPassword(e.target.value)} />
                      )}
                      <button onClick={handleSignIn}
                        disabled={telegramAuthLoading || !telegramCode.trim()}
                        className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-black rounded-xl text-xs uppercase tracking-widest transition-all">
                        {telegramAuthLoading ? "Autenticando..." : "🔐 Autenticar Código"}
                      </button>
                    </div>
                  )}
                  {telegramAuthError && (
                    <div className="mt-3 p-3 rounded-xl text-xs font-bold border bg-rose-500/10 border-rose-500/20 text-rose-400">
                      {telegramAuthError}
                    </div>
                  )}
                </div>
              ) : (
                <>
                  <div>
                    <h2 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-4">Status do Copier</h2>
                    <div className="space-y-4">
                      <div className="flex items-center justify-between bg-slate-950 p-4 rounded-xl border border-slate-900">
                        <span className="text-slate-400 text-xs font-bold uppercase">{liveData?.copier_running ? `Módulo ${liveData?.signal_source === 'tradingview' || liveData?.copier_source === 'tradingview' ? 'TradingView Webhook' : 'Telegram'}` : 'Módulo de Automação'}</span>
                        <span className={`w-3 h-3 rounded-full ${
                          liveData?.copier_running ? 'bg-emerald-400 animate-pulse shadow-md shadow-emerald-400/50' : 'bg-rose-500'
                        }`}></span>
                      </div>
                      {liveData?.meta_hit_today && liveData?.auto_lock_meta && (
                        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-3 text-center">
                          <p className="text-amber-400 text-xs font-black uppercase tracking-widest">META BATIDA HOJE - TRAVADO</p>
                          <p className="text-slate-500 text-[10px] mt-1">Libera automaticamente à 00:00</p>
                        </div>
                      )}
                      <div className="text-xs font-mono text-slate-400 space-y-2 bg-slate-950 p-4 rounded-xl border border-slate-900">
                        <p><span className="text-slate-600 font-bold">PROCESSO:</span> {liveData?.copier_running ? (liveData?.signal_source === 'tradingview' || liveData?.copier_source === 'tradingview' ? 'AGUARDANDO WEBHOOK' : 'EXECUTANDO') : (liveData?.last_message && liveData.last_message.toLowerCase().includes('erro') ? 'ERRO' : 'OCIOSO')}</p>
                        <p className="truncate"><span className="text-slate-600 font-bold">RAW LOG:</span> {liveData?.last_message || 'Nenhum payload recebido'}</p>
                        <p><span className="text-slate-600 font-bold">SYNC:</span> {liveData?.timestamp || '-'}</p>
                      </div>
                      {!liveData?.copier_running && liveData?.last_message && liveData.last_message.toLowerCase().includes('erro') && (
                        <div className="mt-3 bg-rose-500/10 border border-rose-500/30 rounded-xl p-3">
                          <p className="text-rose-400 text-[11px] font-bold">{liveData.last_message}</p>
                        </div>
                      )}
                    </div>
                  </div>
                  <button 
                    onClick={handleToggleCopier}
                    disabled={alternandoCopier}
                    className={`w-full py-4 mt-4 rounded-xl text-white text-xs font-black uppercase tracking-widest transition shadow-lg ${
                      liveData?.copier_running 
                        ? 'bg-rose-600 hover:bg-rose-500 active:scale-[0.98]' 
                        : 'bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98]'
                    } disabled:opacity-50`}
                  >
                    {alternandoCopier ? 'Chaveando Módulo...' : liveData?.copier_running 
                      ? `Desativar Copier${(liveData?.signal_source === 'tradingview' || liveData?.copier_source === 'tradingview') ? ' (Webhook)' : ' (Telegram)'}`
                      : 'Ativar Copier'
                    }
                  </button>
                  <button 
                    onClick={async () => {
                      try { await fetch('/telegram/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` } }); } catch {}
                      setTelegramAuthState("idle");
                    }}
                    className="w-full text-center text-[11px] text-slate-500 hover:text-slate-300 font-bold mt-3 transition-colors cursor-pointer">
                    📱 Trocar / Reautenticar Número do Telegram
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Operações Recentes */}
          <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6">
            <h2 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-4">Histórico Operacional (Live Stream)</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-left">
                    <th className="p-3 text-slate-500 font-bold uppercase text-[11px] tracking-wider">Ativo</th>
                    <th className="p-3 text-slate-500 font-bold uppercase text-[11px] tracking-wider">Direção</th>
                    <th className="p-3 text-slate-500 font-bold uppercase text-[11px] tracking-wider">Horário</th>
                    <th className="p-3 text-slate-500 font-bold uppercase text-[11px] tracking-wider">Resultado</th>
                    <th className="p-3 text-slate-500 font-bold uppercase text-[11px] tracking-wider">Lucro</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/40">
                  {trades.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="p-8 text-center text-slate-500 font-light italic">
                        Nenhuma operação realizada hoje. Aguardando sinais do Telegram...
                      </td>
                    </tr>
                  ) : (
                    trades.map((trade, idx) => (
                      <tr key={trade.id ? String(trade.id) : `trade-${idx}`} className="hover:bg-slate-800/20 transition font-mono">
                        <td className="p-3 font-bold text-slate-200">{trade.symbol}</td>
                        <td className="p-3">
                          <span className={trade.direction === 'CALL' || trade.direction === 'BUY' ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                            {trade.direction}
                          </span>
                        </td>
                        <td className="p-3 text-slate-400 text-xs">{trade.entrada}</td>
                        <td className="p-3">
                          <span className={
                            trade.resultado.toUpperCase() === 'WIN'
                              ? 'text-emerald-400 font-black text-xs'
                              : trade.resultado.toUpperCase() === 'LOSS'
                              ? 'text-rose-400 font-black text-xs'
                              : 'text-amber-400 font-black text-xs'
                          }>
                            {trade.resultado}
                          </span>
                        </td>
                        <td className="p-3 font-bold">
                          <span className={trade.lucro >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                             {trade.lucro >= 0 ? '+' : ''} {formatMoney(Number(trade.lucro), currency)}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Footer */}
          <div className="mt-8 p-4 bg-slate-900/20 border border-slate-900 rounded-xl text-center text-xs text-slate-600 font-mono">
            <p suppressHydrationWarning>Sincronismo Global: {liveData?.timestamp && liveData.timestamp !== '-' ? liveData.timestamp : new Date().toLocaleTimeString('pt-BR')}</p>
          </div>
      </div>
    </div>
  );
}
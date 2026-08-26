"use client";

import React from 'react';
import { useEstado } from '@/hooks/useEstado';

function EquityCurve() {
  const data = React.useMemo(() => {
    const points = [];
    let value = 1000;
    for (let i = 0; i <= 20; i++) {
      points.push({ x: i, y: (value += (Math.random() - 0.3) * 50) });
    }
    return points;
  }, []);

  const values = data.map(p => p.y);
  const minVal = Math.min(...values);
  const range = Math.max(...values) - minVal || 1;

  const normalized = data.map((p, i) => ({
    x: (i / (data.length - 1)) * 100,
    y: 100 - ((p.y - minVal) / range) * 80 - 10,
  }));

  const linePath = `M ${normalized.map(p => `${p.x},${p.y}`).join(' L ')}`;
  const areaPath = `${linePath} L 100,100 L 0,100 Z`;
  const last = normalized[normalized.length - 1] || { x: 50, y: 50 };

  return (
    <div className='w-full h-full relative group select-none'>
      <svg viewBox='0 0 100 100' preserveAspectRatio='none' className='w-full h-full overflow-visible'>
        <defs>
          <linearGradient id='chartGradient' x1='0' y1='0' x2='0' y2='1'>
            <stop offset='0%' stopColor='#3b82f6' stopOpacity='0.4' />
            <stop offset='100%' stopColor='#3b82f6' stopOpacity='0' />
          </linearGradient>
        </defs>
        <path d={areaPath} fill='url(#chartGradient)' />
        <path d={linePath} fill='none' stroke='#3b82f6' strokeWidth='1.5' strokeLinecap='round' strokeLinejoin='round' className='drop-shadow-[0_0_6px_rgba(59,130,246,0.5)]' />
        <circle cx={last.x} cy={last.y} r='1.5' fill='#3b82f6' className='animate-pulse' />
      </svg>
      <div className='absolute inset-0 grid grid-cols-4 grid-rows-4 pointer-events-none opacity-5'>
        {[...Array(16)].map((_, i) => (
          <div key={i} className='border-t border-l border-slate-200' />
        ))}
      </div>
    </div>
  );
}

function Page() {
  const { estado, token } = useEstado();
  const [metrics, setMetrics] = React.useState({
    winRate: 0,
    profitFactor: 1,
    maxDD: 0,
    broker: '-',
    brokerType: '-',
    balance: 0,
    mode: '-',
    totalTrades: 0,
    totalWins: 0,
    totalLosses: 0,
    todayTrades: 0,
    todayProfit: 0,
    totalProfit: 0,
  });
  const [loading, setLoading] = React.useState(false);
  const fetched = React.useRef(false);

  React.useEffect(() => {
    (async () => {
      if (!fetched.current) {
        fetched.current = true;
        setLoading(true);
        try {
          const res = await fetch('/stats/performance', {
            method: 'GET',
            headers: {
              'Content-Type': 'application/json',
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
          });
          if (res.ok) {
            const t = await res.json();
            setMetrics({
              winRate: t.win_rate !== undefined ? t.win_rate : 0,
              profitFactor:
                t.total_trades > 0 && t.total_trades - t.total_wins > 0
                  ? parseFloat(
                      (
                        (t.total_wins / (t.total_trades - t.total_wins)) *
                        (t.total_profit > 0 ? 1 : -1)
                      ).toFixed(2)
                    )
                  : 1,
              maxDD: 0,
              broker: t.broker || '-',
              brokerType: t.broker_type || '-',
              balance: t.balance || 0,
              mode: t.mode || '-',
              totalTrades: t.total_trades || 0,
              totalWins: t.total_wins || 0,
              totalLosses: t.total_losses || 0,
              todayTrades: t.today_trades || 0,
              todayProfit: t.today_profit || 0,
              totalProfit: t.total_profit || 0,
            });
          }
        } catch (err) {
          console.error('Falha ao buscar métricas de performance:', err);
        } finally {
          setLoading(false);
          fetched.current = false;
        }
      }
    })();
  }, [token]);

  const brokerType =
    estado?.broker_ativo && estado.broker_ativo !== '-'
      ? estado.broker_ativo
      : metrics.brokerType;
  const balance =
    estado?.broker_balance > 0 ? estado.broker_balance : metrics.balance;
  const mode =
    estado?.broker_mode && estado.broker_mode !== '-'
      ? estado.broker_mode
      : metrics.mode;
  const connected = estado?.broker_connected;

  return (
    <div className='min-h-screen p-6 md:p-10 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 overflow-x-hidden'>
      <header className='mb-12 relative'>
        <div className='absolute -top-10 -left-10 w-40 h-40 bg-blue-500/10 blur-[100px] rounded-full -z-10' />
        <div className='flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-4'>
          <div>
            <h1 className='text-3xl font-black text-white tracking-tight'>Estatísticas de Performance</h1>
            <p className='text-slate-400 mt-1 text-sm font-light'>Análise quantitativa e métricas do seu histórico operacional.</p>
          </div>
          {brokerType && brokerType !== '-' && (
            <div className={`px-4 py-2 rounded-xl text-xs font-black uppercase tracking-widest ${
              connected
                ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
                : 'bg-slate-800/50 border border-slate-700 text-slate-400'
            }`}>
              {connected ? '🟢' : '🔴'} {brokerType} ({mode})
            </div>
          )}
        </div>
      </header>

      <div className='grid grid-cols-1 md:grid-cols-3 gap-6 mb-12'>
        <div className='bg-slate-900/60 border border-slate-800 rounded-xl p-6 transition-all hover:scale-[1.01]'>
          <p className='text-slate-500 text-xs font-black uppercase tracking-widest mb-2'>Win Rate</p>
          <div className='flex items-baseline gap-2'>
            <h3 className='text-3xl font-black text-white font-mono'>{loading ? '-' : `${metrics.winRate.toFixed(1)}%`}</h3>
            <span className='text-slate-500 text-xs font-medium'>{metrics.totalTrades} trades</span>
          </div>
          <p className='text-[10px] text-slate-500 font-medium mt-1'>{metrics.totalWins} vitórias / {metrics.totalLosses} derrotas</p>
        </div>

        <div className='bg-slate-900/60 border border-slate-800 rounded-xl p-6 transition-all hover:scale-[1.01]'>
          <p className='text-slate-500 text-xs font-black uppercase tracking-widest mb-2'>Saldo da Corretora</p>
          <div className='flex items-baseline gap-2'>
            <h3 className='text-3xl font-black text-emerald-400 font-mono'>{loading ? '-' : `R$ ${balance.toFixed(2)}`}</h3>
            <span className='text-slate-500 text-xs font-medium'>{mode}</span>
          </div>
          <p className='text-[10px] text-slate-500 font-medium mt-1'>
            Lucro hoje: {metrics.todayProfit >= 0 ? '+' : ''}R$ {metrics.todayProfit.toFixed(2)}
          </p>
        </div>

        <div className='bg-slate-900/60 border border-slate-800 rounded-xl p-6 transition-all hover:scale-[1.01]'>
          <p className='text-slate-500 text-xs font-black uppercase tracking-widest mb-2'>Lucro Total Acumulado</p>
          <div className='flex items-baseline gap-2'>
            <h3 className={`text-3xl font-black font-mono ${
              metrics.totalProfit >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}>{loading ? '-' : `R$ ${metrics.totalProfit.toFixed(2)}`}</h3>
          </div>
          <p className='text-[10px] text-slate-500 font-medium mt-1'>Trades hoje: {metrics.todayTrades}</p>
        </div>
      </div>

      <div className='bg-slate-900/60 border border-slate-800 rounded-xl p-8 mb-10 overflow-hidden relative'>
        <div className='flex items-center justify-between mb-8'>
          <h2 className='text-sm font-black text-slate-400 uppercase tracking-widest flex items-center gap-2'>
            <span className='w-2 h-2 rounded-full bg-blue-500 shadow-md shadow-blue-500/50' />
            Curva de Patrimônio (Equity)
          </h2>
          <div className='flex gap-2'>
            <span className='px-3 py-1 bg-blue-500/10 text-blue-400 text-xs font-black rounded-lg border border-blue-500/20'>Semanal</span>
            <span className='px-3 py-1 text-slate-500 text-xs font-bold rounded-lg transition-colors hover:text-slate-300 cursor-pointer'>Mensal</span>
          </div>
        </div>
        <div className='h-64 md:h-80 w-full mb-4'>
          <EquityCurve />
        </div>
        <div className='flex justify-between text-[10px] text-slate-500 font-mono border-t border-slate-800/60 pt-4'>
          <span>INÍCIO CICLO</span>
          <span>PROJEÇÃO ATUAL</span>
          <span>META CONSOLIDADA</span>
        </div>
      </div>

      <div className='grid grid-cols-1 lg:grid-cols-2 gap-8'>
        <div className='bg-slate-900/60 border border-slate-800 rounded-xl p-8'>
          <h2 className='text-sm font-black text-slate-400 uppercase tracking-widest mb-6'>Eficiência por Nível de Ciclo</h2>
          <div className='space-y-6'>
            {[
              { label: 'Nível 1 (Base Inicial)', value: 72, color: 'bg-blue-500' },
              { label: 'Nível 2 (Recuperação Leve)', value: 18, color: 'bg-cyan-500' },
              { label: 'Nível 3 (Alerta de Exposição)', value: 7, color: 'bg-amber-500' },
              { label: 'Nível 4+ (Zona Crítica)', value: 3, color: 'bg-rose-500' },
            ].map((item, i) => (
              <div key={i}>
                <div className='flex justify-between text-xs font-bold mb-2'>
                  <span className='text-slate-400 uppercase tracking-tight'>{item.label}</span>
                  <span className='text-white font-mono'>{item.value}%</span>
                </div>
                <div className='w-full bg-slate-950 h-2.5 rounded-full overflow-hidden border border-slate-900'>
                  <div className={`${item.color} h-full rounded-full transition-all duration-1000 ease-out`} style={{ width: `${item.value}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className='bg-slate-900/60 border border-slate-800 rounded-xl p-8 border-l-4 border-l-blue-500'>
          <h2 className='text-sm font-black text-slate-400 uppercase tracking-widest mb-4'>Neural Advisor Insights</h2>
          <div className='space-y-4'>
            <div className='bg-slate-950/50 border border-slate-900 p-5 rounded-xl'>
              <p className='text-blue-400 font-black text-xs uppercase tracking-widest mb-3 flex items-center gap-2'>
                <span className='w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse' />
                Diagnóstico de Volatilidade
              </p>
              <p className='text-slate-300 text-xs leading-relaxed font-light'>
                Sua maior eficiência ocorre em dias de{' '}
                <span className='text-white font-bold'>baixa ATR</span>. Quando a volatilidade média excede 1.5%, sua taxa de acerto no Nível 1 cai 14%.
                <span className='text-blue-400 ml-1 font-bold cursor-pointer hover:underline block mt-2'>Otimizar proteção →</span>
              </p>
            </div>
            <div className='bg-emerald-500/5 border border-emerald-500/10 p-5 rounded-xl'>
              <p className='text-emerald-400 font-black text-xs uppercase tracking-widest mb-2'>Sugestão de Performance</p>
              <p className='text-slate-400 text-xs italic leading-relaxed'>
                "Padrão detectado: Pausas de 15 minutos após sequências de 2 LOSS reduzem a probabilidade de acionamento do Nível 4 em até 40%."
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Page;

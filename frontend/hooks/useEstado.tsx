"use client";

import { createContext, useContext, useState, useEffect, useCallback, useRef, ReactNode } from "react";
import { API_URL } from "@/lib/constants";

const BALANCE_REFRESH_INTERVAL = 30000; // 30 segundos

export interface BrokerConectado {
  broker: string;
  balance: number;
  mode: string;
  is_demo: boolean;
  connected: boolean;
}

export interface EstadoUsuario {
  email: string;
  username: string;
  liberado: boolean;
  is_admin: boolean;
  plan_name: string;
  broker_ativo: string;
  broker_is_demo: boolean;
  stake: number;
  risk_mode: string;
  stop_loss_pct: number;
  daily_meta_pct: number;
  telegram_enabled: boolean;
  latency_protection: boolean;
  capital_planilha: number | null;
  broker_balance: number;
  broker_mode: string;
  broker_connected: boolean;
  brokers_conectados: Record<string, BrokerConectado>;
  auto_lock_meta: boolean;
  meta_hit_today: boolean;
  meta_hit_date: string | null;
  signal_source: string;
  webhook_secret: string | null;
  currency: string;
  allowed_brokers: string[];
}

const DEFAULT: EstadoUsuario = {
  email: "", username: "", liberado: true, is_admin: false,
  plan_name: "basic", broker_ativo: "iqoption", broker_is_demo: true,
  stake: 1.0, risk_mode: "safe", stop_loss_pct: 5.0, daily_meta_pct: 3.0,
  telegram_enabled: false, latency_protection: false, capital_planilha: null,
  broker_balance: 0, broker_mode: "-", broker_connected: false,
  brokers_conectados: {},
  auto_lock_meta: false, meta_hit_today: false, meta_hit_date: null,
  signal_source: "telegram", webhook_secret: null,
  currency: "USD",
  allowed_brokers: [],
};

function persistirEstado(estado: EstadoUsuario) {
  if (typeof window === "undefined") return;
  localStorage.setItem("rde_planilha_broker", estado.broker_ativo);
  localStorage.setItem("rde_planilha_balance", estado.broker_balance.toString());
  localStorage.setItem("rde_planilha_mode", estado.broker_mode);
  localStorage.setItem("rde_planilha_capital", (estado.capital_planilha ?? estado.broker_balance).toString());
  localStorage.setItem("rde_planilha_connected", estado.broker_connected.toString());
  localStorage.setItem("rde_brokers_conectados", JSON.stringify(estado.brokers_conectados));
  localStorage.setItem("rde_estado", JSON.stringify({
    email: estado.email,
    username: estado.username,
    liberado: estado.liberado,
    is_admin: estado.is_admin,
    plan_name: estado.plan_name,
    broker_ativo: estado.broker_ativo,
    broker_is_demo: estado.broker_is_demo,
    stake: estado.stake,
    risk_mode: estado.risk_mode,
    stop_loss_pct: estado.stop_loss_pct,
    daily_meta_pct: estado.daily_meta_pct,
    telegram_enabled: estado.telegram_enabled,
    latency_protection: estado.latency_protection,
    signal_source: estado.signal_source,
    auto_lock_meta: estado.auto_lock_meta,
    meta_hit_today: estado.meta_hit_today,
    meta_hit_date: estado.meta_hit_date,
    currency: estado.currency,
    allowed_brokers: estado.allowed_brokers,
  }));
}

function carregarEstadoLocal(): Partial<EstadoUsuario> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("rde_estado");
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

interface Ctx {
  estado: EstadoUsuario;
  loading: boolean;
  token: string;
  salvar: (campos: Partial<EstadoUsuario>) => Promise<boolean>;
  salvarCapital: (capital: number) => Promise<void>;
  setBrokerConectado: (broker: string, balance: number, mode: string, is_demo: boolean) => void;
  setTodosBrokers: (brokers: Record<string, BrokerConectado>) => void;
  recarregar: () => Promise<void>;
  refreshBalance: () => Promise<void>;
}

export const EstadoContext = createContext<Ctx>({
  estado: DEFAULT, loading: true, token: "",
  salvar: async () => false, salvarCapital: async () => {},
  setBrokerConectado: () => {}, setTodosBrokers: () => {},
  recarregar: async () => {}, refreshBalance: async () => {},
});

export function EstadoProvider({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<EstadoUsuario>(DEFAULT);
  const [loading, setLoading] = useState(true);
  const iniciado = useRef(false);
  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const getToken = () => typeof window !== "undefined" ? (sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token") || "") : "";

  const recarregar = useCallback(async () => {
    const token = getToken();
    if (!token) { setLoading(false); return; }
    try {
      const res = await fetch(`${API_URL}/user/estado`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(10000),
      });
      if (res.ok) {
        const data = await res.json();
        setEstado(prev => {
          const next = {
            ...prev,
            ...data,
            broker_balance: data.broker_balance || prev.broker_balance,
            broker_connected: data.broker_connected || prev.broker_connected,
            broker_mode: data.broker_mode || prev.broker_mode,
            brokers_conectados: prev.brokers_conectados,
            currency: data.currency || prev.currency || "USD",
          };
          persistirEstado(next);
          return next;
        });
      }
    } catch (e) {
      // Evita spam de warning em caso de backend reiniciando
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshBalance = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_URL}/broker/refresh-balance`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(15000),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.status === "ok" || data.balance > 0) {
          setEstado(prev => {
            const novosBrokers = { ...prev.brokers_conectados };
            if (Array.isArray(data.brokers)) {
              data.brokers.forEach((b: any) => {
                if (!b?.broker) return;
                novosBrokers[b.broker] = {
                  broker: b.broker,
                  balance: b.balance || 0,
                  mode: b.mode || "Demo",
                  is_demo: (b.mode || "Demo") === "Demo",
                  connected: !!b.connected,
                };
              });
            } else if (data.broker) {
              novosBrokers[data.broker] = {
                broker: data.broker,
                balance: data.balance,
                mode: data.mode || prev.broker_mode,
                is_demo: (data.mode || prev.broker_mode) === "Demo",
                connected: true,
              };
            }
            const next = {
              ...prev,
              broker_balance: data.balance || prev.broker_balance,
              broker_mode: data.mode || prev.broker_mode,
              broker_connected: data.status === "ok",
              brokers_conectados: novosBrokers,
            };
            persistirEstado(next);
            return next;
          });
        }
      }
    } catch (e) {
      // Silencioso — evita spam no console a cada 30s
    }
  }, []);

  // Inicialização e hidratação síncrona com o LocalStorage
  useEffect(() => {
    if (iniciado.current) return;
    iniciado.current = true;

    if (typeof window !== "undefined") {
      const savedBrokers = localStorage.getItem("rde_brokers_conectados");
      const savedEstado = carregarEstadoLocal();
      const bal = localStorage.getItem("rde_planilha_balance");
      const mode = localStorage.getItem("rde_planilha_mode");
      const broker = localStorage.getItem("rde_planilha_broker");
      const capital = localStorage.getItem("rde_planilha_capital");

      setEstado(prev => {
        let next = { ...prev };

        if (savedEstado) {
          next = { ...next, ...savedEstado };
        }

        if (savedBrokers) {
          try {
            next.brokers_conectados = JSON.parse(savedBrokers);
          } catch {}
        }

        if (bal && broker) {
          next.broker_ativo = broker;
          next.broker_balance = parseFloat(bal);
          next.broker_mode = mode || "Demo";
          next.broker_connected = true;
        }

        if (capital) {
          next.capital_planilha = parseFloat(capital);
        }

        return next;
      });
    }

    recarregar();
  }, [recarregar]);

  // Timer de refresh de saldo a cada 30 segundos
  useEffect(() => {
    const token = getToken();
    if (!token) return;

    // Primeiro refresh imediato após a recarga inicial
    const initialDelay = setTimeout(() => {
      refreshBalance();
    }, 5000);

    // Timer recorrente a cada 30 segundos
    refreshTimerRef.current = setInterval(() => {
      refreshBalance();
    }, BALANCE_REFRESH_INTERVAL);

    return () => {
      clearTimeout(initialDelay);
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    };
  }, [refreshBalance]);

  const salvar = useCallback(async (campos: Partial<EstadoUsuario>): Promise<boolean> => {
    const token = getToken();
    if (!token) return false;

    setEstado(prev => {
      const next = { ...prev, ...campos };
      persistirEstado(next);
      return next;
    });
    try {
      const res = await fetch(`${API_URL}/user/preferences`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(campos),
      });
      if (!res.ok) {
        console.warn("salvar preferences falhou:", res.status, await res.text());
      }
      await recarregar();
      return res.ok;
    } catch (e) {
      console.warn("salvar preferences erro de rede:", e);
      await recarregar();
      return false;
    }
  }, [recarregar]);

  const salvarCapital = useCallback(async (capital: number) => {
    const token = getToken();
    if (!token) return;
    
    setEstado(prev => {
      const next = { ...prev, capital_planilha: capital };
      persistirEstado(next);
      return next;
    });
    
    try {
      await fetch(`${API_URL}/user/salvar-capital?capital=${capital}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch (e) { console.warn("salvarCapital falhou:", e); }
  }, []);

  const setBrokerConectado = useCallback((broker: string, balance: number, mode: string, is_demo: boolean) => {
    setEstado(prev => {
      const next = {
        ...prev,
        broker_ativo: broker,
        broker_is_demo: is_demo,
        broker_balance: balance,
        broker_mode: mode,
        broker_connected: true,
        capital_planilha: balance,
        brokers_conectados: {
          ...prev.brokers_conectados,
          [broker]: { broker, balance, mode, is_demo, connected: true },
        },
      };
      persistirEstado(next);
      return next;
    });
  }, []);

  const setTodosBrokers = useCallback((brokers: Record<string, BrokerConectado>) => {
    setEstado(prev => {
      const next = { ...prev, brokers_conectados: brokers };
      persistirEstado(next);
      return next;
    });
  }, []);

  const token = typeof window !== "undefined" ? (sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token") || "") : "";

  return (
    <EstadoContext.Provider value={{ estado, loading, token, salvar, salvarCapital, setBrokerConectado, setTodosBrokers, recarregar, refreshBalance }}>
      {children}
    </EstadoContext.Provider>
  );
}

export function useEstado() {
  return useContext(EstadoContext);
}
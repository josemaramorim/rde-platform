"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useEstado } from "@/hooks/useEstado";
import { API_URL, errToText } from "@/lib/constants";

const ALL_BROKERS = [
  { id: "iqoption",     label: "IQ Option",     icon: "📊" },
  { id: "quotex",       label: "Quotex",         icon: "📈" },
  { id: "pocketoption", label: "Pocket Option",  icon: "🟣" },
  { id: "deriv",        label: "Deriv / Binary", icon: "🔷" },
];

const getToken = () => sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token") || "";

export default function SetupPage() {
  const router = useRouter();
  const { estado, recarregar } = useEstado();

  const [selectedBroker, setSelectedBroker] = useState("iqoption");
  const [brokerEmail, setBrokerEmail] = useState("");
  const [brokerPassword, setBrokerPassword] = useState("");
  const [brokerApiToken, setBrokerApiToken] = useState("");
  const [derivAppId, setDerivAppId] = useState("");
  const [derivExpiry, setDerivExpiry] = useState("");
  const [isDemo, setIsDemo] = useState(true);
  const [testing, setTesting] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [brokerStatus, setBrokerStatus] = useState<{ ok: boolean; msg: string } | null>(null);
  const [telegramConnected, setTelegramConnected] = useState(false);
  const [copierRunning, setCopierRunning] = useState(false);

  const [currency, setCurrency] = useState<string>(estado?.currency || "USD");
  const [savingCurrency, setSavingCurrency] = useState(false);

  // Admin server config state
  const [adminConfig, setAdminConfig] = useState<{configured: boolean; admin_server_url: string} | null>(null);
  const [adminUrlInput, setAdminUrlInput] = useState("");
  const [savingAdmin, setSavingAdmin] = useState(false);
  const [adminMsg, setAdminMsg] = useState<{ok: boolean; text: string} | null>(null);

  // Brokers disponíveis (filtrados pelo plano do usuário)
  const allowed = estado?.allowed_brokers || [];
  const BROKERS = allowed.length > 0
    ? ALL_BROKERS.filter(b => allowed.includes(b.id))
    : ALL_BROKERS;

  useEffect(() => {
    const token = getToken();
    if (!token) { router.push("/login"); return; }
    // Verificar termo de risco
    fetch(`${API_URL}/risk-term/status`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(5000),
    })
      .then(r => r.json())
      .then(data => {
        if (!data.accepted) router.push("/termo-risco");
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetch("/api/admin-server-config", {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then(r => r.json())
      .then(data => {
        setAdminConfig(data);
        if (!data.configured) setAdminUrlInput(data.admin_server_url || "http://");
      })
      .catch(() => {});
  }, []);

  const handleSaveAdminUrl = async () => {
    setSavingAdmin(true);
    setAdminMsg(null);
    try {
      const r = await fetch("/api/admin-server-config", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ admin_server_url: adminUrlInput.trim() }),
      });
      const data = await r.json();
      if (r.ok) {
        setAdminConfig(data);
        setAdminMsg({ ok: true, text: "Configurado! Reinicie o servidor para aplicar." });
      } else {
        setAdminMsg({ ok: false, text: errToText(data.detail) || "Erro ao salvar" });
      }
    } catch {
      setAdminMsg({ ok: false, text: "Erro de conexão" });
    } finally {
      setSavingAdmin(false);
    }
  };

  const fetchTelegramStatus = () => {
    const token = getToken();
    if (!token) return;
    fetch("/telegram/status", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d) {
          setTelegramConnected(d.connected ?? false);
          setCopierRunning(d.copier_running ?? false);
        }
      })
      .catch(() => {});
  };

  const handleSaveCurrency = async () => {
    setSavingCurrency(true);
    try {
      const r = await fetch("/user/currency", {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ currency }),
      });
      if (r.ok) {
        setBrokerStatus({ ok: true, msg: `Moeda alterada para ${currency}` });
      } else {
        setBrokerStatus({ ok: false, msg: "Erro ao salvar moeda" });
      }
    } catch {
      setBrokerStatus({ ok: false, msg: "Erro de conexão ao salvar moeda" });
    } finally {
      setSavingCurrency(false);
    }
  };

  const initRef = useRef(false);
  useEffect(() => {
    if (!initRef.current && estado) {
      initRef.current = true;
      const broker = estado.broker_ativo && estado.broker_ativo !== "-" ? estado.broker_ativo : "iqoption";
      setSelectedBroker(broker);
      setIsDemo(estado.broker_is_demo ?? true);
      setCurrency(estado.currency || "USD");
      setBrokerStatus({
        ok: estado.broker_connected,
        msg: estado.broker_connected
          ? `${broker} conectada — Saldo: ${estado.currency === "BRL" ? "R$ " : "$ "}${(estado.broker_balance || 0).toFixed(2)}`
          : `${broker} — Não conectada`,
      });
    }
    fetchTelegramStatus();
  }, [estado]);

  const precisaEmailSenha = selectedBroker === "iqoption" || selectedBroker === "quotex";
  const precisaToken = selectedBroker === "pocketoption" || selectedBroker === "deriv";

  const handleTestConnection = async () => {
    setTesting(true);
    setBrokerStatus(null);
    const token = getToken();
    if (!token) return;

    try {
      const payload: Record<string, any> = {
        broker_name: selectedBroker,
        is_demo: isDemo,
      };
      if (precisaEmailSenha) {
        payload.email = brokerEmail;
        payload.password = brokerPassword;
      } else if (precisaToken) {
        payload.api_token = brokerApiToken;
        if (selectedBroker === "deriv") {
          if (derivAppId.trim()) payload.deriv_app_id = derivAppId.trim();
          if (derivExpiry.trim()) payload.deriv_token_expiry = derivExpiry.trim();
        }
      }

      const saveRes = await fetch("/broker/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(payload),
      });
      if (!saveRes.ok) {
        const err = await saveRes.json().catch(() => ({}));
        setBrokerStatus({ ok: false, msg: errToText(err.detail) || "Falha ao salvar credenciais" });
        setTesting(false);
        return;
      }

      if (recarregar) recarregar();
      setTesting(false);
      setBrokerStatus({ ok: true, msg: "Credenciais salvas! Testando conexão em segundo plano..." });

      (async () => {
        try {
          const testRes = await fetch("/broker/test-connection", {
            method: "POST",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
            body: JSON.stringify({ broker_name: selectedBroker }),
            signal: AbortSignal.timeout(8000),
          });
          const testData = await testRes.json();

          if (testData.status === "ok") {
            const bal = testData.balance != null ? `Saldo: R$ ${Number(testData.balance).toFixed(2)}` : "";
            setBrokerStatus({
              ok: true,
              msg: `${selectedBroker.toUpperCase()} conectada — ${bal} (${testData.mode || "Demo"})`,
            });
          } else {
            setBrokerStatus({ ok: false, msg: testData.message || "Falha na conexão" });
          }
        } catch (e: any) {
          setBrokerStatus({ ok: false, msg: e?.message || "Erro ao conectar" });
        }
      })();
    } catch (e: any) {
      setBrokerStatus({ ok: false, msg: e?.message || "Erro ao conectar" });
      setTesting(false);
    }
  };

  const handleConfirm = async () => {
    setConfirmLoading(true);
    const token = getToken();
    if (!token) { window.location.href = "/login"; return; }

    try {
      const payload: Record<string, any> = {
        broker_name: selectedBroker,
        is_demo: isDemo,
      };
      if (precisaEmailSenha) {
        payload.email = brokerEmail;
        payload.password = brokerPassword;
      } else if (precisaToken) {
        payload.api_token = brokerApiToken;
        if (selectedBroker === "deriv") {
          if (derivAppId.trim()) payload.deriv_app_id = derivAppId.trim();
          if (derivExpiry.trim()) payload.deriv_token_expiry = derivExpiry.trim();
        }
      }
      await fetch("/broker/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(payload),
      });

      await fetch("/broker/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ broker_name: selectedBroker }),
      });
      window.location.href = "/dashboard";
    } catch {
      window.location.href = "/dashboard";
    }
  };

  // Token de ativação
  const [tokenCode, setTokenCode] = useState("");
  const [ativandoToken, setAtivandoToken] = useState(false);
  const [tokenMsg, setTokenMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const handleAtivarToken = async (e: React.FormEvent) => {
    e.preventDefault();
    setAtivandoToken(true);
    setTokenMsg(null);
    const t = getToken();
    if (!t) return;
    try {
      const res = await fetch("/auth/ativar-token", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${t}` },
        body: JSON.stringify({ codigo: tokenCode.trim() }),
      });
      const data = await res.json();
      if (res.ok) {
        setTokenMsg({ ok: true, text: `✅ Ativado! Plano: ${data.plano}` });
        setTimeout(() => window.location.reload(), 1500);
      } else {
        setTokenMsg({ ok: false, text: errToText(data.detail) || "Token inválido" });
      }
    } catch {
      setTokenMsg({ ok: false, text: "Erro de conexão" });
    } finally {
      setAtivandoToken(false);
    }
  };

  const liberado = estado?.liberado ?? false;
  const capital = estado?.broker_connected && estado?.broker_balance > 0
    ? estado.broker_balance
    : (estado?.capital_planilha || 0);
  const metaBatida = estado?.meta_hit_today ?? false;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-4 md:p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8">
          <div className="flex items-center gap-4">
            <h1 className="text-3xl font-black text-white tracking-tight">RDE</h1>
            <span className="text-xs text-slate-600 font-mono">v1.0</span>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <span className="px-4 py-1.5 bg-slate-800/80 rounded-xl text-xs text-slate-300 font-bold">
              {estado?.email || "..."}
            </span>
            <span className={`px-4 py-1.5 rounded-xl text-[10px] font-black uppercase tracking-widest border ${
              estado?.plan_name === "VIP"
                ? "bg-yellow-500/10 border-yellow-500/20 text-yellow-400"
                : "bg-slate-800 border-slate-700 text-slate-400"
            }`}>
              {estado?.plan_name || "BASIC"}
            </span>
            <span className={`px-4 py-1.5 rounded-xl text-[10px] font-black uppercase tracking-widest border ${
              liberado
                ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                : "bg-rose-500/10 border-rose-500/20 text-rose-400"
            }`}>
              {liberado ? "✅ LIBERADO" : "⛔ AGUARDANDO"}
            </span>
          </div>
        </div>

        {/* Card: Configurar Servidor Admin (mostra se não configurado) */}
        {adminConfig && !adminConfig.configured && (
          <div className="mb-6 bg-gradient-to-r from-blue-500/10 to-purple-500/10 border border-blue-500/20 rounded-2xl p-6 backdrop-blur-md">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-lg">🖥️</span>
              <h2 className="text-sm font-black text-white uppercase tracking-widest">Servidor Admin</h2>
            </div>
            <p className="text-xs text-slate-400 mb-4">
              Informe o endereço do servidor do administrador para validar sua licença.
            </p>
            <div className="flex flex-col gap-3">
                <input
                  type="text"
                  value={adminUrlInput}
                  onChange={e => setAdminUrlInput(e.target.value)}
                  placeholder="https://rde.seudominio.com"
                  className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl px-4 py-3 text-sm outline-none focus:border-blue-500 font-mono"
                />
                <p className="text-[10px] text-slate-500">
                  Se o administrador configurou um Cloudflare Tunnel, use a URL https:// fornecida.
                </p>
                <button
                  onClick={handleSaveAdminUrl}
                  disabled={savingAdmin || !adminUrlInput.trim()}
                  className="w-full py-3 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 disabled:opacity-50 text-white font-black rounded-xl text-xs uppercase tracking-widest transition-all shadow-lg"
                >
                  {savingAdmin ? "Salvando..." : "Salvar Configuração"}
                </button>
              {adminMsg && (
                <div className={`p-3 rounded-xl text-xs font-bold border ${adminMsg.ok ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" : "bg-rose-500/10 border-rose-500/20 text-rose-400"}`}>
                  {adminMsg.text}
                </div>
              )}
            </div>
          </div>
        )}

        {!liberado && (
          <div className="mb-6 bg-gradient-to-r from-amber-500/10 to-rose-500/10 border border-amber-500/20 rounded-2xl p-6 backdrop-blur-md">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-lg">🔑</span>
              <h2 className="text-sm font-black text-white uppercase tracking-widest">Ativar Plataforma</h2>
            </div>
            <p className="text-xs text-slate-400 mb-4">
              Insira o token de licença fornecido pelo administrador para liberar o acesso.
            </p>
            <form onSubmit={handleAtivarToken} className="flex gap-3">
              <input
                type="text"
                value={tokenCode}
                onChange={e => setTokenCode(e.target.value)}
                placeholder="Cole seu token aqui..."
                className="flex-1 bg-slate-950/50 border border-slate-800 text-white rounded-xl px-4 py-3 text-sm outline-none focus:border-amber-500 uppercase tracking-widest font-mono"
                required
              />
              <button type="submit" disabled={ativandoToken}
                className="px-6 py-3 bg-gradient-to-r from-amber-600 to-rose-600 hover:from-amber-500 hover:to-rose-500 disabled:opacity-50 text-white font-black rounded-xl text-xs uppercase tracking-widest transition-all shadow-lg">
                {ativandoToken ? "Ativando..." : "Ativar"}
              </button>
            </form>
            {tokenMsg && (
              <div className={`mt-3 p-3 rounded-xl text-xs font-bold border ${tokenMsg.ok ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" : "bg-rose-500/10 border-rose-500/20 text-rose-400"}`}>
                {tokenMsg.text}
              </div>
            )}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          {/* Card 1: Corretora */}
          <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-6">
            <div className="flex items-center gap-2 mb-5">
              <span className="text-lg">📊</span>
              <h2 className="text-sm font-black text-white uppercase tracking-widest">Corretora</h2>
            </div>

            <div className="grid grid-cols-2 gap-2 mb-4">
              {BROKERS.map(b => (
                <button
                  key={b.id}
                  onClick={() => { setSelectedBroker(b.id); setBrokerStatus(null); }}
                  className={`p-3 rounded-xl text-xs font-bold border transition-all ${
                    selectedBroker === b.id
                      ? "bg-blue-500/10 border-blue-500/40 text-blue-400"
                      : "bg-slate-950/50 border-slate-800 text-slate-500 hover:border-slate-700"
                  }`}
                >
                  {b.icon} {b.label}
                </button>
              ))}
            </div>

            {precisaEmailSenha && (
              <div className="space-y-3 mb-4">
                <input type="email" placeholder="E-mail da corretora"
                  className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl p-3 text-sm outline-none focus:border-blue-500"
                  value={brokerEmail} onChange={e => setBrokerEmail(e.target.value)} />
                <input type="password" placeholder="Senha"
                  className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl p-3 text-sm outline-none focus:border-blue-500"
                  value={brokerPassword} onChange={e => setBrokerPassword(e.target.value)} />
              </div>
            )}
            {precisaToken && (
              <div className="mb-4">
                <input type="password" placeholder="Token PAT da Deriv (pat_...)"
                  className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl p-3 text-sm outline-none focus:border-blue-500"
                  value={brokerApiToken} onChange={e => setBrokerApiToken(e.target.value)} />
                {selectedBroker === "deriv" && (
                  <div className="space-y-3 mt-3">
                    <input placeholder="App ID da aplicação (obrigatório, numérico)"
                      className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl p-3 text-sm outline-none focus:border-blue-500"
                      value={derivAppId} onChange={e => setDerivAppId(e.target.value)} />
                    <input type="date" placeholder="Validade do PAT"
                      className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl p-3 text-sm outline-none focus:border-blue-500"
                      value={derivExpiry} onChange={e => setDerivExpiry(e.target.value)} />
                    <p className="text-[10px] text-slate-500 leading-relaxed">
                      O <b>App ID</b> deve ser o da aplicação PAT que gerou o token em developers.deriv.com.
                      A data de validade serve para alertar 90 dias antes do vencimento.
                    </p>
                  </div>
                )}
              </div>
            )}

            <div className="flex gap-2 p-1 bg-slate-950/50 border border-slate-800 rounded-xl mb-4">
              <button onClick={() => setIsDemo(true)}
                className={`flex-1 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${isDemo ? "bg-slate-800 text-white border border-slate-700" : "text-slate-500"}`}>
                🎓 Demo
              </button>
              <button onClick={() => setIsDemo(false)}
                className={`flex-1 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${!isDemo ? "bg-rose-600/20 text-rose-400 border border-rose-500/30" : "text-slate-500"}`}>
                💰 Real
              </button>
            </div>

            <button
              onClick={handleTestConnection}
              disabled={testing}
              className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 text-white font-black rounded-xl transition-all text-xs uppercase tracking-widest shadow-md active:scale-[0.98] disabled:opacity-50"
            >
              {testing ? "Testando conexão..." : "🔌 Testar Conexão"}
            </button>

            {brokerStatus && (
              <div className={`mt-3 p-3 rounded-xl text-xs font-bold border ${
                brokerStatus.ok
                  ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                  : "bg-rose-500/10 border-rose-500/20 text-rose-400"
              }`}>
                <span className="mr-1">{brokerStatus.ok ? "🟢" : "🔴"}</span>
                {brokerStatus.msg}
              </div>
            )}
          </div>

          {/* Card: Moeda de Exibição */}
          <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-6">
            <div className="flex items-center gap-2 mb-5">
              <span className="text-lg">💱</span>
              <h2 className="text-sm font-black text-white uppercase tracking-widest">Moeda de Exibição</h2>
            </div>
            <p className="text-[11px] text-slate-500 mb-4">
              A corretora opera em dólar (USD). Escolha como exibir saldo e lucro na plataforma.
            </p>
            <div className="flex gap-2 p-1 bg-slate-950/50 border border-slate-800 rounded-xl mb-4">
              <button onClick={() => setCurrency("USD")}
                className={`flex-1 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${currency === "USD" ? "bg-slate-800 text-white border border-slate-700" : "text-slate-500"}`}>
                💵 USD (Dólar)
              </button>
              <button onClick={() => setCurrency("BRL")}
                className={`flex-1 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${currency === "BRL" ? "bg-slate-800 text-white border border-slate-700" : "text-slate-500"}`}>
                🇧🇷 BRL (Real)
              </button>
            </div>
            <button
              onClick={handleSaveCurrency}
              disabled={savingCurrency}
              className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 text-white font-black rounded-xl transition-all text-xs uppercase tracking-widest shadow-md active:scale-[0.98] disabled:opacity-50"
            >
              {savingCurrency ? "Salvando..." : "💱 Salvar Moeda"}
            </button>
          </div>

          {/* Card 2: Telegram */}
          <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-6">
            <div className="flex items-center gap-2 mb-5">
              <span className="text-lg">💬</span>
              <h2 className="text-sm font-black text-white uppercase tracking-widest">Telegram</h2>
            </div>

            <div className={`p-4 rounded-xl border text-center ${
              telegramConnected
                ? "bg-emerald-500/10 border-emerald-500/20"
                : "bg-rose-500/10 border-rose-500/20"
            }`}>
              <div className="text-4xl mb-2">
                {telegramConnected ? "🟢" : "🔴"}
              </div>
              <p className={`text-sm font-black uppercase tracking-widest ${telegramConnected ? "text-emerald-400" : "text-rose-400"}`}>
                {telegramConnected ? "Conectado" : "Desconectado"}
              </p>
              <p className="text-[10px] text-slate-500 mt-1">
                {copierRunning ? "Copiador em execução" : "Copiador parado"}
              </p>
            </div>

            <button
              onClick={fetchTelegramStatus}
              className="w-full mt-3 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold rounded-xl transition-all text-[10px] uppercase tracking-widest"
            >
              🔄 Verificar Status
            </button>
          </div>

          {/* Card 3: Capital */}
          <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-6">
            <div className="flex items-center gap-2 mb-5">
              <span className="text-lg">💰</span>
              <h2 className="text-sm font-black text-white uppercase tracking-widest">Capital</h2>
            </div>
            <p className="text-3xl font-black text-white">
              {capital.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}
            </p>
            <p className="text-[10px] text-slate-500 mt-2 uppercase tracking-widest">
              {estado?.broker_connected ? "Saldo da corretora" : "Capital da planilha"}
            </p>
            <div className="flex gap-2 mt-4">
              <span className="px-3 py-1 bg-slate-800 rounded-lg text-[10px] font-bold text-slate-400">
                Stake: R$ {estado?.stake?.toFixed(2) || "0.00"}
              </span>
              <span className="px-3 py-1 bg-slate-800 rounded-lg text-[10px] font-bold text-slate-400">
                Modo: {estado?.broker_is_demo ? "🎓 Demo" : "💰 Real"}
              </span>
            </div>
          </div>

          {/* Card 4: Meta */}
          <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-6">
            <div className="flex items-center gap-2 mb-5">
              <span className="text-lg">🎯</span>
              <h2 className="text-sm font-black text-white uppercase tracking-widest">Meta Diária</h2>
            </div>
            <div className={`p-4 rounded-xl border text-center ${
              metaBatida
                ? "bg-emerald-500/10 border-emerald-500/20"
                : "bg-slate-950/50 border-slate-800"
            }`}>
              <div className={`text-4xl mb-2 ${metaBatida ? "" : "opacity-30"}`}>
                {metaBatida ? "🏆" : "⏳"}
              </div>
              <p className={`text-sm font-black uppercase tracking-widest ${metaBatida ? "text-emerald-400" : "text-slate-400"}`}>
                {metaBatida ? "META BATIDA HOJE" : "META PENDENTE"}
              </p>
              <p className="text-[10px] text-slate-500 mt-1">
                {estado?.daily_meta_pct || 3}% sobre o capital
              </p>
            </div>
          </div>
        </div>

        {/* Botao Confirmar */}
        <div className="flex flex-col items-center">
          <button
            onClick={handleConfirm}
            disabled={confirmLoading}
            className="w-full max-w-md py-5 bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 text-white font-black rounded-2xl transition-all text-sm uppercase tracking-widest shadow-lg shadow-blue-600/20 active:scale-[0.99] disabled:opacity-50"
          >
            {confirmLoading ? "Ativando..." : "✅ Confirmar e Ir para o Dashboard"}
          </button>
          <p className="text-[10px] text-slate-600 mt-3">
            Certifique-se de que a corretora está conectada (🟢) antes de confirmar.
          </p>
        </div>
      </div>
    </div>
  );
}

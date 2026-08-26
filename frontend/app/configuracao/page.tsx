"use client";

import { useState, useEffect, useRef } from "react";
import { useEstado, EstadoUsuario } from "@/hooks/useEstado";
import { API_URL, errToText } from "@/lib/constants";

interface BrokerStatus {
    broker: string;
    is_active: boolean;
    is_demo: boolean;
    has_token: boolean;
    has_email: boolean;
}

const BROKERS = ["iqoption", "quotex", "pocketoption", "deriv"];

const BROKER_LABELS: Record<string, string> = {
    iqoption: "IQ Option",
    quotex: "Quotex",
    pocketoption: "Pocket Option",
    deriv: "Deriv / Binary",
};

export default function ConfigPage() {
    const { estado, token: tokenContexto, salvar, setBrokerConectado, salvarCapital } = useEstado();
    const token = tokenContexto || (typeof window !== "undefined" ? (sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token")) : null);

    const [status, setStatus] = useState<BrokerStatus[]>([]);
    const [loading, setLoading] = useState(false);
    const [selectedBroker, setSelectedBroker] = useState(estado?.broker_ativo || "iqoption");
    const [formData, setFormData] = useState({ api_token: "", email: "", password: "", is_demo: true });
    const [saveMsg, setSaveMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
    const [fetchStatusMsg, setFetchStatusMsg] = useState<string | null>(null);
    const prevBroker = useRef(selectedBroker);

    // Signal source state
    const [signalSource, setSignalSource] = useState<"telegram" | "tradingview">(
        estado?.signal_source === "tradingview" ? "tradingview" : "telegram"
    );
    const [webhookSecret, setWebhookSecret] = useState<string>(estado?.webhook_secret || "");
    const [tvStatusMsg, setTvStatusMsg] = useState<string | null>(null);

    const fetchStatus = async () => {
        setFetchStatusMsg("🔄 Atualizando...");
        const t = tokenContexto || (typeof window !== "undefined" ? (sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token")) : null);
        if (!t) { setFetchStatusMsg("❌ Sessão expirada. Faça login novamente."); return; }
        try {
            const res = await fetch(`/broker/status`, {
                headers: { Authorization: `Bearer ${t}` },
                signal: AbortSignal.timeout(5000),
            });
            if (!res.ok) { setFetchStatusMsg(`❌ Erro ${res.status}. Verifique sua conexão.`); return; }
            const data: BrokerStatus[] = await res.json();
            setStatus(data);
            setFetchStatusMsg("✅ Status atualizado!");
        } catch (e) {
            setFetchStatusMsg("❌ Erro de rede. Verifique se o servidor está rodando.");
        }
        setTimeout(() => setFetchStatusMsg(null), 3000);
    };

    // Load signal source from estado — sync both ways
    useEffect(() => {
        if (estado?.signal_source === "tradingview" || estado?.signal_source === "telegram") {
            setSignalSource(estado.signal_source);
        }
        if (estado?.webhook_secret) {
            setWebhookSecret(estado.webhook_secret);
        }
        if (estado?.broker_ativo && estado.broker_ativo !== "-") {
            setSelectedBroker(estado.broker_ativo);
        }
    }, [estado?.signal_source, estado?.webhook_secret, estado?.broker_ativo]);

    useEffect(() => {
        const current = status.find(s => s.broker === selectedBroker);
        const currentIsDemo = current ? current.is_demo : true;

        if (prevBroker.current !== selectedBroker) {
            prevBroker.current = selectedBroker;
            setFormData({
                api_token: "",
                email: "",
                password: "",
                is_demo: currentIsDemo
            });
            setSaveMsg(null);
        } else {
            setFormData(prev => ({ ...prev, is_demo: currentIsDemo }));
        }
    }, [selectedBroker, status]);

    useEffect(() => {
        fetchStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [token]);

    const handleToggleMode = async (is_demo: boolean) => {
        setFormData(prev => ({ ...prev, is_demo }));
        if (!token) return;
        
        const s = status.find(item => item.broker === selectedBroker);
        if (!s) return;

        try {
            await fetch(`/broker/toggle-mode`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                body: JSON.stringify({ broker_name: selectedBroker, is_demo }),
            });
            fetchStatus();
        } catch { /* silencioso */ }
    };

    const handleSave = async (e: React.FormEvent) => {
        e.preventDefault();
        setSaveMsg(null);
        setLoading(true);

        const authToken = token || (typeof window !== "undefined" ? (sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token")) : null);

        if (!authToken) {
            setSaveMsg({ type: "err", text: "Sessão expirada. Faça login novamente no sistema." });
            setLoading(false);
            return;
        }

        const payload: Record<string, any> = {
            broker_name: selectedBroker,
            is_demo: formData.is_demo,
        };

        if (selectedBroker === "iqoption" || selectedBroker === "quotex") {
            payload.email = formData.email;
            payload.password = formData.password;
        } else if (selectedBroker === "pocketoption" || selectedBroker === "deriv") {
            payload.api_token = formData.api_token;
        }

        try {
            const res = await fetch(`/broker/settings`, {
                method: "POST",
                headers: { 
                    "Content-Type": "application/json", 
                    "Authorization": `Bearer ${authToken}`
                },
                body: JSON.stringify(payload),
            });

            if (res.ok) {
                setSaveMsg({ type: "ok", text: `${BROKER_LABELS[selectedBroker]} vinculada com sucesso!` });
                setFormData(prev => ({ ...prev, api_token: "", email: "", password: "" }));
                fetchStatus();
                setLoading(false);

                // Ativar corretora no servidor e testar conexão em segundo plano
                (async () => {
                    try {
                        await fetch(`/broker/activate`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json", Authorization: `Bearer ${authToken}` },
                            body: JSON.stringify({ broker_name: selectedBroker }),
                        });
                        const testRes = await fetch(`/broker/test-connection`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json", Authorization: `Bearer ${authToken}` },
                            body: JSON.stringify({ broker_name: selectedBroker }),
                            signal: AbortSignal.timeout(10000),
                        });
                        const testData = await testRes.json();
                        if (testData.status === "ok") {
                            const balanceNum = testData.balance ?? 0;
                            const modeStr = testData.mode || (formData.is_demo ? "Demo" : "Real");
                            if (setBrokerConectado) setBrokerConectado(selectedBroker, balanceNum, modeStr, formData.is_demo);
                            if (salvarCapital) salvarCapital(balanceNum);
                            setSaveMsg({ type: "ok", text: `${BROKER_LABELS[selectedBroker]} conectada! Saldo: R$ ${balanceNum.toFixed(2)}` });
                        } else {
                            if (setBrokerConectado) setBrokerConectado(selectedBroker, 0, formData.is_demo ? "Demo" : "Real", formData.is_demo);
                            setSaveMsg({ type: "err", text: testData.message || "Erro ao testar conexão com a corretora." });
                        }
                    } catch (connErr: any) {
                        if (setBrokerConectado) setBrokerConectado(selectedBroker, 0, formData.is_demo ? "Demo" : "Real", formData.is_demo);
                        setSaveMsg({ type: "err", text: connErr?.message || "Erro de conexão ao testar a corretora." });
                    }
                })();
            } else {
                const err = await res.json().catch(() => ({}));
                setSaveMsg({ type: "err", text: errToText(err.detail) || "Falha ao salvar as credenciais." });
                setLoading(false);
            }
        } catch {
            setSaveMsg({ type: "err", text: "Servidor offline. Verifique se o backend está operando." });
            setLoading(false);
        }
    };

    // Toggle signal source (Telegram vs TradingView)
    const handleToggleSignalSource = async (source: "telegram" | "tradingview") => {
        if (!token) return;
        const ok = await salvar({ signal_source: source } as Partial<EstadoUsuario>);
        if (ok) {
            setSignalSource(source);
            setTvStatusMsg(null);
        }
    };

    // Generate TradingView webhook secret
    const handleGenerateWebhookSecret = async () => {
        if (!token) return;
        try {
            const res = await fetch(`/tradingview/generate-secret`, {
                method: "POST",
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
                const data = await res.json();
                setWebhookSecret(data.webhook_secret);
                setTvStatusMsg("Webhook Secret gerado com sucesso! Copie e cole no alerta do TradingView.");
            }
        } catch {
            setTvStatusMsg("Erro ao gerar Webhook Secret.");
        }
    };

    const getStatusDot = (b: string) => {
        const s = status.find(item => item.broker === b);
        if (!s || (!s.has_token && !s.has_email)) return "bg-slate-700";
        return s.is_demo ? "bg-yellow-400" : "bg-emerald-500";
    };

    const getStatusLabel = (b: string) => {
        const s = status.find(item => item.broker === b);
        if (!s || (!s.has_token && !s.has_email)) return "Não configurado";
        return s.is_demo ? "Treinamento" : "Conta Real";
    };

    const brokerAtivo = estado?.broker_ativo && estado.broker_ativo !== "-"
        ? estado.broker_ativo
        : null;

    return (
        <div className="min-h-screen p-6 md:p-10 bg-slate-950 overflow-x-hidden">
            <header className="mb-10">
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                    <div>
                        <h1 className="text-4xl font-black text-white tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-cyan-400">Configurações de Conexão</h1>
                        <p className="text-slate-400 mt-2 font-light">
                            Cadastre suas credenciais de operação. Para iniciar os robôs, acesse a{" "}
                            <a href="/planilha" className="text-blue-400 hover:underline font-bold">Planilha</a>.
                        </p>
                    </div>
                    {brokerAtivo && (
                        <div className={`px-4 py-2 rounded-xl text-xs font-black uppercase tracking-widest ${
                            estado?.broker_connected
                                ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-400"
                                : "bg-slate-800/50 border border-slate-700 text-slate-400"
                        }`}>
                            {estado?.broker_connected ? "🟢" : "🔴"} {brokerAtivo} ({estado?.broker_mode || "?"})
                        </div>
                    )}
                </div>
            </header>

            {/* Modo de Sinal: Telegram vs TradingView Webhook */}
            <div className="mb-8 bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-6">
                <h2 className="text-xs font-black text-slate-500 uppercase tracking-widest mb-4">Modo de Sinal</h2>
                <p className="text-slate-400 text-sm mb-4">
                    Escolha como os sinais chegam à plataforma. TradingView Webhook elimina a dependência do Telegram e reduz a latência.
                </p>
                <div className="flex gap-3 mb-4">
                    <button
                        onClick={() => handleToggleSignalSource("telegram")}
                        className={`flex-1 py-4 rounded-xl text-xs font-black uppercase tracking-widest transition-all border ${
                            signalSource === "telegram"
                                ? "bg-blue-600/10 border-blue-500/50 text-blue-400 shadow-lg shadow-blue-500/5"
                                : "border-slate-800 text-slate-500 hover:border-slate-700"
                        }`}
                    >
                        📱 Telegram
                    </button>
                    <button
                        onClick={() => handleToggleSignalSource("tradingview")}
                        className={`flex-1 py-4 rounded-xl text-xs font-black uppercase tracking-widest transition-all border ${
                            signalSource === "tradingview"
                                ? "bg-emerald-600/10 border-emerald-500/50 text-emerald-400 shadow-lg shadow-emerald-500/5"
                                : "border-slate-800 text-slate-500 hover:border-slate-700"
                        }`}
                    >
                        📊 TradingView Webhook
                    </button>
                </div>

                {signalSource === "tradingview" && (
                    <div className="bg-slate-950/60 rounded-xl p-5 border border-slate-800/60">
                        <h3 className="text-white text-sm font-bold mb-3">Configuração TradingView Webhook</h3>
                        <p className="text-slate-500 text-xs mb-4">
                            Crie um alerta no TradingView com ação "Webhook URL". O RDE recebe e executa automaticamente.
                        </p>

                        <div className="space-y-4">
                            <div>
                                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1 block">Webhook URL (no alerta do TradingView)</label>
                                <div className="flex items-center gap-2">
                                    <input type="text" readOnly
                                        value="http://localhost:8000/tradingview/webhook"
                                        className="flex-1 bg-slate-900 border border-slate-800 text-slate-300 rounded-xl px-4 py-3 text-sm font-mono" />
                                    <button
                                        onClick={() => {
                                            navigator.clipboard.writeText("http://localhost:8000/tradingview/webhook");
                                            setTvStatusMsg("Webhook URL copiada! Cole no campo 'Webhook URL' do alerta no TradingView.");
                                        }}
                                        className="px-4 py-3 bg-slate-800 border border-slate-700 text-slate-300 rounded-xl text-xs font-bold hover:bg-slate-700 transition-all"
                                    >
                                        Copiar
                                    </button>
                                </div>
                                <p className="text-[9px] text-slate-500 mt-1">Endpoint completo: <code className="text-emerald-400">http://localhost:8000/tradingview/webhook</code></p>
                            </div>

                            <div>
                                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1 block">Webhook Secret (campo "passphrase" no JSON)</label>
                                <div className="flex items-center gap-2">
                                    <input type="text" readOnly
                                        value={webhookSecret || "Clique em 'Gerar Secret' abaixo"}
                                        className={`flex-1 bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 text-sm font-mono ${webhookSecret ? "text-emerald-400" : "text-slate-600"}`} />
                                    <button
                                        onClick={handleGenerateWebhookSecret}
                                        className="px-4 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold transition-all"
                                    >
                                        Gerar Secret
                                    </button>
                                    {webhookSecret && (
                                        <button
                                            onClick={() => {
                                                navigator.clipboard.writeText(webhookSecret);
                                                setTvStatusMsg("Webhook Secret copiado!");
                                            }}
                                            className="px-4 py-3 bg-slate-800 border border-slate-700 text-slate-300 rounded-xl text-xs font-bold hover:bg-slate-700 transition-all"
                                        >
                                            Copiar
                                        </button>
                                    )}
                                </div>
                            </div>

                            {tvStatusMsg && (
                                <p className={`text-xs font-bold ${tvStatusMsg.includes("sucesso") || tvStatusMsg.includes("copiada") || tvStatusMsg.includes("copiado") ? "text-emerald-400" : "text-rose-400"}`}>
                                    {tvStatusMsg}
                                </p>
                            )}

                            <div className="bg-slate-900/60 rounded-xl p-4 border border-slate-800/40">
                                <p className="text-slate-400 text-xs">
                                    <span className="text-white font-bold">Payload JSON do alerta:</span><br/>
                                    <code className="text-blue-400 block mt-1 bg-slate-950 p-3 rounded-lg text-[10px] leading-relaxed">
{`{
  "passphrase": "${webhookSecret || "SEU_SECRET"}",
  "symbol": "{{ticker}}",
  "direction": "{{strategy.order.action}}",
  "expiry_minutes": 1
}`}
                                    </code>
                                </p>
                                <p className="text-slate-500 text-[10px] mt-2">
                                    1. Crie um alerta no TradingView com ação "Webhook URL"<br/>
                                    2. Cole a URL e o JSON acima no campo "Message"<br/>
                                    3. O RDE recebe, aplica o gerenciamento de risco e executa na corretora<br/>
                                    4. Acompanhe tudo no <a href="/dashboard" className="text-blue-400 hover:underline font-bold">Dashboard</a>
                                </p>
                            </div>
                        </div>
                    </div>
                )}

                {signalSource === "telegram" && (
                    <div className="bg-slate-950/60 rounded-xl p-5 border border-slate-800/60">
                        <p className="text-slate-400 text-xs">
                            Modo tradicional: sinais chegam via grupo do Telegram e são processados automaticamente.
                            Configure o copier na aba <a href="/planilha" className="text-blue-400 hover:underline font-bold">Planilha</a>.
                        </p>
                    </div>
                )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Lateral: Lista de Corretoras */}
                <div className="space-y-3">
                    <h2 className="text-xs font-black text-slate-500 uppercase tracking-widest mb-4">Corretoras Suportadas</h2>
                    {BROKERS.map(b => {
                        const s = status.find(item => item.broker === b);
                        const configured = s && (s.has_token || s.has_email);
                        return (
                            <div
                                key={b}
                                onClick={() => setSelectedBroker(b)}
                                className={`rounded-2xl p-5 cursor-pointer border backdrop-blur-md transition-all ${selectedBroker === b ? "border-blue-500/50 bg-blue-500/5 shadow-lg shadow-blue-500/5" : "border-slate-800 bg-slate-900/40 hover:border-slate-700"}`}
                            >
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-white font-black text-sm">{BROKER_LABELS[b]}</p>
                                        <p className={`text-[10px] font-bold uppercase tracking-widest mt-1 ${configured ? (s?.is_demo ? "text-yellow-400" : "text-emerald-400") : "text-slate-600"}`}>
                                            {getStatusLabel(b)}
                                        </p>
                                    </div>
                                    <div className={`w-3 h-3 rounded-full ${getStatusDot(b)} ${configured ? "animate-pulse shadow-md shadow-current" : ""}`}></div>
                                </div>
                            </div>
                        );
                    })}

                    <button
                        onClick={fetchStatus}
                        className="w-full mt-2 py-2.5 bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-400 text-xs font-black uppercase tracking-widest rounded-xl transition-all"
                    >
                        🔄 Atualizar Conexões
                    </button>

                    {fetchStatusMsg && (
                        <p className={`text-xs font-bold text-center mt-2 ${fetchStatusMsg.includes('✅') ? 'text-emerald-400' : fetchStatusMsg.includes('🔄') ? 'text-blue-400' : 'text-rose-400'}`}>
                            {fetchStatusMsg}
                        </p>
                    )}

                    <div className="p-4 bg-slate-900 border border-slate-800 rounded-2xl">
                        <p className="text-blue-400 text-[10px] font-black uppercase tracking-widest mb-1">Criptografia Ponta a Ponta</p>
                        <p className="text-slate-500 text-xs font-light">Seus dados de acesso são criptografados com o algoritmo bancário <span className="text-slate-300 font-bold">AES-256</span>.</p>
                    </div>
                </div>

                {/* Formulário de Configuração */}
                <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-8">
                    <h2 className="text-xl font-black text-white mb-1">{BROKER_LABELS[selectedBroker]}</h2>
                    <p className="text-slate-500 text-sm mb-6">Insira e atualize suas credenciais com segurança.</p>

                    <form onSubmit={handleSave} className="space-y-6">
                        {/* Tipo de conta */}
                        <div className="space-y-2">
                            <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Ambiente de Execução</label>
                            <div className="flex gap-2 p-1 bg-slate-950 border border-slate-800 rounded-xl">
                                <button type="button" onClick={() => handleToggleMode(true)}
                                    className={`flex-1 py-3 rounded-lg text-xs font-black uppercase tracking-widest transition-all ${formData.is_demo ? "bg-slate-800 text-white shadow-inner" : "text-slate-500 hover:text-slate-300"}`}>
                                    🎓 Treinamento (Demo)
                                </button>
                                <button type="button" onClick={() => handleToggleMode(false)}
                                    className={`flex-1 py-3 rounded-lg text-xs font-black uppercase tracking-widest transition-all ${!formData.is_demo ? "bg-rose-600 text-white shadow-lg shadow-rose-600/20" : "text-slate-500 hover:text-slate-300"}`}>
                                    💰 Conta Real
                                </button>
                            </div>
                        </div>

                        {/* Campos dinâmicos */}
                        {(selectedBroker === "iqoption" || selectedBroker === "quotex") && (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">E-mail de Acesso</label>
                                    <input type="email" placeholder="seu@email.com" required
                                        className="w-full bg-slate-950 border border-slate-800 text-white rounded-xl p-4 outline-none focus:border-blue-500 text-sm"
                                        value={formData.email}
                                        onChange={e => setFormData({ ...formData, email: e.target.value })} />
                                </div>
                                <div className="space-y-2">
                                    <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Senha</label>
                                    <input type="password" placeholder="••••••••" required
                                        className="w-full bg-slate-950 border border-slate-800 text-white rounded-xl p-4 outline-none focus:border-blue-500 text-sm"
                                        value={formData.password}
                                        onChange={e => setFormData({ ...formData, password: e.target.value })} />
                                </div>
                            </div>
                        )}

                        {(selectedBroker === "pocketoption" || selectedBroker === "deriv") && (
                            <div className="space-y-2">
                                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Token de API / SSID</label>
                                <input type="password" placeholder={selectedBroker === "deriv" ? "Cole seu token da API Deriv" : 'Exemplo: 42["auth",{"session":"..."}]'} required
                                    className="w-full bg-slate-950 border border-slate-800 text-white rounded-xl p-4 outline-none focus:border-blue-500 font-mono text-sm"
                                    value={formData.api_token}
                                    onChange={e => setFormData({ ...formData, api_token: e.target.value })} />
                                <p className="text-[9px] text-slate-500">{selectedBroker === "deriv" ? "Gere em: Deriv App → Settings → API Token" : "Extração: F12 → Network → Filtro WS → Localizar frame auth"}</p>
                            </div>
                        )}

                        {saveMsg && (
                            <div className={`p-4 rounded-xl text-xs font-bold border ${saveMsg.type === "ok" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-red-500/10 text-red-400 border-red-500/20"}`}>
                                {saveMsg.type === "ok" ? "✅ " : "❌ "} {saveMsg.text}
                            </div>
                        )}

                        <div className="flex gap-3">
                            <button type="submit" disabled={loading}
                                className="px-8 py-4 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-600 text-white font-black rounded-xl transition-all shadow-lg active:scale-95 uppercase text-xs tracking-widest">
                                {loading ? "Salvando..." : "Vincular e Proteger"}
                            </button>
                            <a href="https://t.me/AmigosTraderBrasil" target="_blank" rel="noopener noreferrer"
                                className="px-6 py-4 bg-slate-800 border border-slate-700 hover:bg-slate-700 text-slate-300 font-bold rounded-xl transition-all text-xs flex items-center">
                                💬 Suporte Oficial
                            </a>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    );
}
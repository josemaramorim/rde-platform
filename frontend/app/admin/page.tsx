"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useEstado } from "@/hooks/useEstado";
import { API_URL, errToText } from "@/lib/constants";

interface User {
    id: string;
    email: string;
    username: string;
    is_active: boolean;
    is_admin: boolean;
    trading_enabled: boolean;
    liberado: boolean;
    last_seen: string | null;
    is_online: boolean;
    total_profit: number;
    stake: number;
    plan_name: string;
    admin_notes: string | null;
}

export default function AdminPage() {
    // 🔑 Conexão direta com o Estado Global para receber o Token autenticado em tempo real
    const { token } = useEstado();

    const [users, setUsers]           = useState<User[]>([]);
    const [filtered, setFiltered]     = useState<User[]>([]);
    const [search, setSearch]         = useState("");
    const [filterStatus, setFilter]   = useState("Todos");
    const [loading, setLoading]       = useState(true);
    const [error, setError]           = useState("");
    const [toast, setToast]           = useState<{ text: string; ok: boolean } | null>(null);
    const [modal, setModal] = useState<User | null>(null);
    const [modalNotes, setModalNotes] = useState("");
    const [modalPlan, setModalPlan] = useState("Free");
    const [saving, setSaving] = useState(false);
    const [saveMsg, setSaveMsg] = useState("");

    // Novo cliente
    const [novoEmail, setNovoEmail]   = useState("");
    const [novoNome, setNovoNome]     = useState("");
    const [novaSenha, setNovaSenha]   = useState("");
    const [criando, setCriando]       = useState(false);
    const [criarMsg, setCriarMsg]     = useState("");
    const [showCriar, setShowCriar]   = useState(false);

    // Plan Brokers Management
    const [planBrokers, setPlanBrokers] = useState<Record<string, string[]>>({});
    const [savingPlanBrokers, setSavingPlanBrokers] = useState<string | null>(null);
    const [planBrokerMsg, setPlanBrokerMsg] = useState<{ text: string; ok: boolean } | null>(null);
    const [loadingPlanBrokers, setLoadingPlanBrokers] = useState(true);

    const initialized = useRef(false);

    // Badge de plano (VIP / Pro / Free)
    const planBadge = (plan: string) => {
        const p = (plan || "Free").toLowerCase();
        if (p === "vip")
            return <span className="px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest bg-amber-500/15 text-amber-400 border border-amber-500/30">👑 VIP</span>;
        if (p === "pro")
            return <span className="px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest bg-blue-500/15 text-blue-400 border border-blue-500/30">⭐ Pro</span>;
        return <span className="px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest bg-slate-700/40 text-slate-400 border border-slate-600/40">Free</span>;
    };

    const showToast = (text: string, ok = true) => {
        setToast({ text, ok });
        setTimeout(() => setToast(null), 3000);
    };

    // Busca de usuários com validação reativa do token global
    const fetchUsers = useCallback(async () => {
        if (!token) { 
            setError("Faça login como administrador ou aguarde a sincronização."); 
            setLoading(false); 
            return; 
        }
        try {
            const res = await fetch(`/admin/v2/users`, {
                headers: { Authorization: `Bearer ${token}` },
                signal: AbortSignal.timeout(5000),
            });
            if (res.status === 401 || res.status === 403) { 
                setError("Acesso negado. Token inválido ou expirado."); 
                setLoading(false); 
                return; 
            }
            if (!res.ok) throw new Error(`Erro ${res.status}`);
            setError(""); // Limpa o erro caso a requisição volte a funcionar
            setUsers(await res.json());
        } catch (e: any) {
            if (e.name !== "AbortError") setError(e.message || "Erro ao carregar.");
        } finally { setLoading(false); }
    }, [token]);

    const fetchPlanBrokers = async () => {
        if (!token) return;
        setLoadingPlanBrokers(true);
        try {
            const res = await fetch(`/admin/v2/plans/brokers`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
                const data = await res.json();
                const map: Record<string, string[]> = {};
                data.forEach((p: any) => { map[p.name.toLowerCase()] = p.allowed_brokers || []; });
                setPlanBrokers(map);
            }
        } catch (e) {
            console.error("Erro ao buscar brokers dos planos:", e);
        } finally {
            setLoadingPlanBrokers(false);
        }
    };

    const savePlanBrokers = async (planName: string, brokers: string[]) => {
        if (!token) return;
        setSavingPlanBrokers(planName);
        try {
            const res = await fetch(`/admin/v2/plans/brokers`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                body: JSON.stringify({ plan_name: planName, allowed_brokers: brokers }),
            });
            if (res.ok) {
                setPlanBrokers(prev => ({ ...prev, [planName.toLowerCase()]: brokers }));
                setPlanBrokerMsg({ text: `Brokers do ${planName} atualizados!`, ok: true });
            } else {
                const err = await res.json().catch(() => ({}));
                setPlanBrokerMsg({ text: errToText(err.detail) || "Erro ao salvar", ok: false });
            }
        } catch {
            setPlanBrokerMsg({ text: "Erro de conexão", ok: false });
        } finally {
            setSavingPlanBrokers(null);
            setTimeout(() => setPlanBrokerMsg(null), 3000);
        }
    };

    useEffect(() => {
        if (initialized.current) return;
        initialized.current = true;
        fetchUsers();
        fetchPlanBrokers();
        const iv = setInterval(fetchUsers, 30000);
        return () => clearInterval(iv);
    }, [fetchUsers]);

    // Filtros
    useEffect(() => {
        let list = [...users];
        if (filterStatus === "Online")    list = list.filter(u => u.is_online);
        if (filterStatus === "Liberados") list = list.filter(u => u.liberado);
        if (filterStatus === "Pendentes") list = list.filter(u => !u.liberado);
        if (filterStatus === "Bloqueados") list = list.filter(u => !u.is_active);
        if (filterStatus === "VIP") list = list.filter(u => (u.plan_name || "Free").toLowerCase() === "vip");
        if (filterStatus === "Pro") list = list.filter(u => (u.plan_name || "Free").toLowerCase() === "pro");
        if (filterStatus === "Free") list = list.filter(u => (u.plan_name || "Free").toLowerCase() === "free");
        if (search.trim()) {
            const q = search.toLowerCase();
            list = list.filter(u => u.email.toLowerCase().includes(q) || (u.username || "").toLowerCase().includes(q));
        }
        setFiltered(list);
    }, [search, filterStatus, users]);

    const liberar = async (user: User) => {
        if (!token) return showToast("Sessão inválida. Faça login novamente.", false);
        try {
            const ep = user.liberado
                ? `/admin/bloquear-cliente?email=${encodeURIComponent(user.email)}`
                : `/admin/liberar-cliente?email=${encodeURIComponent(user.email)}`;
            const res = await fetch(ep, { 
                method: "POST", 
                headers: { Authorization: `Bearer ${token}` } 
            });
            if (res.ok) {
                setUsers(prev => prev.map(u => u.id === user.id ? { ...u, liberado: !u.liberado, trading_enabled: !u.liberado } : u));
                showToast(user.liberado ? "Cliente bloqueado" : "Cliente liberado!");
            } else {
                showToast("Erro na alteração de licença.", false);
            }
        } catch {
            showToast("Erro de rede ao alterar licença.", false);
        }
    };

    const toggleActive = async (user: User) => {
        if (!token) return showToast("Sessão inválida.", false);
        try {
            const res = await fetch(`/admin/v2/user/${user.id}/toggle-active`, {
                method: "POST", 
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
                const data = await res.json();
                setUsers(prev => prev.map(u => u.id === user.id ? { ...u, is_active: data.is_active } : u));
                showToast(data.is_active ? "Conta desbloqueada" : "Conta bloqueada");
            } else {
                showToast("Não foi possível alterar o status da conta.", false);
            }
        } catch {
            showToast("Erro de conexão ao alterar conta.", false);
        }
    };

    const saveModal = async () => {
        if (!modal || !token) return;
        setSaving(true); setSaveMsg("");
        try {
            const res = await fetch(`/admin/v2/user/${modal.id}/control?admin_notes=${encodeURIComponent(modalNotes)}`, {
                method: "PATCH", 
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) throw new Error();
            setSaveMsg("Salvo!");
            setUsers(prev => prev.map(u => u.id === modal.id ? { ...u, admin_notes: modalNotes } : u));
            setTimeout(() => { setModal(null); setSaveMsg(""); }, 1200);
        } catch { 
            setSaveMsg("Erro ao salvar."); 
        } finally { setSaving(false); }
    };

    const changePlan = async (user: User, plan: string) => {
        if (!token) return showToast("Sessão inválida.", false);
        try {
            const res = await fetch(`/admin/v2/user/${user.id}/plan`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                body: JSON.stringify({ plan_name: plan }),
            });
            if (res.ok) {
                setUsers(prev => prev.map(u => u.id === user.id ? { ...u, plan_name: plan } : u));
                if (modal && modal.id === user.id) setModal(m => m ? { ...m, plan_name: plan } : m);
                showToast(`Plano alterado para ${plan}`);
            } else {
                showToast("Erro ao alterar o plano.", false);
            }
        } catch {
            showToast("Erro de conexão ao alterar plano.", false);
        }
    };

    const criarCliente = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!token) return setCriarMsg("Acesso não autorizado.");
        setCriando(true); setCriarMsg("");
        try {
            const res = await fetch(`/auth/register`, {
                method: "POST",
                headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                body: JSON.stringify({ email: novoEmail, password: novaSenha, username: novoNome }),
            });
            if (res.ok) {
                setCriarMsg("Cliente criado! Libere o acesso na lista.");
                setNovoEmail(""); setNovoNome(""); setNovaSenha("");
                fetchUsers();
                setTimeout(() => { setShowCriar(false); setCriarMsg(""); }, 2000);
            } else {
                const err = await res.json();
                setCriarMsg(errToText(err.detail) || "Erro ao criar cliente.");
            }
        } catch { setCriarMsg("Erro de conexão."); } finally { setCriando(false); }
    };

    // Stats
    const online     = users.filter(u => u.is_online).length;
    const liberados = users.filter(u => u.liberado).length;
    const pendentes = users.filter(u => !u.liberado && u.is_active).length;

    // Telegram status
    const [telegramInfo, setTelegramInfo] = useState<{ channel_configured: boolean; target_channel: string | null; missing_channel_warning: string | null } | null>(null);

    const fetchTelegramInfo = useCallback(async () => {
        if (!token) return;
        try {
            const res = await fetch(`/telegram/status`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
                const data = await res.json();
                setTelegramInfo(data);
            }
        } catch {}
    }, [token]);

    useEffect(() => {
        if (token) fetchTelegramInfo();
    }, [token, fetchTelegramInfo]);

    return (
        <div className="min-h-screen p-4 md:p-8 bg-slate-950">
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-black text-white tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-cyan-400">Painel Admin</h1>
                    <p className="text-slate-400 mt-1 text-xs">Controle de clientes e licenças</p>
                </div>
                <div className="flex gap-2">
                    <button onClick={() => setShowCriar(!showCriar)}
                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-all">
                        + Novo Cliente
                    </button>
                    <a href="/admin/tokens"
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-all">
                        🔑 Tokens
                    </a>
                    <button onClick={() => { fetchUsers(); fetchTelegramInfo(); }}
                        className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-all">
                        Atualizar
                    </button>
                </div>
            </header>

            {/* Banner de Status do Canal Telegram */}
            {telegramInfo && !telegramInfo.channel_configured && (
                <div className="mb-6 p-4 rounded-2xl border border-rose-500/30 bg-rose-500/10 backdrop-blur-md flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                        <span className="text-2xl">⚠️</span>
                        <div>
                            <p className="text-xs font-black uppercase tracking-widest text-rose-400">Canal Telegram Não Configurado</p>
                            <p className="text-[11px] text-slate-400 mt-0.5">
                                As variáveis <code className="text-rose-300 bg-rose-950/60 px-1.5 py-0.5 rounded font-mono">TELEGRAM_GROUP_NAME</code> ou <code className="text-rose-300 bg-rose-950/60 px-1.5 py-0.5 rounded font-mono">TELEGRAM_CHAT_ID</code> não estão definidas no servidor/Docker. O Copier permanecerá bloqueado até a definição da sala.
                            </p>
                        </div>
                    </div>
                </div>
            )}

            {telegramInfo && telegramInfo.channel_configured && (
                <div className="mb-6 p-3 px-4 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 backdrop-blur-md flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                        <span className="text-emerald-400 font-bold">🎯 Canal de Sinais Ativo:</span>
                        <span className="text-white font-mono bg-slate-900 px-2 py-0.5 rounded-lg border border-slate-800 font-bold">{telegramInfo.target_channel}</span>
                    </div>
                    <span className="text-[10px] text-slate-500 uppercase tracking-widest">Exclusivo</span>
                </div>
            )}


            {/* Criar cliente */}
            {showCriar && (
                <div className="rounded-2xl p-6 mb-6 border border-emerald-500/20 bg-emerald-500/5 backdrop-blur-md">
                    <h2 className="text-sm font-black text-emerald-400 uppercase tracking-widest mb-4">Cadastrar Novo Cliente</h2>
                    <form onSubmit={criarCliente} className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                            <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Nome</label>
                            <input value={novoNome} onChange={e => setNovoNome(e.target.value)} required
                                placeholder="Nome do cliente"
                                className="w-full mt-1 bg-slate-900 border border-slate-700 text-white rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-emerald-500/50" />
                        </div>
                        <div>
                            <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Email</label>
                            <input type="email" value={novoEmail} onChange={e => setNovoEmail(e.target.value)} required
                                placeholder="email@cliente.com"
                                className="w-full mt-1 bg-slate-900 border border-slate-700 text-white rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-emerald-500/50" />
                        </div>
                        <div>
                            <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Senha</label>
                            <input type="password" value={novaSenha} onChange={e => setNovaSenha(e.target.value)} required
                                placeholder="Mínimo 8 caracteres"
                                className="w-full mt-1 bg-slate-900 border border-slate-700 text-white rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-emerald-500/50" />
                        </div>
                        {criarMsg && (
                            <div className={`md:col-span-3 p-3 rounded-xl text-xs font-bold ${criarMsg.includes("criado") ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"}`}>
                                {criarMsg}
                            </div>
                        )}
                        <div className="md:col-span-3 flex gap-3">
                            <button type="submit" disabled={criando}
                                className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-black rounded-xl text-xs uppercase tracking-widest transition-all">
                                {criando ? "Criando..." : "Criar Cliente"}
                            </button>
                            <button type="button" onClick={() => setShowCriar(false)}
                                className="px-6 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold rounded-xl text-xs transition-all">
                                Cancelar
                            </button>
                        </div>
                    </form>
                </div>
            )}

            {error && <div className="mb-4 p-4 bg-red-500/10 border border-red-500/20 rounded-2xl text-red-400 text-sm font-bold">{error}</div>}

            {/* Stats */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
                {[
                    { label: "Total", value: users.length, color: "text-white" },
                    { label: "Online", value: online, color: "text-emerald-400", pulse: true },
                    { label: "Liberados", value: liberados, color: "text-blue-400" },
                    { label: "Pendentes", value: pendentes, color: "text-yellow-400" },
                ].map(s => (
                    <div key={s.label} className="rounded-2xl p-4 bg-slate-900 border border-slate-800">
                        <p className="text-slate-500 text-[10px] font-black uppercase tracking-widest mb-1">{s.label}</p>
                        <p className={`text-3xl font-black ${s.color} ${s.pulse ? "animate-pulse" : ""}`}>{s.value}</p>
                    </div>
                ))}
            </div>

            {/* Plan Brokers Management */}
            <div className="mb-6 bg-slate-900/50 border border-slate-800 rounded-2xl p-6">
                <div className="flex items-center gap-2 mb-4">
                    <span className="text-lg">🔧</span>
                    <h2 className="text-sm font-black text-white uppercase tracking-widest">Brokers por Plano</h2>
                </div>
                <p className="text-xs text-slate-400 mb-4">
                    Defina quais corretoras cada plano pode usar. O cliente só verá as permitidas.
                </p>
                {loadingPlanBrokers ? (
                    <div className="text-center text-slate-500 text-sm py-4">Carregando...</div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {["VIP", "Pro", "Free"].map(plan => {
                            const brokers = planBrokers[plan] || [];
                            const allBrokers = [
                                { id: "iqoption", label: "IQ Option", icon: "📊" },
                                { id: "quotex", label: "Quotex", icon: "📈" },
                                { id: "pocketoption", label: "Pocket Option", icon: "🟣" },
                                { id: "deriv", label: "Deriv / Binary", icon: "🔷" },
                            ];
                            return (
                                <div key={plan} className="bg-slate-950/50 border border-slate-800 rounded-xl p-4">
                                    <div className="flex items-center justify-between mb-3">
                                        <span className={`px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest border ${
                                            plan === "VIP" ? "bg-amber-500/15 text-amber-400 border-amber-500/30" :
                                            plan === "Pro" ? "bg-blue-500/15 text-blue-400 border-blue-500/30" :
                                            "bg-slate-700/40 text-slate-400 border-slate-600/40"
                                        }`}>
                                            {plan === "VIP" ? "👑 VIP" : plan === "Pro" ? "⭐ Pro" : "Free"}
                                        </span>
                                    </div>
                                    <div className="grid grid-cols-2 gap-2 mb-3">
                                        {allBrokers.map(b => (
                                            <label key={b.id} className={`flex items-center gap-2 p-2 rounded-lg text-xs font-bold border transition-all cursor-pointer ${
                                                brokers.includes(b.id)
                                                    ? "bg-blue-500/10 border-blue-500/40 text-blue-400"
                                                    : "bg-slate-950/50 border-slate-800 text-slate-500 hover:border-slate-700"
                                            }`}>
                                                <input type="checkbox"
                                                    checked={brokers.includes(b.id)}
                                                    onChange={() => {
                                                        const newBrokers = brokers.includes(b.id)
                                                            ? brokers.filter(x => x !== b.id)
                                                            : [...brokers, b.id];
                                                        savePlanBrokers(plan, newBrokers);
                                                    }}
                                                    disabled={savingPlanBrokers === plan}
                                                    className="w-4 h-4 accent-blue-500" />
                                                <span className="flex items-center gap-1">{b.icon} {b.label}</span>
                                            </label>
                                        ))}
                                    </div>
                                    {savingPlanBrokers === plan && (
                                        <div className="text-center text-xs text-slate-500 py-2">Salvando...</div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                )}
                {planBrokerMsg && (
                    <div className={`mt-3 p-3 rounded-xl text-xs font-bold border ${
                        planBrokerMsg.ok ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" : "bg-rose-500/10 border-rose-500/20 text-rose-400"
                    }`}>
                        {planBrokerMsg.text}
                    </div>
                )}
            </div>

            {/* Filtros */}
            <div className="flex flex-wrap gap-2 mb-4">
                <input type="text" placeholder="Buscar email ou nome..."
                    value={search} onChange={e => setSearch(e.target.value)}
                    className="flex-1 min-w-48 px-4 py-2 bg-slate-900 border border-slate-700 rounded-xl text-white text-sm placeholder-slate-600 outline-none focus:border-blue-500" />
                 <div className="flex gap-2 flex-wrap">
                    {["Todos", "VIP", "Pro", "Free", "Online", "Liberados", "Pendentes", "Bloqueados"].map(f => (
                        <button key={f} onClick={() => setFilter(f)}
                            className={`px-3 py-2 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${filterStatus === f ? "bg-blue-600 text-white" : "bg-slate-800 text-slate-400 hover:bg-slate-700"}`}>
                            {f}
                        </button>
                    ))}
                </div>
            </div>

            {/* Tabela */}
            {loading ? (
                <div className="py-20 text-center text-slate-600 text-xs font-black uppercase tracking-widest animate-pulse">Carregando...</div>
            ) : (
                <div className="rounded-2xl overflow-hidden border border-slate-800 bg-slate-900/50">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-slate-800 text-[10px] text-slate-500 uppercase tracking-widest bg-slate-900">
                                    <th className="text-left px-4 py-3">Status</th>
                                    <th className="text-left px-4 py-3">Cliente</th>
                                    <th className="text-center px-4 py-3">Licença</th>
                                    <th className="text-center px-4 py-3">Trading</th>
                                    <th className="text-right px-4 py-3">Lucro</th>
                                    <th className="text-center px-4 py-3">Ações</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filtered.length === 0 && (
                                    <tr><td colSpan={6} className="py-12 text-center text-slate-600 text-xs font-bold uppercase">Nenhum usuário encontrado.</td></tr>
                                )}
                                {filtered.map((u, i) => (
                                    <tr key={u.id} className={`border-b border-slate-800/40 hover:bg-slate-800/20 transition-colors ${i % 2 === 0 ? "" : "bg-slate-900/10"}`}>
                                        <td className="px-4 py-3">
                                            <div className="flex items-center gap-2">
                                                <span className={`w-2.5 h-2.5 rounded-full ${u.is_online ? "bg-emerald-500 animate-pulse" : u.is_active ? "bg-slate-500" : "bg-red-500"}`}></span>
                                                <span className="text-[10px] text-slate-500">{u.is_online ? "Online" : u.is_active ? "Offline" : "Bloqueado"}</span>
                                            </div>
                                        </td>
                                        <td className="px-4 py-3">
                                            <p className="font-bold text-white text-sm">{u.username || "—"}</p>
                                            <p className="text-slate-500 text-xs">{u.email}</p>
                                            {u.is_admin && <span className="text-[9px] text-yellow-400 font-black">ADMIN</span>}
                                        </td>
                                        <td className="px-4 py-3 text-center">
                                            <div className="flex flex-col items-center gap-1.5">
                                                {planBadge(u.plan_name)}
                                                <button onClick={() => liberar(u)}
                                                    className={`px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest transition-all ${u.liberado ? "bg-emerald-500/10 text-emerald-400 hover:bg-red-500/10 hover:text-red-400" : "bg-yellow-500/10 text-yellow-400 hover:bg-emerald-500/20 hover:text-emerald-400"}`}>
                                                    {u.liberado ? "Liberado" : "Pendente"}
                                                </button>
                                            </div>
                                        </td>
                                        <td className="px-4 py-3 text-center">
                                            <span className={`text-[10px] font-black ${u.trading_enabled ? "text-emerald-400" : "text-red-400"}`}>
                                                {u.trading_enabled ? "ON" : "OFF"}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-right font-mono text-emerald-400 font-bold text-sm">
                                            ${u.total_profit.toFixed(2)}
                                        </td>
                                        <td className="px-4 py-3 text-center">
                                            <div className="flex items-center justify-center gap-2">
                                                <button onClick={() => liberar(u)}
                                                    className={`px-2 py-1 rounded-lg text-[10px] font-black uppercase transition-all ${u.liberado ? "bg-red-500/10 text-red-400 hover:bg-red-500/20" : "bg-emerald-600 text-white hover:bg-emerald-500"}`}>
                                                    {u.liberado ? "Revogar" : "Liberar"}
                                                </button>
                                                <button onClick={() => { setModal(u); setModalNotes(u.admin_notes || ""); setModalPlan(u.plan_name || "Free"); setSaveMsg(""); }}
                                                    className="px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-[10px] font-black uppercase transition-all">
                                                    Gerir
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* Toast */}
            {toast && (
                <div className={`fixed bottom-6 right-6 px-5 py-3 rounded-xl text-sm font-bold shadow-2xl border z-50 ${toast.ok ? "bg-emerald-900 border-emerald-500/30 text-emerald-400" : "bg-red-900 border-red-500/30 text-red-400"}`}>
                    {toast.text}
                </div>
            )}

            {/* Toast Plan Brokers */}
            {planBrokerMsg && (
                <div className={`fixed bottom-6 right-6 px-5 py-3 rounded-xl text-sm font-bold shadow-2xl border z-50 ${planBrokerMsg.ok ? "bg-emerald-900 border-emerald-500/30 text-emerald-400" : "bg-red-900 border-red-500/30 text-red-400"}`}>
                    {planBrokerMsg.text}
                </div>
            )}

            {/* Modal */}
            {modal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
                    <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-md p-6 shadow-2xl">
                        <h2 className="text-lg font-black text-white mb-1">Gerir Cliente</h2>
                        <p className="text-slate-400 text-sm mb-5">{modal.email}</p>

                        <div className="grid grid-cols-3 gap-3 mb-5">
                            {[
                                { label: "Plano", value: modal.plan_name || "Free", color: "text-amber-400" },
                                { label: "Licença", value: modal.liberado ? "Liberado" : "Pendente", color: modal.liberado ? "text-emerald-400" : "text-yellow-400" },
                                { label: "Conta", value: modal.is_active ? "Ativa" : "Bloqueada", color: modal.is_active ? "text-emerald-400" : "text-red-400" },
                                { label: "Online", value: modal.is_online ? "Sim" : "Não", color: modal.is_online ? "text-emerald-400" : "text-slate-400" },
                            ].map(item => (
                                <div key={item.label} className="bg-slate-800/50 rounded-xl p-3 text-center">
                                    <p className="text-[9px] text-slate-500 uppercase tracking-widest mb-1">{item.label}</p>
                                    <p className={`font-black text-sm ${item.color}`}>{item.value}</p>
                                </div>
                            ))}
                        </div>

                        {/* Ações rápidas */}
                        <div className="grid grid-cols-2 gap-2 mb-5">
                            <button onClick={() => { liberar(modal); setModal(null); }}
                                className={`py-2.5 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${modal.liberado ? "bg-red-500/10 text-red-400 hover:bg-red-500/20" : "bg-emerald-600 text-white hover:bg-emerald-500"}`}>
                                {modal.liberado ? "Revogar Licença" : "Liberar Acesso"}
                            </button>
                            <button onClick={() => { toggleActive(modal); setModal(null); }}
                                className={`py-2.5 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${modal.is_active ? "bg-red-500/10 text-red-400 hover:bg-red-500/20" : "bg-slate-700 text-slate-300 hover:bg-slate-600"}`}>
                                {modal.is_active ? "Bloquear Conta" : "Desbloquear"}
                            </button>
                        </div>

                        {/* Plano */}
                        <div className="mb-5">
                            <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Tipo de Conta (Plano)</label>
                            <div className="flex gap-2 mt-2">
                                {["Free", "Pro", "VIP"].map(p => (
                                    <button key={p} onClick={() => changePlan(modal, p)}
                                        className={`flex-1 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${
                                            (modal.plan_name || "Free") === p
                                                ? (p === "VIP" ? "bg-amber-500/20 text-amber-400 border border-amber-500/40"
                                                   : p === "Pro" ? "bg-blue-500/20 text-blue-400 border border-blue-500/40"
                                                   : "bg-slate-600/30 text-slate-200 border border-slate-500/40")
                                                : "bg-slate-800 text-slate-400 hover:bg-slate-700"
                                        }`}>
                                        {p === "VIP" ? "👑 VIP" : p === "Pro" ? "⭐ Pro" : "Free"}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Notas */}
                        <div className="mb-5">
                            <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Notas do Admin</label>
                            <textarea value={modalNotes} onChange={e => setModalNotes(e.target.value)}
                                placeholder="Observações sobre este cliente..."
                                rows={3}
                                className="w-full mt-2 bg-slate-800/50 border border-slate-700 text-white rounded-xl p-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/50 resize-none" />
                        </div>

                        {saveMsg && <p className={`text-sm mb-3 font-bold ${saveMsg === "Salvo!" ? "text-emerald-400" : "text-red-400"}`}>{saveMsg}</p>}

                        <div className="flex gap-3">
                            <button onClick={() => setModal(null)}
                                className="flex-1 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl font-bold text-sm transition-all">
                                Fechar
                            </button>
                            <button onClick={saveModal} disabled={saving}
                                className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-xl font-black text-sm uppercase tracking-widest transition-all">
                                {saving ? "Salvando..." : "Salvar Notas"}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
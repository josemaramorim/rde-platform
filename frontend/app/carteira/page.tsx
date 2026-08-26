"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useEstado } from "@/hooks/useEstado";
import { API_URL } from "@/lib/constants";

const PLANS = [
    {
        id: "basic",
        name: "Basic",
        price: 49,
        color: "blue",
        signals: 5,
        meta_pct: 2,
        description: "5 sinais positivos até bater a meta de 2% ao dia",
        features: ["5 sinais/dia", "Meta 2% ao dia", "1 corretora", "Suporte básico"],
    },
    {
        id: "pro",
        name: "Pro",
        price: 149,
        color: "emerald",
        signals: 30,
        meta_pct: 3,
        description: "Até 30 sinais positivos até bater a meta de 3% ao dia",
        features: ["30 sinais/dia", "Meta 3% ao dia", "3 corretoras", "Suporte prioritário", "Planilha IA"],
        popular: true,
    },
    {
        id: "vip",
        name: "VIP",
        price: 300,
        color: "purple",
        signals: 999,
        meta_pct: 10,
        description: "Livre para todos os sinais até bater a meta de 10% ao dia",
        features: ["Sinais ilimitados", "Meta 10% ao dia", "Todas as corretoras", "Suporte VIP 24h", "Planilha IA", "Acesso antecipado"],
    },
];

export default function CarteiraPage() {
    const router = useRouter();
    // 🔑 Obtendo o token centralizado e reativo do hook global
    const { token } = useEstado();

    const [currentPlan, setCurrentPlan] = useState<any>(null);
    const [planExpires, setPlanExpires] = useState<string | null>(null);
    const [loading, setLoading] = useState<string | null>(null);
    const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);

    useEffect(() => {
        const fetchPlan = async () => {
            if (!token) return;
            try {
                const res = await fetch(`/account/me`, {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (res.ok) {
                    const data = await res.json();
                    const planName = data.plan_name?.toLowerCase() || "basic";
                    setCurrentPlan(PLANS.find(p => p.id === planName) || PLANS[0]);
                    if (data.plan_expires_at) {
                        setPlanExpires(new Date(data.plan_expires_at).toLocaleDateString("pt-BR"));
                    }
                }
            } catch { /* silencioso */ }
        };
        fetchPlan();
    }, [token]);

    const handleUpgrade = async (planId: string) => {
        if (!token) { router.push("/login"); return; }
        setLoading(planId);
        setMsg(null);
        try {
            const res = await fetch(`/create-checkout-session?plan_name=${planId.charAt(0).toUpperCase() + planId.slice(1)}`, {
                method: "POST",
                headers: { Authorization: `Bearer ${token}` },
            });
            const data = await res.json();
            if (data.url) {
                window.open(data.url, "_blank");
            } else if (data.error) {
                setMsg({ type: "err", text: `Erro: ${data.error}` });
            } else {
                setMsg({ type: "err", text: "Resposta inesperada do servidor." });
            }
        } catch {
            setMsg({ type: "err", text: "Erro ao processar. Tente novamente." });
        } finally {
            setLoading(null);
        }
    };

    return (
        <div className="min-h-screen p-6 md:p-10 bg-slate-950 overflow-x-hidden">
            <header className="mb-10">
                <h1 className="text-4xl font-black text-white tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-cyan-400">Carteira & Planos</h1>
                <p className="text-slate-400 mt-2 font-light">Escolha o plano ideal para sua operação.</p>
            </header>

            {/* Plano atual */}
            {currentPlan && (
                <div className="rounded-2xl p-6 mb-10 border border-blue-500/20 bg-blue-500/5 backdrop-blur-md">
                    <div className="flex items-center justify-between flex-wrap gap-4">
                        <div>
                            <p className="text-[10px] font-black text-blue-400 uppercase tracking-widest mb-1">Plano Atual</p>
                            <p className="text-2xl font-black text-white">{currentPlan.name}</p>
                            <p className="text-slate-400 text-sm mt-1">{currentPlan.description}</p>
                        </div>
                        <div className="text-right">
                            <p className="text-3xl font-black text-white">R$ {currentPlan.price}<span className="text-slate-500 text-sm font-medium">/mês</span></p>
                            {planExpires && <p className="text-[10px] text-slate-500 mt-1">Expira em {planExpires}</p>}
                        </div>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                        {currentPlan.features.map((f: string) => (
                            <span key={f} className="px-3 py-1 bg-blue-500/10 text-blue-400 text-[10px] font-black rounded-full border border-blue-500/20">{f}</span>
                        ))}
                    </div>
                </div>
            )}

            {msg && (
                <div className={`p-4 rounded-xl mb-6 text-sm font-bold border ${msg.type === "ok" ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" : "bg-red-500/10 border-red-500/20 text-red-400"}`}>
                    {msg.text}
                </div>
            )}

            {/* Cards dos planos */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
                {PLANS.map(plan => {
                    const isActive = currentPlan?.id === plan.id;
                    const colors: Record<string, string> = {
                        blue: "border-blue-500/30 bg-blue-500/5",
                        emerald: "border-emerald-500/30 bg-emerald-500/5",
                        purple: "border-purple-500/30 bg-purple-500/5",
                    };
                    const btnColors: Record<string, string> = {
                        blue: "bg-blue-600 hover:bg-blue-500 shadow-blue-600/20",
                        emerald: "bg-emerald-600 hover:bg-emerald-500 shadow-emerald-600/20",
                        purple: "bg-purple-600 hover:bg-purple-500 shadow-purple-600/20",
                    };
                    const textColors: Record<string, string> = {
                        blue: "text-blue-400",
                        emerald: "text-emerald-400",
                        purple: "text-purple-400",
                    };
                    return (
                        <div key={plan.id} className={`rounded-2xl p-6 border relative bg-slate-900/40 backdrop-blur-md ${isActive ? colors[plan.color] : "border-slate-800"} transition-all hover:border-slate-600`}>
                            {plan.popular && (
                                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 bg-emerald-500 text-slate-950 text-[10px] font-black uppercase tracking-widest rounded-full">
                                    Mais Popular
                                </div>
                            )}
                            {isActive && (
                                <div className="absolute -top-3 right-4 px-3 py-1 bg-blue-500 text-white text-[10px] font-black uppercase tracking-widest rounded-full">
                                    Ativo
                                </div>
                            )}
                            <p className={`text-[10px] font-black uppercase tracking-widest mb-2 ${textColors[plan.color ?? 'blue']}`}>{plan.name}</p>
                            <p className="text-3xl font-black text-white mb-1">R$ {plan.price}<span className="text-slate-500 text-sm font-medium">/mês</span></p>
                            <p className="text-slate-400 text-xs mb-6 leading-relaxed">{plan.description}</p>

                            <div className="space-y-2 mb-6">
                                {plan.features.map(f => (
                                    <div key={f} className="flex items-center gap-2 text-xs text-slate-300">
                                        <span className={`w-1.5 h-1.5 rounded-full ${(textColors[plan.color ?? 'blue'] ?? '').replace("text-", "bg-")}`}></span>
                                        {f}
                                    </div>
                                ))}
                            </div>

                            <button
                                onClick={() => !isActive && handleUpgrade(plan.id)}
                                disabled={isActive || loading === plan.id}
                                className={`w-full py-3 rounded-xl text-xs font-black uppercase tracking-widest transition-all shadow-lg ${isActive ? "bg-slate-800 text-slate-500 cursor-default" : `${btnColors[plan.color ?? 'blue']} text-white active:scale-95`}`}
                            >
                                {loading === plan.id ? "Processando..." : isActive ? "Plano Atual" : `Assinar ${plan.name}`}
                            </button>
                        </div>
                    );
                })}
            </div>

            {/* Limites por plano */}
            <div className="rounded-2xl p-6 bg-slate-900 border border-slate-800">
                <h2 className="text-sm font-black text-white uppercase tracking-widest mb-6">Comparativo de Limites</h2>
                <div className="overflow-x-auto">
                    <table className="w-full text-left">
                        <thead>
                            <tr className="border-b border-slate-800">
                                <th className="pb-4 text-[10px] font-black text-slate-500 uppercase tracking-widest">Recurso</th>
                                <th className="pb-4 text-[10px] font-black text-blue-400 uppercase tracking-widest text-center">Basic</th>
                                <th className="pb-4 text-[10px] font-black text-emerald-400 uppercase tracking-widest text-center">Pro</th>
                                <th className="pb-4 text-[10px] font-black text-purple-400 uppercase tracking-widest text-center">VIP</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60">
                            {[
                                ["Sinais por dia", "5", "30", "Ilimitado"],
                                ["Meta diária", "2%", "3%", "10%"],
                                ["Corretoras", "1", "3", "Todas"],
                                ["Planilha IA", "❌", "✅", "✅"],
                                ["Suporte", "Básico", "Prioritário", "VIP 24h"],
                                ["Preço/mês", "R$ 49", "R$ 149", "R$ 300"],
                            ].map(([feature, basic, pro, vip]) => (
                                <tr key={feature}>
                                    <td className="py-3 text-slate-400 text-xs">{feature}</td>
                                    <td className="py-3 text-center text-xs text-white font-bold">{basic}</td>
                                    <td className="py-3 text-center text-xs text-white font-bold">{pro}</td>
                                    <td className="py-3 text-center text-xs text-white font-bold">{vip}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
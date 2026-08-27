"use client";

import { useState, useEffect, useCallback } from "react";
import { useEstado } from "@/hooks/useEstado";
import { API_URL } from "@/lib/constants";

interface LicencaResumo {
  total: number;
  disponiveis: number;
  ativos: number;
  expirados: number;
  revogados: number;
}

interface Token {
  id: string;
  codigo: string;
  plano: string;
  status: string;
  expiracao_dias: number;
  expira_em?: string;
  usado_por?: string;
  destinatario?: string;
  ultimo_ip?: string;
  ultima_atividade?: string;
}

export default function AdminTokensPage() {
  const { token } = useEstado();
  const [tokens, setTokens] = useState<Token[]>([]);
  const [resumo, setResumo] = useState<LicencaResumo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState<{ text: string; ok: boolean } | null>(null);
  const [statusFilter, setStatusFilter] = useState("");

  const [plano, setPlano] = useState("Basic");
  const [quantidade, setQuantidade] = useState(1);
  const [expiracaoDias, setExpiracaoDias] = useState(30);
  const [destinatario, setDestinatario] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generatedTokens, setGeneratedTokens] = useState<string[]>([]);

  const showFeedback = (text: string, ok: boolean = true) => {
    setFeedback({ text, ok });
    setTimeout(() => setFeedback(null), 3000);
  };

  const fetchTokens = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      let url = `${API_URL}/admin/tokens`;
      if (statusFilter) url += `?status=${statusFilter}`;
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setTokens(await res.json());
      } else {
        const text = await res.text().catch(() => "");
        setError(`Erro ${res.status}: ${text || "Falha ao carregar tokens."}`);
      }
    } catch {
      setError("Erro ao carregar tokens.");
    } finally {
      setLoading(false);
    }
  }, [token, statusFilter]);

  const fetchResumo = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_URL}/admin/licencas/resumo`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setResumo(await res.json());
    } catch {
      // silent
    }
  }, [token]);

  useEffect(() => {
    fetchTokens();
    fetchResumo();
    const interval = setInterval(fetchResumo, 10000);
    return () => clearInterval(interval);
  }, [fetchTokens, fetchResumo]);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setGenerating(true);
    setGeneratedTokens([]);
    try {
      const res = await fetch(`${API_URL}/admin/tokens/gerar`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          plano,
          quantidade,
          expiracao_dias: expiracaoDias,
          destinatario: destinatario || undefined,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setGeneratedTokens(data.tokens);
        showFeedback(`${quantidade} token(s) gerados!`);
        fetchTokens();
        fetchResumo();
      } else {
        showFeedback("Erro ao gerar tokens.", false);
      }
    } catch {
      showFeedback("Erro de conexão.", false);
    } finally {
      setGenerating(false);
    }
  };

  const handleRevoke = async (tokenId: string) => {
    if (!token || !confirm("Revogar este token? O cliente será bloqueado.")) return;
    try {
      const res = await fetch(`${API_URL}/admin/tokens/${tokenId}/revogar`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        showFeedback("Token revogado.");
        fetchTokens();
        fetchResumo();
      } else {
        showFeedback("Erro ao revogar.", false);
      }
    } catch {
      showFeedback("Erro de conexão.", false);
    }
  };

  return (
    <div className="min-h-screen p-4 md:p-8 bg-slate-950">
      <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black text-white tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-cyan-400">
            Tokens de Licença
          </h1>
          <p className="text-slate-400 mt-1 text-xs">
            Gerencie tokens de ativação da plataforma
          </p>
        </div>
        <a
          href="/admin"
          className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-all"
        >
          ← Clientes
        </a>
      </header>

      {error && (
        <div className="mb-4 p-4 bg-red-500/10 border border-red-500/20 rounded-2xl text-red-400 text-sm font-bold">
          {error}
        </div>
      )}

      {resumo && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
          {[
            { label: "Total", value: resumo.total, color: "text-white" },
            { label: "Disponíveis", value: resumo.disponiveis, color: "text-emerald-400" },
            { label: "Ativos", value: resumo.ativos, color: "text-blue-400", pulse: true },
            { label: "Expirados", value: resumo.expirados, color: "text-yellow-400" },
            { label: "Revogados", value: resumo.revogados, color: "text-red-400" },
          ].map((item) => (
            <div key={item.label} className="rounded-2xl p-4 bg-slate-900 border border-slate-800">
              <p className="text-slate-500 text-[10px] font-black uppercase tracking-widest mb-1">
                {item.label}
              </p>
              <p className={`text-3xl font-black ${item.color} ${item.pulse ? "animate-pulse" : ""}`}>
                {item.value}
              </p>
            </div>
          ))}
        </div>
      )}

      <div className="rounded-2xl p-6 mb-6 border border-emerald-500/20 bg-emerald-500/5 backdrop-blur-md">
        <h2 className="text-sm font-black text-emerald-400 uppercase tracking-widest mb-4">
          Gerar Novos Tokens
        </h2>
        <form onSubmit={handleGenerate} className="grid grid-cols-1 md:grid-cols-5 gap-4">
          <div>
            <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Plano</label>
            <select value={plano} onChange={(e) => setPlano(e.target.value)}
              className="w-full mt-1 bg-slate-900 border border-slate-700 text-white rounded-xl px-4 py-2.5 text-sm outline-none">
              <option value="Basic">Basic</option>
              <option value="Pro">Pro</option>
              <option value="VIP">VIP</option>
            </select>
          </div>
          <div>
            <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Qtd</label>
            <input type="number" min={1} max={100} value={quantidade}
              onChange={(e) => setQuantidade(Number(e.target.value))}
              className="w-full mt-1 bg-slate-900 border border-slate-700 text-white rounded-xl px-4 py-2.5 text-sm outline-none" />
          </div>
          <div>
            <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Validade</label>
            <select value={expiracaoDias} onChange={(e) => setExpiracaoDias(Number(e.target.value))}
              className="w-full mt-1 bg-slate-900 border border-slate-700 text-white rounded-xl px-4 py-2.5 text-sm outline-none">
              {[7, 15, 30, 60, 90, 180, 365].map(d => (
                <option key={d} value={d}>{d} dias</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Cliente (email)</label>
            <input type="email" value={destinatario} onChange={(e) => setDestinatario(e.target.value)}
              placeholder="opcional"
              className="w-full mt-1 bg-slate-900 border border-slate-700 text-white rounded-xl px-4 py-2.5 text-sm outline-none placeholder:text-slate-600" />
          </div>
          <div className="flex items-end">
            <button type="submit" disabled={generating}
              className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-black rounded-xl text-xs uppercase tracking-widest transition-all">
              {generating ? "Gerando..." : "Gerar Token(s)"}
            </button>
          </div>
        </form>

        {generatedTokens.length > 0 && (
          <div className="mt-4 p-4 bg-slate-900 rounded-xl border border-emerald-500/20">
            <p className="text-emerald-400 text-xs font-black mb-2">Tokens gerados (copie e distribua):</p>
            <div className="space-y-1">
              {generatedTokens.map((tok, i) => (
                <div key={i} className="flex items-center gap-2">
                  <code className="flex-1 text-xs bg-slate-950 px-3 py-1.5 rounded-lg text-emerald-300 font-mono select-all">{tok}</code>
                  <button onClick={() => { navigator.clipboard.writeText(tok); showFeedback("Copiado!"); }}
                    className="text-[10px] text-blue-400 hover:text-blue-300 font-black uppercase">Copiar</button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        {["", "disponivel", "ativo", "expirado", "revogado"].map((s) => (
          <button key={s} onClick={() => setStatusFilter(s)}
            className={`px-3 py-2 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${statusFilter === s ? "bg-blue-600 text-white" : "bg-slate-800 text-slate-400 hover:bg-slate-700"}`}>
            {s || "Todos"}
          </button>
        ))}
        <button onClick={fetchTokens}
          className="px-3 py-2 bg-slate-800 text-slate-400 rounded-xl text-xs font-bold hover:bg-slate-700 transition-all ml-auto">
          Atualizar
        </button>
      </div>

      {loading ? (
        <div className="py-20 text-center text-slate-600 text-xs font-black uppercase tracking-widest animate-pulse">Carregando...</div>
      ) : (
        <div className="rounded-2xl overflow-hidden border border-slate-800 bg-slate-900/50">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-[10px] text-slate-500 uppercase tracking-widest bg-slate-900">
                  <th className="text-left px-4 py-3">Token</th>
                  <th className="text-center px-4 py-3">Plano</th>
                  <th className="text-center px-4 py-3">Status</th>
                  <th className="text-center px-4 py-3">Validade</th>
                  <th className="text-left px-4 py-3">Cliente</th>
                  <th className="text-left px-4 py-3">Destinatário</th>
                  <th className="text-center px-4 py-3">IP</th>
                  <th className="text-center px-4 py-3">Atividade</th>
                  <th className="text-center px-4 py-3">Ações</th>
                </tr>
              </thead>
              <tbody>
                {tokens.length === 0 && (
                  <tr><td colSpan={9} className="py-12 text-center text-slate-600 text-xs font-bold uppercase">Nenhum token encontrado.</td></tr>
                )}
                {tokens.map((tok, i) => (
                  <tr key={tok.id} className={`border-b border-slate-800/40 hover:bg-slate-800/20 ${i % 2 === 0 ? "" : "bg-slate-900/10"}`}>
                    <td className="px-4 py-3"><code className="text-xs text-slate-300 font-mono">{tok.codigo}</code></td>
                    <td className="px-4 py-3 text-center"><span className="text-xs font-black text-white">{tok.plano}</span></td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-2 py-0.5 rounded-lg text-[10px] font-black border ${
                        ({ disponivel: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
                           ativo: "bg-blue-500/10 text-blue-400 border-blue-500/20",
                           expirado: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
                           revogado: "bg-red-500/10 text-red-400 border-red-500/20" })[tok.status] || "bg-slate-800 text-slate-400"
                      }`}>{tok.status}</span>
                    </td>
                    <td className="px-4 py-3 text-center text-xs text-slate-400">
                      {tok.expiracao_dias}d{tok.expira_em && <span className="block text-[10px] text-slate-500">{new Date(tok.expira_em).toLocaleDateString()}</span>}
                    </td>
                    <td className="px-4 py-3"><span className="text-xs text-slate-300">{tok.usado_por || "—"}</span></td>
                    <td className="px-4 py-3"><span className="text-xs text-slate-500">{tok.destinatario || "—"}</span></td>
                    <td className="px-4 py-3 text-center text-[10px] text-slate-500">{tok.ultimo_ip || "—"}</td>
                    <td className="px-4 py-3 text-center text-[10px] text-slate-500">{tok.ultima_atividade ? new Date(tok.ultima_atividade).toLocaleString() : "—"}</td>
                    <td className="px-4 py-3 text-center">
                      {tok.status === "ativo" && (
                        <button onClick={() => handleRevoke(tok.id)}
                          className="px-2 py-1 bg-red-500/10 text-red-400 hover:bg-red-500/20 rounded-lg text-[10px] font-black uppercase transition-all">Revogar</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {feedback && (
        <div className={`fixed bottom-6 right-6 px-5 py-3 rounded-xl text-sm font-bold shadow-2xl border z-50 ${
          feedback.ok ? "bg-emerald-900 border-emerald-500/30 text-emerald-400" : "bg-red-900 border-red-500/30 text-red-400"
        }`}>
          {feedback.text}
        </div>
      )}
    </div>
  );
}

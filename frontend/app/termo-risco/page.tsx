"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useEstado } from "@/hooks/useEstado";
import { API_URL } from "@/lib/constants";

const getToken = () => sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token") || "";

function validateCpf(raw: string): boolean {
  const cpf = raw.replace(/\D/g, "");
  if (cpf.length !== 11) return false;
  if (/^(\d)\1{10}$/.test(cpf)) return false;
  const digits = cpf.split("").map(Number);
  let sum = 0;
  for (let i = 0; i < 9; i++) sum += (digits[i] ?? 0) * (10 - i);
  let d1 = 11 - (sum % 11);
  if (d1 >= 10) d1 = 0;
  if (d1 !== (digits[9] ?? -1)) return false;
  sum = 0;
  for (let i = 0; i < 10; i++) sum += (digits[i] ?? 0) * (11 - i);
  let d2 = 11 - (sum % 11);
  if (d2 >= 10) d2 = 0;
  return d2 === (digits[10] ?? -1);
}

function formatCpf(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 11);
  return digits
    .replace(/(\d{3})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
}

export default function TermoRiscoPage() {
  const router = useRouter();
  const { estado } = useEstado();

  const [termText, setTermText] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [cpf, setCpf] = useState("");
  const [cpfError, setCpfError] = useState("");
  const [readConfirm, setReadConfirm] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<"loading" | "pending" | "accepted" | "error">("loading");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    const token = getToken();
    if (!token) { router.push("/login"); return; }

    Promise.all([
      fetch(`${API_URL}/risk-term/text`, { headers: { Authorization: `Bearer ${token}` } }),
      fetch(`${API_URL}/risk-term/status`, { headers: { Authorization: `Bearer ${token}` } }),
      fetch(`${API_URL}/user/estado`, { headers: { Authorization: `Bearer ${token}` } }),
    ]).then(async ([resTerm, resStatus, resUser]) => {
      if (resTerm.status === 401 || resStatus.status === 401 || resUser.status === 401) {
        localStorage.removeItem("rde_token");
        sessionStorage.removeItem("rde_token");
        router.push("/login");
        return;
      }
      const termData = await resTerm.json();
      const termStatus = await resStatus.json();
      const userData = await resUser.json();

      if (termData.text) setTermText(termData.text);
      if (userData.email) setEmail(userData.email);
      if (userData.username) setFullName(userData.username);
      if (termStatus.accepted) {
        setStatus("accepted");
      } else {
        setStatus("pending");
      }
    }).catch(() => setStatus("error"));
  }, []);

  const handleSubmit = async () => {
    if (!readConfirm || !accepted || !fullName || !email || !cpf) {
      setMsg("Preencha todos os campos e confirme a leitura.");
      return;
    }
    if (!validateCpf(cpf)) {
      setCpfError("CPF inválido. Verifique os números digitados.");
      setMsg("CPF inválido. Corrija antes de prosseguir.");
      return;
    }
    setLoading(true);
    setMsg("");
    try {
      const token = getToken();
      const res = await fetch(`${API_URL}/risk-term/accept`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ full_name: fullName, email, cpf_or_id: cpf, accepted: true }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        setStatus("accepted");
        setMsg("Termo aceito com sucesso!");
      } else {
        setMsg(data.detail || data.message || "Erro ao salvar. Tente novamente.");
      }
    } catch (err: any) {
      setMsg(err?.message || "Erro de conexão.");
    } finally {
      setLoading(false);
    }
  };

  if (status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-slate-400 text-sm">Carregando termo...</p>
        </div>
      </div>
    );
  }

  if (status === "accepted") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
        <div className="max-w-md w-full mx-4">
          <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-2xl p-8 text-center">
            <div className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
              <span className="text-3xl">✅</span>
            </div>
            <h2 className="text-xl font-black text-emerald-400 mb-3">Termo Aceito</h2>
            <p className="text-slate-400 text-sm mb-6">
              Você já aceitou o Termo de Responsabilidade e Assunção de Risco.
              Pode acessar a plataforma normalmente.
            </p>
            <button onClick={() => router.push("/dashboard")}
              className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-black rounded-xl text-xs uppercase tracking-widest transition-all">
              Ir para o Dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen py-8 px-4 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-black text-white tracking-tight">Termo de Responsabilidade e Assunção de Risco</h1>
          <p className="text-slate-500 mt-1 text-sm">RDE Platform — Versão 1.0</p>
        </div>

        {/* Termo */}
        <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-6 mb-6">
          <div className="max-h-[400px] overflow-y-auto pr-2 scrollbar-thin">
            <div className="bg-slate-950/60 rounded-xl p-6 border border-slate-800/60">
              {termText.split("\n").map((line, i) => {
                if (line.startsWith("TERMO DE")) return <h2 key={i} className="text-sm font-black text-white uppercase tracking-widest mb-4">{line}</h2>;
                if (line.startsWith("Versão")) return <p key={i} className="text-[10px] text-slate-500 mb-6">{line}</p>;
                if (line.match(/^\d+\.\s/)) return <h3 key={i} className="text-xs font-black text-blue-400 uppercase tracking-widest mt-4 mb-2">{line}</h3>;
                if (line.startsWith("a)") || line.startsWith("b)") || line.startsWith("c)") || line.startsWith("d)") || line.startsWith("e)") || line.startsWith("f)"))
                  return <p key={i} className="text-slate-400 text-xs leading-relaxed pl-4 mb-1">{line}</p>;
                if (line.trim() === "") return <div key={i} className="h-2" />;
                return <p key={i} className="text-slate-400 text-xs leading-relaxed mb-2">{line}</p>;
              })}
            </div>
          </div>
        </div>

        {/* Formulário */}
        <div className="bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-2xl p-6">
          <h2 className="text-xs font-black text-white uppercase tracking-widest mb-6">Dados de Confirmação</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div>
              <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1 block">Nome Completo *</label>
              <input type="text" value={fullName} onChange={e => setFullName(e.target.value)}
                className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/40" />
            </div>
            <div>
              <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1 block">E-mail *</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-blue-500/40" />
            </div>
            <div>
              <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1 block">CPF / Documento de Identidade *</label>
              <input
                type="password"
                value={cpf}
                onChange={e => {
                  const formatted = formatCpf(e.target.value);
                  setCpf(formatted);
                  if (cpfError) setCpfError("");
                }}
                onBlur={() => {
                  if (cpf && !validateCpf(cpf)) setCpfError("CPF inválido. Verifique os números digitados.");
                  else setCpfError("");
                }}
                placeholder="•••.•••.•••-••"
                autoComplete="off"
                className={`w-full bg-slate-950/50 border ${cpfError ? "border-rose-500/60 focus:ring-rose-500/40" : "border-slate-800 focus:ring-blue-500/40"} text-white rounded-xl px-4 py-3 text-sm outline-none focus:ring-2 transition-all`}
              />
              {cpfError && <p className="text-rose-400 text-[10px] font-bold mt-1">{cpfError}</p>}
            </div>
          </div>

          {/* Checkboxes */}
          <div className="space-y-3 mb-6">
            <label className="flex items-start gap-3 cursor-pointer group">
              <div className="mt-0.5">
                <input type="checkbox" checked={readConfirm} onChange={e => setReadConfirm(e.target.checked)}
                  className="w-4 h-4 rounded border-slate-700 bg-slate-950 text-blue-500 focus:ring-blue-500/40" />
              </div>
              <span className="text-slate-400 text-xs leading-relaxed group-hover:text-slate-300 transition-colors">
                <span className="text-white font-bold">Confirmo que li</span> e compreendi integralmente todos os termos e condições do Termo de Responsabilidade e Assunção de Risco acima.
              </span>
            </label>

            <label className="flex items-start gap-3 cursor-pointer group">
              <div className="mt-0.5">
                <input type="checkbox" checked={accepted} onChange={e => setAccepted(e.target.checked)}
                  className="w-4 h-4 rounded border-slate-700 bg-slate-950 text-blue-500 focus:ring-blue-500/40" />
              </div>
              <span className="text-slate-400 text-xs leading-relaxed group-hover:text-slate-300 transition-colors">
                <span className="text-white font-bold">Aceito</span> todos os riscos descritos e isento a RDE Platform, seus desenvolvedores e afiliados de qualquer responsabilidade por perdas financeiras.
              </span>
            </label>
          </div>

          {msg && (
            <div className={`p-3 rounded-xl mb-4 text-xs font-bold ${msg.includes("sucesso") ? "bg-emerald-500/10 border border-emerald-500/30 text-emerald-400" : "bg-rose-500/10 border border-rose-500/30 text-rose-400"}`}>
              {msg}
            </div>
          )}

          <button onClick={handleSubmit} disabled={loading || !readConfirm || !accepted || !fullName || !email || !cpf}
            className={`w-full py-4 rounded-xl text-xs font-black uppercase tracking-widest transition-all shadow-lg active:scale-[0.98] ${
              readConfirm && accepted && fullName && email && cpf
                ? "bg-blue-600 hover:bg-blue-500 text-white"
                : "bg-slate-800 text-slate-600 cursor-not-allowed"
            }`}>
            {loading ? "Salvando..." : "Aceitar Termo e Prosseguir"}
          </button>
        </div>
      </div>
    </div>
  );
}

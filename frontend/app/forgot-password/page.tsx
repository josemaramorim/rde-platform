"use client";

import { useState } from "react";
import Link from "next/link";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [success, setSuccess] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSuccess("");
    setError("");
    setLoading(true);

    try {
      const res = await fetch("/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      if (res.ok) {
        setSuccess(
          "Se o e-mail estiver cadastrado em nosso ecossistema, você receberá instruções de recuperação em instantes."
        );
      } else {
        const data = await res.json();
        setError(data.detail || "Erro ao processar solicitação.");
      }
    } catch {
      setError("Falha na conexão com o servidor.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center p-6 relative overflow-hidden">
      <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] bg-blue-600/10 blur-[150px] rounded-full -z-10" />
      <div className="w-full max-w-md bg-slate-900/60 border border-slate-800 rounded-[2rem] p-10 md:p-12 shadow-2xl relative backdrop-blur-md">
        <div className="text-center mb-10">
          <h1 className="text-3xl font-black text-white tracking-tighter">
            Recuperar Acesso
          </h1>
          <p className="text-slate-500 text-[10px] font-black uppercase tracking-[0.4em] mt-3 underline decoration-blue-500/50 underline-offset-4">
            Security Protocol
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {success && (
            <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 p-4 rounded-xl text-xs font-bold leading-relaxed">
              ✓ {success}
            </div>
          )}

          {error && (
            <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 p-4 rounded-xl text-xs font-bold leading-relaxed">
              ✗ {error}
            </div>
          )}

          {!success && (
            <>
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest ml-1">
                  E-mail Cadastrado
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => {
                    if (error) setError("");
                    setEmail(e.target.value);
                  }}
                  className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl px-5 py-4 focus:outline-none focus:ring-2 focus:ring-blue-500/40 transition-all text-sm font-light placeholder:text-slate-700"
                  placeholder="seu@email.com"
                  required
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 text-white font-black py-4 rounded-xl transition-all shadow-lg shadow-blue-600/10 active:scale-[0.98] uppercase text-xs tracking-[0.2em] disabled:opacity-50"
              >
                {loading ? "Processando..." : "Enviar Instruções →"}
              </button>
            </>
          )}
        </form>

        <div className="mt-10 text-center">
          <Link
            href="/login"
            className="text-xs text-slate-500 font-bold hover:text-slate-300 transition-colors uppercase tracking-widest"
          >
            ← Voltar para o Login
          </Link>
        </div>
      </div>
    </div>
  );
}

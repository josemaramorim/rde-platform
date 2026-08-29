"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter } from "next/navigation";
import { useEstado } from "@/hooks/useEstado";
import { API_URL } from "@/lib/constants";
import Link from "next/link";

function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const router = useRouter();
  const { recarregar } = useEstado();

  useEffect(() => {
    if (typeof window !== "undefined") {
      const t = sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token");
      if (t) {
        window.location.replace("/dashboard");
      }
    }
  }, []);

  const navegarParaSetup = async (token?: string) => {
    const t = token || sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token");
    if (t) {
      try {
        const res = await fetch(`${API_URL}/risk-term/status`, {
          headers: { Authorization: `Bearer ${t}` },
          signal: AbortSignal.timeout(2000),
        });
        if (res.ok) {
          const data = await res.json();
          if (!data.accepted) {
            window.location.href = "/termo-risco";
            return;
          }
        }
      } catch { /* em caso de erro, vai pro setup normalmente */ }
    }
    window.location.href = "/setup";
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const formData = new URLSearchParams();
      formData.append("username", email);
      formData.append("password", password);

      const response = await fetch(`${API_URL}/auth/jwt/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: formData.toString(),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "E-mail ou senha incorretos.");
      }

      const tokenGerado = data.access_token || data.token || data.accessToken;

      if (tokenGerado) {
        sessionStorage.setItem("rde_token", tokenGerado);
        localStorage.setItem("rde_token", tokenGerado);
        recarregar().catch(() => {});
        await navegarParaSetup(tokenGerado);
      } else {
        setError("O servidor não retornou um token válido de acesso.");
        setLoading(false);
      }
    } catch (err: any) {
      setError(err.message || "E-mail ou senha incorretos.");
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6 relative overflow-hidden">
      <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] bg-blue-500/10 blur-[150px] rounded-full -z-10"></div>
      <div className="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] bg-purple-500/5 blur-[150px] rounded-full -z-10"></div>

      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-blue-500/20 bg-blue-500/10 text-blue-400 text-[10px] font-black uppercase tracking-widest">
            🔐 Portal de Acesso RDE
          </span>
        </div>

        <div className="bg-slate-900/60 border border-slate-800/80 rounded-[2.5rem] p-10 backdrop-blur-md shadow-2xl">
          <div className="text-center mb-8">
            <h1 className="text-4xl font-black text-white tracking-tighter bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
              RDE
            </h1>
            <p className="text-slate-500 text-[10px] font-black uppercase tracking-[0.4em] mt-2">
              Painel Operacional
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 p-4 rounded-xl text-xs font-bold leading-relaxed">
                ⚠️ {error}
              </div>
            )}

            <div className="space-y-2">
              <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest ml-1">
                E-mail
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="seuemail@dominio.com"
                required
                autoComplete="email"
                className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl px-5 py-4 focus:outline-none focus:ring-2 focus:ring-blue-500/40 transition-all text-sm font-light placeholder:text-slate-700"
              />
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center px-1">
                <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">
                  Senha
                </label>
                <Link
                  href="/forgot-password"
                  className="text-blue-400 text-[10px] font-bold hover:underline transition-all"
                >
                  Esqueceu a senha?
                </Link>
              </div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                autoComplete="current-password"
                className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl px-5 py-4 focus:outline-none focus:ring-2 focus:ring-blue-500/40 transition-all text-sm font-light placeholder:text-slate-700"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full text-white font-black py-4 rounded-xl transition-all uppercase text-xs tracking-widest shadow-lg active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-500 shadow-blue-600/10"
            >
              {loading ? "Autenticando..." : "Entrar na Plataforma →"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );

}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">Carregando...</div>}>
      <LoginForm />
    </Suspense>
  );
}


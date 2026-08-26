"use client";

import { useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [feedback, setFeedback] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);

    if (password.length < 8) {
      setFeedback({ type: "err", text: "A senha deve ter pelo menos 8 caracteres." });
      return;
    }

    if (password !== confirm) {
      setFeedback({ type: "err", text: "As senhas não coincidem." });
      return;
    }

    setLoading(true);

    try {
      const res = await fetch("/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });

      if (res.ok) {
        setFeedback({
          type: "ok",
          text: "Senha redefinida com sucesso! Redirecionando...",
        });
        setTimeout(() => router.push("/login"), 2000);
      } else {
        setFeedback({
          type: "err",
          text: "Token inválido ou expirado. Solicite um novo link.",
        });
      }
    } catch {
      setFeedback({ type: "err", text: "Erro de conexão com o servidor." });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-[2.5rem] p-10 shadow-2xl">
      <div className="text-center mb-8">
        <h1 className="text-4xl font-black text-white tracking-tighter">RDE</h1>
        <p className="text-slate-500 text-[10px] font-black uppercase tracking-widest mt-2">
          Redefinir Senha
        </p>
      </div>

      {token ? (
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">
              Nova Senha
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Mínimo 8 caracteres"
              className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-2xl px-5 py-4 outline-none focus:ring-2 focus:ring-blue-500/40 text-sm font-medium placeholder:text-slate-600"
              required
            />
          </div>

          <div className="space-y-2">
            <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest">
              Confirmar Senha
            </label>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Repita a nova senha"
              className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-2xl px-5 py-4 outline-none focus:ring-2 focus:ring-blue-500/40 text-sm font-medium placeholder:text-slate-600"
              required
            />
          </div>

          {feedback && (
            <div
              className={`p-3 rounded-xl text-xs font-bold border transition-all ${
                feedback.type === "ok"
                  ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                  : "bg-rose-500/10 border-rose-500/20 text-rose-400"
              }`}
            >
              {feedback.text}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800/80 disabled:text-slate-500 text-white font-black py-4 rounded-2xl transition-all shadow-xl active:scale-[0.98] uppercase text-xs tracking-widest"
          >
            {loading ? "Redefinindo..." : "Redefinir Senha →"}
          </button>
        </form>
      ) : (
        <div className="text-center py-4">
          <p className="text-rose-400 text-sm font-bold">
            Link inválido ou ausente.
          </p>
          <p className="text-slate-400 text-xs mt-1 font-light">
            Por favor, solicite um novo e-mail de recuperação.
          </p>
          <button
            onClick={() => router.push("/login")}
            className="mt-6 text-blue-400 text-xs font-bold hover:underline transition-all"
          >
            Voltar ao login
          </button>
        </div>
      )}
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center p-6 overflow-x-hidden">
      <Suspense
        fallback={
          <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center">
            <p className="text-slate-500 text-xs font-black uppercase tracking-widest animate-pulse">
              Carregando...
            </p>
          </div>
        }
      >
        <ResetPasswordForm />
      </Suspense>
    </div>
  );
}

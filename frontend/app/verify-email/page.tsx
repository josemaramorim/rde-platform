"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token");

  const [message, setMessage] = useState("Processando sua validação...");

  useEffect(() => {
    if (!token) {
      setMessage("Token de validação inválido ou ausente.");
      return;
    }

    fetch("/auth/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    })
      .then((res) => {
        if (res.ok) {
          setMessage("Email validado com sucesso! Redirecionando...");
          setTimeout(() => router.push("/login"), 3000);
        } else {
          setMessage("O token expirou ou já foi utilizado.");
        }
      })
      .catch(() => {
        setMessage("Erro ao conectar com o servidor.");
      });
  }, [token, router]);

  return (
    <div className="bg-slate-900 border border-slate-800 p-8 rounded-2xl text-center max-w-md">
      <h1 className="text-2xl font-black mb-4">Verificação de Conta</h1>
      <p className="text-slate-400 font-light">{message}</p>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 text-white">
      <Suspense
        fallback={
          <div className="min-h-screen flex items-center justify-center bg-slate-950 text-white">
            <p className="text-slate-400">Carregando...</p>
          </div>
        }
      >
        <VerifyEmailContent />
      </Suspense>
    </div>
  );
}

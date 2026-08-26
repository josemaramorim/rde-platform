"use client";

import { useState, useEffect, useRef } from "react";
import { useEstado } from "@/hooks/useEstado";
import { toast } from "@/components/Toast";

export default function ProfilePage() {
  const { estado, salvar } = useEstado();
  
  const [user, setUser] = useState({ username: "", email: "", plan_name: "basic" });
  const [avatar, setAvatar] = useState<string | null>(null);
  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [latencyProtection, setLatencyProtection] = useState(false);
  const [telegramConnected, setTelegramConnected] = useState(false);
  const [botConfigured, setBotConfigured] = useState(false);
  const [copierRunning, setCopierRunning] = useState(false);
  const [togglingCopier, setTogglingCopier] = useState(false);

  // Troca de senha
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwdMsg, setPwdMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [pwdLoading, setPwdLoading] = useState(false);

  // Esqueci senha
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotMsg, setForgotMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [forgotLoading, setForgotLoading] = useState(false);
  const [showForgot, setShowForgot] = useState(false);

  const fileRef = useRef<HTMLInputElement>(null);
  const getToken = () => typeof window !== "undefined" ? (sessionStorage.getItem("rde_token") || localStorage.getItem("rde_token")) : null;

  useEffect(() => {
    // Evita ler propriedades de 'estado' se ele for nulo ou indefinido
    if (estado) {
      setUser({
        username: (estado as any).username || "",
        email: (estado as any).email || "",
        plan_name: (estado as any).plan_name || "basic"
      });
      setTelegramEnabled((estado as any).telegram_enabled || false);
      setLatencyProtection((estado as any).latency_protection || false);
    }
    
    const savedAvatar = localStorage.getItem("rde_avatar");
    if (savedAvatar) setAvatar(savedAvatar);

    const token = getToken();
    fetch(`/telegram/status`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d) {
          setTelegramConnected(d.connected ?? false);
          setBotConfigured(d.bot_configured ?? false);
          setCopierRunning(d.copier_running ?? false);
        }
      })
      .catch(() => {});
  }, [estado?.username, estado?.email, estado?.plan_name, estado?.telegram_enabled, estado?.latency_protection]);

  // Upload de foto — salva em base64 no localStorage
  const handlePhotoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { 
      toast.error("Foto muito grande. Máximo 2MB.", "Perfil"); 
      return; 
    }
    const reader = new FileReader();
    reader.onload = () => {
      const base64 = reader.result as string;
      setAvatar(base64);
      localStorage.setItem("rde_avatar", base64);
    };
    reader.readAsDataURL(file);
  };

  // Trocar senha
  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwdMsg(null);
    if (newPassword.length < 8) { 
      setPwdMsg({ type: "err", text: "Senha deve ter pelo menos 8 caracteres." }); 
      return; 
    }
    if (newPassword !== confirmPassword) { 
      setPwdMsg({ type: "err", text: "As senhas não coincidem." }); 
      return; 
    }
    
    setPwdLoading(true);
    const token = getToken();
    try {
      const res = await fetch(`/users/me`, {
        method: "PATCH",
        headers: { 
          "Content-Type": "application/json", 
          Authorization: `Bearer ${token}` 
        },
        body: JSON.stringify({ password: newPassword }),
      });
      
      if (res.ok) {
        setPwdMsg({ type: "ok", text: "Senha alterada com sucesso!" });
        setNewPassword("");
        setConfirmPassword("");
      } else {
        setPwdMsg({ type: "err", text: "Erro ao alterar senha. Tente novamente." });
      }
    } catch {
      setPwdMsg({ type: "err", text: "Erro de conexão." });
    } finally { // <-- Corrigido spelling aqui
      setPwdLoading(false);
    }
  };

  // Esqueci senha
  const handleForgotPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setForgotMsg(null);
    setForgotLoading(true);
    try {
      const res = await fetch(`/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: forgotEmail }),
      });
      if (res.ok) {
        setForgotMsg({ type: "ok", text: `E-mail de recuperação enviado para ${forgotEmail}. Verifique sua caixa de entrada.` });
        setForgotEmail("");
      } else {
        setForgotMsg({ type: "err", text: "Erro ao enviar e-mail. Verifique o endereço." });
      }
    } catch {
      setForgotMsg({ type: "err", text: "Erro de conexão." });
    } finally { // <-- Corrigido spelling aqui
      setForgotLoading(false);
    }
  };

  const updatePref = async (field: string, value: boolean) => {
    if (field === "telegram_enabled") {
      setTelegramEnabled(value);
      setTogglingCopier(true);
      try {
        const token = getToken();
        const res = await fetch(`/copier/toggle`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ active: value }),
        });
        if (res.ok) {
          const data = await res.json();
          setCopierRunning(data.active ?? value);
        }
      } catch {
        setTelegramEnabled(!value);
      } finally {
        setTogglingCopier(false);
      }
    }
    if (field === "latency_protection") {
      setLatencyProtection(value);
    }
    await salvar({ [field]: value });
  };

  const planColors: Record<string, string> = {
    basic: "text-blue-400",
    pro: "text-emerald-400",
    vip: "text-purple-400",
  };

  const handleLogout = () => {
    localStorage.clear();
    window.location.href = "/login";
  };

  return (
    <div className="min-h-screen p-6 md:p-10 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 overflow-x-hidden">
      <header className="mb-10">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <h1 className="text-3xl font-black text-white tracking-tight">Perfil</h1>
            <p className="text-slate-500 mt-2 text-sm font-light">Gerencie sua conta e preferências operacionais.</p>
          </div>
          <div className="flex gap-2">
            {estado?.broker_ativo && estado.broker_ativo !== "-" && (
              <div className={`px-4 py-2 rounded-xl text-xs font-black uppercase tracking-widest ${
                estado?.broker_connected
                  ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-400"
                  : "bg-slate-800/50 border border-slate-700 text-slate-400"
              }`}>
                {estado?.broker_connected ? "🟢" : "🔴"} {estado.broker_ativo} ({estado?.broker_mode || "-"})
              </div>
            )}
            <div className={`px-4 py-2 rounded-xl text-xs font-black uppercase tracking-widest ${
              botConfigured && telegramConnected
                ? "bg-blue-500/10 border border-blue-500/20 text-blue-400"
                : botConfigured
                ? "bg-rose-500/10 border border-rose-500/20 text-rose-400"
                : "bg-slate-800/50 border border-slate-700 text-slate-500"
            }`}>
              {botConfigured && telegramConnected ? "🟢" : botConfigured ? "🔴" : "⚪"} Telegram
            </div>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Coluna Esquerda: Informações do Usuário */}
        <div className="space-y-6">
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 text-center backdrop-blur-md">
            {/* Avatar container */}
            <div className="relative w-24 h-24 mx-auto mb-4">
              {avatar ? (
                <img src={avatar} alt="avatar" className="w-24 h-24 rounded-2xl object-cover border-2 border-slate-800" />
              ) : (
                <div className="w-24 h-24 bg-gradient-to-br from-blue-600 to-blue-400 rounded-2xl flex items-center justify-center text-3xl font-black text-white">
                  {user.username?.charAt(0)?.toUpperCase() || "U"}
                </div>
              )}
              <button
                onClick={() => fileRef.current?.click()}
                className="absolute -bottom-2 -right-2 w-8 h-8 bg-blue-600 hover:bg-blue-500 rounded-xl flex items-center justify-center text-white text-xs transition-all shadow-lg"
                title="Trocar foto"
              >
                📷
              </button>
              <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handlePhotoChange} />
            </div>

            <h2 className="text-xl font-black text-white">{user.username || "Usuário"}</h2>
            <p className={`text-[10px] font-black uppercase tracking-widest mt-1 ${planColors[user.plan_name?.toLowerCase() || "basic"]}`}>
              Plano {user.plan_name?.toUpperCase() || "BASIC"}
            </p>
            <p className="text-slate-500 text-xs mt-2 truncate max-w-[200px] mx-auto">{user.email || "sem-email@provedor.com"}</p>

            <button
              onClick={() => fileRef.current?.click()}
              className="w-full mt-5 py-2.5 bg-slate-800 hover:bg-slate-750 border border-slate-700/50 text-white text-xs font-black uppercase tracking-widest rounded-xl transition-all"
            >
              Trocar Foto
            </button>
          </div>

          {/* Card de Preferências */}
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 space-y-5 backdrop-blur-md">
            <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Preferências</p>

            {[
              { label: "Copier Telegram", sub: copierRunning ? "Executando sinais no broker" : "Parado — clique para ativar", key: "telegram_enabled", val: telegramEnabled },
              { label: "Proteção de Latência", sub: "Bloqueia se ping > 400ms", key: "latency_protection", val: latencyProtection },
            ].map(item => (
              <div key={item.key} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {item.key === "telegram_enabled" && (
                    <span className={`w-2 h-2 rounded-full ${copierRunning ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'}`}></span>
                  )}
                  <div>
                    <p className="text-white text-sm font-bold">{item.label}</p>
                    <p className="text-[10px] text-slate-500">{item.sub}</p>
                  </div>
                </div>
                <div
                  onClick={() => { if (!togglingCopier) updatePref(item.key, !item.val); }}
                  className={`w-11 h-6 rounded-full border flex items-center px-1 transition-all cursor-pointer ${
                    togglingCopier && item.key === "telegram_enabled"
                      ? "opacity-50"
                      : item.val
                      ? "bg-blue-600/20 border-blue-500/30"
                      : "bg-slate-950 border-slate-800"
                  }`}
                >
                  <div className={`w-4 h-4 rounded-full transition-all duration-300 ${item.val ? "bg-blue-500 translate-x-5" : "bg-slate-700 translate-x-0"}`}></div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Coluna Direita: Formulários de Segurança */}
        <div className="lg:col-span-2 space-y-6">

          {/* Formulário Trocar Senha */}
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-8 backdrop-blur-md">
            <h2 className="text-sm font-black text-white uppercase tracking-widest mb-6 flex items-center gap-2">
              🔐 Segurança & Acesso
            </h2>
            <form onSubmit={handleChangePassword} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest ml-1">Nova Senha</label>
                  <input
                    type="password"
                    value={newPassword}
                    onChange={e => setNewPassword(e.target.value)}
                    placeholder="Mínimo 8 caracteres"
                    className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl p-4 text-sm outline-none focus:ring-2 focus:ring-blue-500/40 transition-all placeholder:text-slate-700"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest ml-1">Confirmar Senha</label>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    placeholder="Repita a nova senha"
                    className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl p-4 text-sm outline-none focus:ring-2 focus:ring-blue-500/40 transition-all placeholder:text-slate-700"
                    required
                  />
                </div>
              </div>

              {pwdMsg && (
                <div className={`p-4 rounded-xl text-xs font-bold border ${pwdMsg.type === "ok" ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" : "bg-rose-500/10 border-rose-500/20 text-rose-400"}`}>
                  {pwdMsg.text}
                </div>
              )}

              <div className="flex items-center gap-5 pt-2">
                <button 
                  type="submit" 
                  disabled={pwdLoading}
                  className="px-6 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 text-white font-black rounded-xl text-xs uppercase tracking-widest transition-all shadow-md active:scale-95"
                >
                  {pwdLoading ? "Salvando..." : "Alterar Senha"}
                </button>
                <button 
                  type="button" 
                  onClick={() => setShowForgot(!showForgot)}
                  className="text-xs text-blue-400 hover:text-blue-300 font-bold transition-colors"
                >
                  Esqueci minha senha →
                </button>
              </div>
            </form>
          </div>

          {/* Recuperação Externa Dinâmica */}
          {showForgot && (
            <div className="bg-blue-600/5 border border-blue-500/10 rounded-2xl p-8 backdrop-blur-md">
              <h2 className="text-sm font-black text-white uppercase tracking-widest mb-2 flex items-center gap-2">
                📧 Recuperar via E-mail
              </h2>
              <p className="text-slate-400 text-xs mb-6 font-light">Um link de redefinição externa será enviado para o endereço informado abaixo.</p>
              
              <form onSubmit={handleForgotPassword} className="space-y-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest ml-1">E-mail de Cadastro</label>
                  <input
                    type="email"
                    value={forgotEmail}
                    onChange={e => setForgotEmail(e.target.value)}
                    placeholder="seu@email.com"
                    className="w-full bg-slate-950/50 border border-slate-800 text-white rounded-xl p-4 text-sm outline-none focus:ring-2 focus:ring-blue-500/40 transition-all placeholder:text-slate-700"
                    required
                  />
                </div>

                {forgotMsg && (
                  <div className={`p-4 rounded-xl text-xs font-bold border ${forgotMsg.type === "ok" ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" : "bg-rose-500/10 border-rose-500/20 text-rose-400"}`}>
                    {forgotMsg.text}
                  </div>
                )}

                <button 
                  type="submit" 
                  disabled={forgotLoading}
                  className="px-6 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 text-white font-black rounded-xl text-xs uppercase tracking-widest transition-all shadow-md active:scale-95"
                >
                  {forgotLoading ? "Enviando..." : "Enviar Link de Recuperação"}
                </button>
              </form>
            </div>
          )}

          {/* Zona de Perigo */}
          <div className="bg-rose-500/5 border border-rose-500/10 rounded-2xl p-6 backdrop-blur-md">
            <p className="text-rose-400 text-[10px] font-black uppercase tracking-widest mb-4 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse"></span>
              Zona de Perigo
            </p>
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <p className="text-white font-bold text-sm">Encerrar Sessão</p>
                <p className="text-slate-500 text-xs mt-0.5">Sair com segurança do painel operacional limpando cookies locais.</p>
              </div>
              <button
                onClick={handleLogout}
                className="px-6 py-2.5 border border-rose-500/20 text-rose-400 hover:bg-rose-500/10 rounded-xl text-xs font-black uppercase tracking-widest transition-all"
              >
                Sair
              </button>
            </div>
          </div>
          
        </div>
      </div>
    </div>
  );
}
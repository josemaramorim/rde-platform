"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { API_URL } from "@/lib/constants";

interface LogTerminalModalProps {
  isOpen: boolean;
  onClose: () => void;
  token?: string | null;
  isAdmin?: boolean;
}

export default function LogTerminalModal({ isOpen, onClose, token, isAdmin = false }: LogTerminalModalProps) {
  const [logs, setLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [lineCount, setLineCount] = useState<number>(200);
  const [refreshInterval, setRefreshInterval] = useState<number>(3); // Em segundos, 0 = Pausado
  const [autoScroll, setAutoScroll] = useState<boolean>(true);
  const [copied, setCopied] = useState<boolean>(false);
  const [logSizeKb, setLogSizeKb] = useState<number>(0);
  const [totalLines, setTotalLines] = useState<number>(0);

  const terminalEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Carregar preferência de intervalo salva
  useEffect(() => {
    try {
      const saved = localStorage.getItem("rde_log_refresh_sec");
      if (saved !== null) {
        setRefreshInterval(Number(saved));
      }
    } catch {}
  }, []);

  const handleIntervalChange = (sec: number) => {
    setRefreshInterval(sec);
    try {
      localStorage.setItem("rde_log_refresh_sec", String(sec));
    } catch {}
  };

  const fetchLogs = useCallback(async (isManual = false) => {
    if (!token) return;
    if (isManual) setLoading(true);
    try {
      const endpoint = isAdmin
        ? `${API_URL}/admin/logs/copier?lines=${lineCount}${searchQuery ? `&filter=${encodeURIComponent(searchQuery)}` : ""}`
        : `${API_URL}/copier/logs?lines=${lineCount}${searchQuery ? `&filter=${encodeURIComponent(searchQuery)}` : ""}`;

      const res = await fetch(endpoint, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) {
        throw new Error(`Erro HTTP ${res.status}`);
      }

      const data = await res.json();
      if (data.status === "ok" && Array.isArray(data.lines)) {
        setLogs(data.lines);
        setLogSizeKb(data.size_kb || 0);
        setTotalLines(data.total_lines || data.lines.length);
        setError(null);
      } else {
        setError(data.message || "Falha ao carregar logs.");
      }
    } catch (err: any) {
      setError(err.message || "Erro de conexão ao buscar logs.");
    } finally {
      setLoading(false);
    }
  }, [token, isAdmin, lineCount, searchQuery]);

  // Carregamento inicial e loop parametrizável
  useEffect(() => {
    if (!isOpen) return;
    fetchLogs(true);

    if (refreshInterval > 0) {
      const timer = setInterval(() => {
        fetchLogs(false);
      }, refreshInterval * 1000);
      return () => clearInterval(timer);
    }
  }, [isOpen, refreshInterval, fetchLogs]);

  // Auto-scroll para o final quando novos logs chegarem
  useEffect(() => {
    if (autoScroll && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const handleCopyLogs = () => {
    if (!logs.length) return;
    navigator.clipboard.writeText(logs.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadLogs = () => {
    if (!logs.length) return;
    const blob = new Blob([logs.join("\n")], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `copier_${new Date().toISOString().slice(0, 10)}.log`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleClearServerLogs = async () => {
    if (!isAdmin || !token) return;
    if (!confirm("Tem certeza que deseja limpar o arquivo de log no servidor?")) return;
    try {
      await fetch(`${API_URL}/admin/logs/copier`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      fetchLogs(true);
    } catch {}
  };

  const formatLogLine = (line: string) => {
    if (line.includes("ERROR") || line.includes("❌") || line.includes("Falha")) {
      return "text-rose-400 font-semibold";
    }
    if (line.includes("WARNING") || line.includes("⚠️") || line.includes("Timeout")) {
      return "text-amber-400";
    }
    if (line.includes("[CHECK]") || line.includes("Conectado") || line.includes("sucesso") || line.includes("WIN")) {
      return "text-emerald-400 font-semibold";
    }
    if (line.includes("[TELEGRAM]") || line.includes("[CONFIG]") || line.includes("[GER]") || line.includes("[PARSE]")) {
      return "text-cyan-400 font-medium";
    }
    return "text-slate-300";
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 md:p-6 bg-black/85 backdrop-blur-md animate-fadeIn">
      <div className="flex flex-col w-full max-w-6xl h-[90vh] bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden font-mono">
        
        {/* Cabeçalho do Terminal */}
        <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-slate-900 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-full bg-rose-500/80 inline-block"></span>
              <span className="w-3 h-3 rounded-full bg-amber-500/80 inline-block"></span>
              <span className="w-3 h-3 rounded-full bg-emerald-500/80 inline-block"></span>
            </div>
            <div>
              <h2 className="text-xs md:text-sm font-black text-white tracking-widest uppercase flex items-center gap-2">
                🖥️ Terminal de Logs ao Vivo <span className="text-[10px] text-cyan-400 bg-cyan-950/80 border border-cyan-800/50 px-2 py-0.5 rounded-full font-mono">copier.log</span>
              </h2>
              <p className="text-[10px] text-slate-400 mt-0.5">
                Total: {totalLines} linhas ({logSizeKb} KB) | Exibindo {logs.length}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => fetchLogs(true)}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold rounded-lg transition-all flex items-center gap-1"
              title="Atualizar Agora"
            >
              🔄 Atualizar
            </button>
            <button
              onClick={handleCopyLogs}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all flex items-center gap-1 ${
                copied ? "bg-emerald-600 text-white" : "bg-slate-800 hover:bg-slate-700 text-slate-300"
              }`}
            >
              {copied ? "✓ Copiado!" : "📋 Copiar"}
            </button>
            <button
              onClick={handleDownloadLogs}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold rounded-lg transition-all flex items-center gap-1"
              title="Baixar Arquivo .log"
            >
              ⬇️ Baixar
            </button>
            {isAdmin && (
              <button
                onClick={handleClearServerLogs}
                className="px-3 py-1.5 bg-rose-950 hover:bg-rose-900 text-rose-300 text-xs font-bold rounded-lg transition-all border border-rose-800/40"
                title="Limpar log no servidor"
              >
                🧹 Limpar
              </button>
            )}
            <button
              onClick={onClose}
              className="px-3 py-1.5 bg-slate-800 hover:bg-rose-600 text-slate-400 hover:text-white text-xs font-bold rounded-lg transition-all ml-2"
            >
              ✕ Fechar
            </button>
          </div>
        </div>

        {/* Barra de Controles e Parametrização */}
        <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-slate-900/60 border-b border-slate-800/80 text-xs">
          
          {/* Seletor de Intervalo Parametrizável */}
          <div className="flex items-center gap-2">
            <span className="text-slate-400 font-bold text-[11px] uppercase tracking-wider">⏱️ Auto-Refresh:</span>
            <div className="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800 gap-1">
              {[
                { label: "1s", val: 1 },
                { label: "2s", val: 2 },
                { label: "3s (Padrão)", val: 3 },
                { label: "5s", val: 5 },
                { label: "10s", val: 10 },
                { label: "⏸️ Pausar", val: 0 },
              ].map((opt) => (
                <button
                  key={opt.val}
                  onClick={() => handleIntervalChange(opt.val)}
                  className={`px-2 py-1 rounded text-[10px] font-black uppercase transition-all ${
                    refreshInterval === opt.val
                      ? "bg-cyan-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-white hover:bg-slate-800"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Seletor de Quantidade de Linhas e Filtro */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500 font-bold text-[11px]">Linhas:</span>
              <select
                value={lineCount}
                onChange={(e) => setLineCount(Number(e.target.value))}
                className="bg-slate-950 border border-slate-800 text-white rounded-lg px-2 py-1 text-xs outline-none focus:border-cyan-500"
              >
                <option value={100}>100</option>
                <option value={200}>200</option>
                <option value={500}>500</option>
                <option value={1000}>1000</option>
              </select>
            </div>

            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="🔍 Filtrar log..."
                className="bg-slate-950 border border-slate-800 text-white rounded-lg px-3 py-1 text-xs outline-none focus:border-cyan-500 w-44 md:w-56"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white text-xs"
                >
                  ✕
                </button>
              )}
            </div>

            <label className="flex items-center gap-1.5 text-[11px] text-slate-400 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(e) => setAutoScroll(e.target.checked)}
                className="accent-cyan-500 rounded"
              />
              Auto-Scroll
            </label>
          </div>
        </div>

        {/* Corpo do Terminal (Linhas do Log) */}
        <div
          ref={scrollContainerRef}
          className="flex-1 p-4 overflow-y-auto bg-[#020617] text-[11px] leading-relaxed select-text space-y-0.5"
        >
          {loading && logs.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-500 gap-2">
              <span className="animate-spin text-cyan-400">⏳</span> Carregando fluxo de logs...
            </div>
          ) : error ? (
            <div className="p-4 bg-rose-950/40 border border-rose-800/50 rounded-xl text-rose-400 text-xs">
              ⚠️ {error}
            </div>
          ) : logs.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-600">
              Nenhuma linha encontrada para o filtro atual.
            </div>
          ) : (
            logs.map((line, idx) => (
              <div key={idx} className="flex items-start gap-3 hover:bg-slate-900/40 px-1 py-0.5 rounded transition-colors font-mono">
                <span className="text-slate-600 text-[10px] select-none w-10 text-right shrink-0">{idx + 1}</span>
                <span className={`break-all whitespace-pre-wrap ${formatLogLine(line)}`}>
                  {line}
                </span>
              </div>
            ))
          )}
          <div ref={terminalEndRef} />
        </div>

        {/* Rodapé de Status */}
        <div className="flex items-center justify-between px-4 py-2 bg-slate-900/90 border-t border-slate-800 text-[10px] text-slate-400">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${refreshInterval > 0 ? "bg-emerald-400 animate-pulse" : "bg-amber-400"}`}></span>
            <span>
              {refreshInterval > 0
                ? `Live Feed Ativo (atualizando a cada ${refreshInterval}s)`
                : "Live Feed Pausado (modo manual)"}
            </span>
          </div>
          <span className="text-slate-500">Pressione ESC para fechar</span>
        </div>

      </div>
    </div>
  );
}

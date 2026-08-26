"use client";

import React, { useState, useEffect } from "react";

export type ToastType = "success" | "error" | "info" | "warning";

export interface ToastMessage {
  id: string;
  type: ToastType;
  title?: string;
  message: string;
  duration?: number;
}

export function showToast(message: string, type: ToastType = "error", title?: string, duration: number = 4000) {
  if (typeof window !== "undefined") {
    const event = new CustomEvent("rde-toast", {
      detail: {
        id: Math.random().toString(36).substring(2, 9),
        message,
        type,
        title,
        duration,
      },
    });
    window.dispatchEvent(event);
  }
}

export const toast = {
  success: (msg: string, title?: string) => showToast(msg, "success", title),
  error: (msg: string, title?: string) => showToast(msg, "error", title),
  info: (msg: string, title?: string) => showToast(msg, "info", title),
  warning: (msg: string, title?: string) => showToast(msg, "warning", title),
};

export default function ToastContainer() {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  useEffect(() => {
    // Interceptar alert padrão do navegador para substituir por toasts elegantes
    const originalAlert = window.alert;
    window.alert = (msg: any) => {
      showToast(String(msg), "error", "Aviso do Sistema");
    };

    const handleToastEvent = (e: Event) => {
      const customEvent = e as CustomEvent<ToastMessage>;
      if (!customEvent.detail) return;

      const newToast = customEvent.detail;
      setToasts((prev) => [...prev, newToast]);

      const timer = setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== newToast.id));
      }, newToast.duration || 4000);

      return () => clearTimeout(timer);
    };

    window.addEventListener("rde-toast", handleToastEvent);

    return () => {
      window.alert = originalAlert;
      window.removeEventListener("rde-toast", handleToastEvent);
    };
  }, []);

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-5 right-5 z-[9999] flex flex-col gap-3 max-w-md w-full px-4 pointer-events-none">
      {toasts.map((t) => {
        let badgeColor = "bg-rose-500/10 border-rose-500/30 text-rose-400";
        let icon = "❌";
        let defaultTitle = "Erro";

        if (t.type === "success") {
          badgeColor = "bg-emerald-500/10 border-emerald-500/30 text-emerald-400";
          icon = "✨";
          defaultTitle = "Sucesso";
        } else if (t.type === "warning") {
          badgeColor = "bg-amber-500/10 border-amber-500/30 text-amber-400";
          icon = "⚠️";
          defaultTitle = "Atenção";
        } else if (t.type === "info") {
          badgeColor = "bg-blue-500/10 border-blue-500/30 text-blue-400";
          icon = "ℹ️";
          defaultTitle = "Informação";
        }

        return (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-start gap-3 p-4 rounded-2xl border backdrop-blur-xl bg-slate-900/95 shadow-2xl transition-all duration-300 animate-in fade-in slide-in-from-top-4 ${badgeColor}`}
          >
            <span className="text-lg leading-none mt-0.5">{icon}</span>
            <div className="flex-1 min-w-0">
              <h4 className="text-xs font-black uppercase tracking-wider mb-1">
                {t.title || defaultTitle}
              </h4>
              <p className="text-xs font-medium text-slate-200 leading-relaxed break-words">
                {t.message}
              </p>
            </div>
            <button
              onClick={() => removeToast(t.id)}
              className="text-slate-400 hover:text-white text-xs font-bold p-1 rounded-lg hover:bg-white/10 transition-colors"
            >
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
}

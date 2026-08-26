"use client";

import { useEffect, useState } from "react";
import { APP_VERSION } from "@/lib/constants";

interface UpdateInfo {
  has_update: boolean;
  current_version: string;
  latest_version: string;
  download_url: string;
  release_notes: string;
}

export default function VersionCheck() {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch("/api/check-update", { signal: AbortSignal.timeout(10000) });
        if (res.ok) {
          const data: UpdateInfo = await res.json();
          data.current_version = APP_VERSION;
          setInfo(data);
        }
      } catch {
        // ignore
      }
    };
    check();
    const interval = setInterval(check, 300_000); // every 5 min
    return () => clearInterval(interval);
  }, []);

  if (!info?.has_update || dismissed) return null;

  return (
    <div className="fixed top-4 right-4 z-50 max-w-sm bg-amber-900/90 border border-amber-600 text-amber-100 rounded-lg shadow-xl p-4 backdrop-blur">
      <div className="flex items-start gap-3">
        <div className="flex-1">
          <p className="text-sm font-semibold flex items-center gap-2">
            <span>Nova versão disponível</span>
            <span className="px-1.5 py-0.5 text-xs bg-amber-600 rounded font-mono">
              v{info.latest_version}
            </span>
          </p>
          <p className="text-xs mt-1 text-amber-200/80">
            Sua versão: v{info.current_version}
          </p>
          {info.release_notes && (
            <p className="text-xs mt-1 text-amber-200/60">{info.release_notes}</p>
          )}
          {info.download_url && (
            <a
              href={info.download_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block mt-2 text-xs font-medium text-amber-100 underline underline-offset-2 hover:text-white"
            >
              Baixar atualização
            </a>
          )}
        </div>
        <button
          onClick={() => setDismissed(true)}
          className="text-amber-300 hover:text-white shrink-0"
          aria-label="Fechar"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

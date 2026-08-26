/**
 * Centralized configuration constants for the RDE Frontend
 * ✅ Single source of truth for API URLs and other configuration
 */

// API Configuration
// If NEXT_PUBLIC_API_URL is empty (standalone client), use relative URLs.
// Otherwise falls back to localhost:8000 for development.
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL != null && process.env.NEXT_PUBLIC_API_URL !== ""
    ? process.env.NEXT_PUBLIC_API_URL
    : "";

export const ADMIN_FRONTEND_URL =
  process.env.NEXT_PUBLIC_ADMIN_URL != null && process.env.NEXT_PUBLIC_ADMIN_URL !== ""
    ? process.env.NEXT_PUBLIC_ADMIN_URL
    : "http://localhost:8000";

export const FRONTEND_URL =
  process.env.NEXT_PUBLIC_FRONTEND_URL != null && process.env.NEXT_PUBLIC_FRONTEND_URL !== ""
    ? process.env.NEXT_PUBLIC_FRONTEND_URL
    : "http://localhost:3000";

// API Endpoints (Imutável com inferência literal estrita do TypeScript)
export const API_ENDPOINTS = {
  AUTH: {
    LOGIN: `${API_URL}/auth/jwt/login`,
    LOGOUT: `${API_URL}/auth/jwt/logout`,
    REGISTER: `${API_URL}/auth/register`,
    FORGOT_PASSWORD: `${API_URL}/auth/forgot-password`,
    RESET_PASSWORD: `${API_URL}/auth/reset-password`,
  },
  USER: {
    ME: `${API_URL}/users/me`,
    UPDATE: `${API_URL}/users/me`,
    ESTADO: `${API_URL}/user/estado`,
    PREFERENCES: `${API_URL}/user/preferences`,
    SALVAR_CAPITAL: `${API_URL}/user/salvar-capital`,
  },
  ADMIN: {
    USERS: `${API_URL}/admin/users`,
    PLANS: `${API_URL}/admin/plans`,
    STATS: `${API_URL}/admin/stats`,
  },
  TRADES: {
    EXECUTE: `${API_URL}/execute-signal`,
    HISTORY: `${API_URL}/trades/history`,
  },
} as const;

// Rate Limiting
export const RATE_LIMITS = {
  DEFAULT: 100,
  AGGRESSIVE: 10,
  LENIENT: 500,
} as const;

// Timeouts (in milliseconds)
export const TIMEOUTS = {
  SHORT: 5000,
  NORMAL: 10000,
  LONG: 30000,
} as const;

// Version info
export const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION || "0.1.0";

// Feature Flags
export const FEATURES = {
  MAINTENANCE_MODE: false,
  TWO_FACTOR_AUTH: true,
  DARK_MODE_ONLY: true,
  DEBUG_MODE: process.env.NODE_ENV === "development",
} as const;

// Environment
export const ENV = process.env.NODE_ENV || "development";
export const IS_PRODUCTION = ENV === "production";
export const IS_DEVELOPMENT = ENV === "development";

// Brokers / Corretoras Suportadas
export const BROKERS = [
  { id: "iqoption", name: "IQ Option" }, // ID normalizado idêntico ao valor padrão do useEstado
  { id: "quotex", name: "Quotex" },
  { id: "pocket_option", name: "Pocket Option" },
  { id: "exnova", name: "Exnova" }
] as const;

// ============================================================
// Moeda & Conversão
// A corretora (IQ Option) opera em USD. A plataforma exibe na
// moeda escolhida pelo usuário (USD ou BRL).
// ============================================================
export type Currency = "USD" | "BRL";

// Taxa USD -> BRL (atualizar conforme o câmbio desejado).
// Mantemos fixa para não depender de API externa; ajuste aqui.
export const USD_TO_BRL_RATE = 5.6;

/**
 * Converte um valor em USD para a moeda escolhida.
 * Se a moeda for USD, retorna o próprio valor.
 */
export function convertFromUsd(valueUsd: number, currency: Currency): number {
  if (currency === "BRL") return valueUsd * USD_TO_BRL_RATE;
  return valueUsd;
}

/**
 * Formata um valor (sempre em USD na fonte) para a moeda escolhida.
 * Ex: formatMoney(2.11, "USD") -> "$2.11"
 *     formatMoney(2.11, "BRL") -> "R$ 11,82"
 */
export function formatMoney(valueUsd: number, currency: Currency): string {
  const converted = convertFromUsd(valueUsd, currency);
  if (currency === "BRL") {
    return converted.toLocaleString("pt-BR", {
      style: "currency",
      currency: "BRL",
    });
  }
  return converted.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

/**
 * Converte qualquer erro da API (string | array de objetos | objeto) em texto
 * seguro para renderizar no React. Evita o erro "Objects are not valid as a
 * React child" quando o FastAPI retorna um ValidationError (422) com detail array.
 */
export function errToText(detail: any): string {
  if (detail === null || detail === undefined) return "Erro desconhecido";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: any) => (d && typeof d === "object" && d.msg) ? d.msg : String(d))
      .join("; ");
  }
  if (typeof detail === "object") {
    if (detail.msg) return detail.msg;
    if (detail.message) return detail.message;
    try { return JSON.stringify(detail); } catch { return String(detail); }
  }
  return String(detail);
}
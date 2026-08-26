import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },

  // Agrupa as configurações de desenvolvimento e rede no bloco experimental nativo
  // allowedDevOrigins: ["192.168.0.149", "localhost:3000"],
  experimental: {},

  ...(process.env.NEXT_OUTPUT === "export" ? {} : {
    async rewrites() {
      return [
        {
          source: "/auth/:path*",
          destination: "http://127.0.0.1:8000/auth/:path*",
        },
        {
          source: "/users/:path*",
          destination: "http://127.0.0.1:8000/users/:path*",
        },
        {
          source: "/user/:path*",
          destination: "http://127.0.0.1:8000/user/:path*",
        },
        {
          source: "/dashboard/:path*",
          destination: "http://127.0.0.1:8000/dashboard/:path*",
        },
        {
          source: "/broker/:path*",
          destination: "http://127.0.0.1:8000/broker/:path*",
        },
        {
          source: "/copier/:path*",
          destination: "http://127.0.0.1:8000/copier/:path*",
        },
        {
          source: "/telegram/:path*",
          destination: "http://127.0.0.1:8000/telegram/:path*",
        },
        {
          source: "/stats/:path*",
          destination: "http://127.0.0.1:8000/stats/:path*",
        },
        {
          source: "/admin/:path*",
          destination: "http://127.0.0.1:8000/admin/:path*",
        },
        {
          source: "/signal",
          destination: "http://127.0.0.1:8000/signal",
        },
        {
          source: "/create-checkout-session",
          destination: "http://127.0.0.1:8000/create-checkout-session",
        },
        {
          source: "/account/:path*",
          destination: "http://127.0.0.1:8000/account/:path*",
        },
        {
          source: "/version",
          destination: "http://127.0.0.1:8000/version",
        },
        {
          source: "/api/:path*",
          destination: "http://127.0.0.1:8000/api/:path*",
        },
        {
          source: "/mt4/:path*",
          destination: "http://127.0.0.1:8000/mt4/:path*",
        },
        {
          source: "/tradingview/:path*",
          destination: "http://127.0.0.1:8000/tradingview/:path*",
        },
        {
          source: "/risk-term/:path*",
          destination: "http://127.0.0.1:8000/risk-term/:path*",
        },
        {
          source: "/planilha/:path*",
          destination: "http://127.0.0.1:8000/planilha/:path*",
        },
      ];
    },
  }),
};

export default nextConfig;
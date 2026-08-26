import { FlatCompat } from "@eslint/eslintrc";
import { dirname } from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Cria um helper de compatibilidade para carregar os plugins antigos do Next.js no novo formato Flat Config
const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  // Carrega as configurações de Core Web Vitals e TypeScript do Next.js com segurança
  ...compat.extends("next/core-web-vitals", "next/typescript"),

  // Definição global de ignores (substitui o globalIgnores antigo do Flat Config)
  {
    ignores: [
      ".next/**",
      "out/**",
      "build/**",
      "next-env.d.ts",
      "node_modules/**",
    ],
  },
];

export default eslintConfig;
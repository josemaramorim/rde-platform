This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Mobile App Support

This frontend is now installable as a Progressive Web App (PWA). After running the app, open it on Android and use the browser menu to add it to your home screen.

- The app manifest is available at `/manifest.webmanifest`
- A service worker is registered automatically from `/sw.js`
- The installed app runs in `standalone` mode

### Como usar no Android

1. Configure o backend para que seja acessível do celular.
   - Em ambiente de desenvolvimento, use o IP da máquina na mesma rede local, por exemplo:
     - `NEXT_PUBLIC_API_URL=http://192.168.0.100:8000`
     - `NEXT_PUBLIC_FRONTEND_URL=http://192.168.0.100:3000`
   - Em produção, aponte para o endpoint público da API.
2. No diretório `rde-frontend`, instale dependências e execute:
   - `npm install`
   - `npm run dev`
3. No Android, abra o Chrome em `http://<IP-da-máquina>:3000`.
4. Use o menu do navegador e escolha **Adicionar à tela inicial**.
5. A partir da tela inicial, o app abre em modo standalone sem a barra de navegação do navegador.

> Obs: esse fluxo é um app instalável (PWA). Se você quiser gerar um APK nativo, use o fluxo Capacitor documentado em `MOBILE_ANDROID.md`.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

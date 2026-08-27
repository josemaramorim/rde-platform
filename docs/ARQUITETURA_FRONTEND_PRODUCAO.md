# Guia de Arquitetura Frontend em Produção — RDE Platform

Este documento detalha as opções arquiteturais para o frontend Next.js da plataforma RDE em ambiente de produção, comparando abordagens, vantagens, desvantagens e estratégias de evolução.

---

## 1. Contexto Histórico e Diagnóstico

### O Problema Identificado
Em produção, ao clicar nos itens do menu lateral (Sidebar), a interface apresentava atrasos perceptíveis (2 a 5 segundos de tela congelada), enquanto no ambiente local (`npm run dev`) a navegação era instantânea (30 a 50 ms).

### As Causas Raiz
1. **Interceptação de Navegação (Hard Reload)**:
   - Em `src/main.py`, existia um script (`patchSidebarLinks`) injetado no HTML que interceptava todos os cliques em links `<aside a[href]>`, cancelava o comportamento padrão (`e.preventDefault()`) e forçava `window.location.href = href`.
   - Isso desativava o comportamento de **SPA (Single Page Application)** nativo do Next.js/React e forçava o navegador a recarregar a página inteira do zero a cada clique.
2. **Política de Cache Inadequada para Chunks**:
   - O servidor FastAPI estava enviando `Cache-Control: no-cache, no-store, must-revalidate` para todos os arquivos `.js`.
   - Como os pacotes do Next.js e React possuem nomes únicos com hash (ex: `chunks/14e20bopbv6s_.js`), eles são imutáveis e deveriam ser cacheados. O bloqueio forçava o navegador a baixar megabytes de JavaScript a cada clique pela rede/túnel de produção.
3. **Re-execução de Providers e Hooks**:
   - A cada hard reload, todos os providers globais (`SessionProvider`, `EstadoProvider`, `VersionCheck`) reiniciavam do zero, disparando chamadas de validação e refresh de saldo repetidamente.

---

## 2. Opções Arquiteturais Disponíveis

### Opção A: Next.js SPA Nativo no Docker (Implementada)

> **Objetivo**: Manter toda a aplicação autocontida em um único container Docker, eliminando a camada de interceptação e permitindo que o Next.js gerencie a navegação em memória.

#### Como Funciona:
- O Next.js compila via `output: "export"` gerando arquivos HTML e pacotes de script otimizados.
- O FastAPI serve os arquivos estáticos na porta 8000, mapeando as rotas para os arquivos estáticos e repassando requisições `/api/` e endpoints de autenticação diretamente para as rotas FastAPI.
- A Sidebar utiliza o componente `<Link>` puro do Next.js. Ao clicar, o React troca os componentes de tela na memória em menos de 50ms, sem recarregar o navegador.
- Arquivos de código (`_next/static/`) recebem `Cache-Control: public, max-age=31536000, immutable`. O navegador faz o download apenas uma vez.
- Somente arquivos HTML recebem validação direta para garantir que atualizações do sistema sejam entregues imediatamente.

#### Vantagens:
- **Zero serviços externos adicionais**: Não requer contas ou serviços como Vercel ou Netlify.
- **Tudo em um comando**: `docker compose up -d` sobe backend, frontend, banco SQLite e robôs.
- **Transição instantânea**: A navegação volta a ser de 30 a 50ms como no desenvolvimento local.
- **Simplicidade de rede**: Frontend e backend compartilham o mesmo host e porta (8000), eliminando problemas de CORS ou certificado SSL entre domínios diferentes.

---

### Opção B: Separação de Camadas (Frontend no Vercel / Cloudflare Pages + API no Docker)

> **Objetivo**: Padrão de microsserviços corporativo, delegando a entrega do frontend a redes globais de borda (CDN Edge).

#### Como Funciona:
- O repositório do frontend é conectado à Vercel ou Cloudflare Pages (ambos com planos gratuitos robustos).
- A cada `git push`, a Vercel compila e distribui os arquivos estáticos e SSR para mais de 300 data centers globais.
- A variável `NEXT_PUBLIC_API_URL` aponta para a VPS/Docker onde roda o backend FastAPI (ex: `https://api.seudominio.com`).
- O FastAPI no Docker cuida exclusivamente de: APIs REST, WebSockets, conexão com corretoras (IQ Option, Deriv) e robô do Telegram.

#### Vantagens:
- Latência global mínima para carregar o primeiro HTML (10 a 30ms em qualquer lugar do mundo).
- O FastAPI na VPS fica livre de servir arquivos estáticos, poupando CPU e memória para as operações financeiras.
- Deploys de frontend independentes dos deploys de backend.

#### Desvantagens / Requisitos:
- Exige domínio próprio com SSL válido na VPS para evitar erros de conteúdo misto (Mixed Content: HTTPS no frontend chamando HTTP no backend).
- Exige configuração rigorosa de CORS no backend para liberar a origem do frontend.
- Dois ambientes para gerenciar em vez de um.

---

### Opção C: Multi-Container no Docker com Nginx Reverso (Docker Standalone)

> **Objetivo**: Arquitetura profissional auto-hospedada (Self-Hosted) em VPS própria, sem depender de Vercel.

#### Como Funciona:
- Um arquivo `docker-compose.yml` com 2 ou 3 serviços:
  1. `nginx`: Escuta nas portas 80/443. Serve diretamente a pasta estática do frontend com compressão Brotli/Gzip e cache agressivo. Faz proxy pass de `/api/*` e `/auth/*` para o backend.
  2. `rde-backend`: Container FastAPI rodando na porta 8000 internamente na rede Docker.
  3. *(Opcional)* `redis`: Para cache e filas assíncronas do copier.

#### Vantagens:
- Nginx é o padrão ouro da indústria para servir arquivos estáticos com altíssimo throughput.
- O Python não precisa de lógica de fallback SPA no código (`src/main.py` fica 100% focado na lógica de negócio).
- Todo o tráfego SSL pode ser terminado diretamente no Nginx com Certbot / Let's Encrypt automático.

---

## 3. Matriz Comparativa

| Critério | Opção A (Atual - Docker SPA Limpo) | Opção B (Vercel + Docker API) | Opção C (Nginx + Docker Multi-Container) |
| :--- | :--- | :--- | :--- |
| **Velocidade de Navegação (Sidebar)** | Instantânea (30-50ms) | Instantânea (30-50ms) | Instantânea (30-50ms) |
| **Complexidade de Manutenção** | Baixa (1 container) | Média (2 plataformas) | Média (Nginx conf + SSL) |
| **Custo de Infraestrutura** | $0 adicional (mesma VPS) | $0 adicional (Vercel Free) | $0 adicional (mesma VPS) |
| **Dependência de Terceiros** | Nenhuma (100% seu) | Vercel / Cloudflare | Nenhuma (100% seu) |
| **Consumo de CPU do Backend** | Baixo | Mínimo | Mínimo |
| **Recomendado Para** | Fase Atual / Estabilidade | Expansão para múltiplos clientes | Produção Enterprise Auto-Hospedada |

---

## 4. Roteiro para Futura Migração (Caso queira ir para Opção B ou C)

1. **Para Opção B (Vercel)**:
   - Apontar o subdomínio `api.seudominio.com` para o IP da sua VPS (onde roda o Docker).
   - Configurar `NEXT_PUBLIC_API_URL=https://api.seudominio.com` nas variáveis de ambiente da Vercel.
   - Conectar o repositório GitHub na Vercel selecionando a pasta raiz como `frontend/`.

2. **Para Opção C (Nginx Reverso)**:
   - Adicionar o bloco de serviço `nginx` no `docker-compose.yml`.
   - Mapear as rotas estáticas para `/usr/share/nginx/html` e rotas dinâmicas para `http://rde-backend:8000`.
   - Remover as linhas de fallback estático do final do `src/main.py`.

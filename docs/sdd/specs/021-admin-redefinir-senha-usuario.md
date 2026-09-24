# 021 — Admin redefine a senha de um usuário pelo modal "Gerir"

- **Status:** Rascunho
- **Autor:** Claude (a pedido de josemaramorim)
- **Data:** 2026-09-24
- **Impedimento(s) relacionado(s):** Nenhum
- **Zona de alto risco?** Não. Toca `src/routes/admin_routes.py` e `frontend/app/admin/page.tsx`; nenhum arquivo de broker, copier, bridge ou executor.

## Problema

O admin não tem como trocar a senha de outro usuário pelo painel:

- O modal **Gerir Cliente** ([frontend/app/admin/page.tsx:579-654](../../../frontend/app/admin/page.tsx)) só oferece liberar/revogar licença, bloquear/desbloquear, trocar plano e editar notas.
- A senha só é definida na **criação** do usuário (`POST /auth/register`, `admin/page.tsx:253`).
- Os caminhos que existem não resolvem o caso do admin:
  - **Perfil → Alterar Senha** (`PATCH /users/me`, [frontend/app/perfil/page.tsx:82-111](../../../frontend/app/perfil/page.tsx)): só o próprio usuário, e só se ele ainda souber a senha atual para entrar.
  - **Esqueci minha senha**: depende de e-mail, e o ICP não tem `MAIL_PASSWORD` configurado, então [src/email_service.py:9-10](../../../src/email_service.py) falha e o e-mail não sai.
  - **`PATCH /users/{id}`** do fastapi-users ([src/main.py:321](../../../src/main.py)): funciona para superusuário, mas só pelo `/docs`, sem interface, e **não grava nada no `AdminLog`**. O admin fica sem registro de quem trocou a senha de quem.

Motivação imediata: depois da troca de `SECRET_KEY` no ICP (spec 020) todos os usuários foram deslogados, e quem não lembra a senha não tem como voltar sem o admin.

## Contexto

- Os endpoints de admin em uso ficam em [src/routes/admin_routes.py](../../../src/routes/admin_routes.py) (`/admin/v2/*`), protegidos por `current_superuser` e registrando cada ação em `AdminLog` e em `log_admin` (por exemplo, `set_user_plan`, linhas ~230-265). Os endpoints de admin em `main.py` são legados e não devem ser copiados (CLAUDE.md).
- O hash e a validação de senha já são feitos pelo `UserManager` do fastapi-users ([src/auth/manager.py](../../../src/auth/manager.py)). **Reutilizar** `user_manager.update(UserUpdate(password=...), user, safe=False)`, que é o mesmo caminho do `PATCH /users/me` e do `PATCH /users/{id}`, em vez de chamar um hasher diretamente (Constituição §2).
- Os logins usam JWT sem estado (`src/auth/backend.py`). Trocar a senha **não derruba** sessões que já estejam abertas: o token continua válido até expirar (`ACCESS_TOKEN_EXPIRE_MINUTES`, 7 dias por padrão). Revogar sessões fica fora do escopo e está registrado abaixo como limitação conhecida.

## Proposta

### Backend — `src/routes/admin_routes.py`

Novo endpoint, no mesmo formato de `set_user_plan`:

```
PATCH /admin/v2/user/{user_id}/password
Body: { "new_password": "<string>" }
Auth: current_superuser
```

- 404 se o usuário não existe.
- 400 se `new_password` tiver menos de 8 caracteres, a mesma regra que o frontend já aplica em `perfil/page.tsx:85`. A validação fica no backend também, para não depender só da interface.
- Troca a senha via `UserManager.update(UserUpdate(password=new_password), user, safe=False)`, obtendo o manager pela dependência `get_user_manager` já existente.
- Grava `AdminLog(admin_email, action="reset_user_password", target_user=user.email, detail="")` e chama `log_admin(...)`. **A senha nunca vai para log, `AdminLog` nem resposta.**
- Resposta: `{"status": "success"}`.
- Type hints e tratamento de erro conforme a Constituição §4.

### Frontend — `frontend/app/admin/page.tsx`

No modal **Gerir Cliente**, entre o bloco de plano e o de notas, uma seção **"Redefinir senha"** com:

- dois campos `type="password"`, **Nova senha** e **Confirmar senha**;
- o botão **Redefinir senha**, desabilitado enquanto os campos estiverem vazios ou a requisição estiver em andamento;
- validação local: pelo menos 8 caracteres e os dois campos iguais, com as mesmas mensagens de `perfil/page.tsx`;
- chamada `PATCH /admin/v2/user/{id}/password` com o token do admin, no mesmo formato de `changePlan`;
- mensagem de sucesso ou erro dentro do próprio modal. Os campos são limpos ao fechar o modal e após sucesso;
- estado próprio (`resetPwd`, `resetPwdConfirm`, `resetPwdMsg`, `resetPwdLoading`), sem reaproveitar `saveMsg`, para não misturar com o "Salvar notas".

Visual no mesmo padrão dos outros blocos do modal (classes Tailwind existentes).

### Arquivos tocados

- `src/routes/admin_routes.py`: novo endpoint
- `frontend/app/admin/page.tsx`: seção nova no modal
- `docs/sdd/specs/021-admin-redefinir-senha-usuario.md`: esta spec

## Critérios de aceite

- [ ] Admin abre **Gerir** num usuário, define uma senha nova e vê a mensagem de sucesso.
- [ ] O usuário consegue entrar com a senha nova, e a senha antiga passa a ser recusada.
- [ ] Senha com menos de 8 caracteres ou confirmação diferente: erro no modal, e nenhuma requisição é enviada.
- [ ] Chamando o endpoint direto com senha curta: HTTP 400.
- [ ] Chamando o endpoint com token de usuário comum: HTTP 403.
- [ ] `user_id` inexistente: HTTP 404.
- [ ] Aparece uma linha `reset_user_password` no `AdminLog` com o e-mail do admin e do usuário, **sem a senha**.
- [ ] A senha não aparece no log do backend nem na resposta HTTP.
- [ ] Fechar e reabrir o modal (no mesmo usuário ou em outro) mostra os campos de senha vazios.
- [ ] O resto do modal (plano, licença, bloquear, notas) continua funcionando como antes.

## Impacto em performance

Neutro. É um endpoint administrativo, fora do hot path de ordens, com uma leitura e uma escrita no banco por chamada, iniciadas manualmente pelo admin.

## Limitações conhecidas

- Sessões já abertas do usuário continuam válidas até o JWT expirar (padrão de 7 dias). Se o motivo da troca for suspeita de conta invadida, hoje o caminho para derrubar a sessão é **Bloquear Conta** no mesmo modal (`is_active=False` faz o fastapi-users recusar o token). Revogar tokens de verdade exigiria uma estratégia de JWT com estado e fica para outra spec.

## Plano de rollback

`git revert` do commit de implementação. Não há migração de schema: usa as colunas `hashed_password` e `admin_logs` que já existem. Senhas trocadas enquanto a funcionalidade esteve no ar continuam valendo, o que é o comportamento esperado.

## Aprovação

- [x] Revisado contra `docs/sdd/CONSTITUICAO.md` (§2 reutiliza o `UserManager` do fastapi-users, §4 type hints e sem `except: pass`, §7 nada implementado antes da aprovação, §8 branch própria)
- [ ] Aprovado explicitamente pelo usuário antes do início da implementação

# 🔀 RDE Platform — Guia de Merge entre Dois Repositórios Git

> **Contexto:** Você possui duas versões do projeto `rde-platform` em repositórios Git diferentes, cada uma com correções independentes. Este guia explica como unir as alterações dos dois de forma segura, usando branches.

---

## 📋 Estrutura de Branches Recomendada

```
josemaramorim/rde-platform (repositório PRINCIPAL — ICP faz deploy daqui)
  ├── main          ← produção (deploy automático via GitHub Actions)
  └── dev-merge     ← branch de integração (recebe as correções do outro repo)

OUTRO_GIT/rde-platform (repositório SECUNDÁRIO)
  ├── main          ← versão deles
  └── icp-fixes     ← branch de exportação das correções
```

> [!IMPORTANT]
> **Nunca faça merge diretamente na `main` sem antes testar na `dev-merge`.**
> A `main` está vinculada ao deploy automático no ICP.

---

## 🚀 Procedimento Completo

### ✅ ETAPA 1 — Criar a branch `dev-merge` no repositório principal

Execute dentro de `C:\Users\WIN10\Downloads\RDE_5`:

```powershell
# Garante que está na main atualizada
git checkout main
git pull origin main

# Cria e sobe a branch dev-merge para o GitHub
git checkout -b dev-merge
git push -u origin dev-merge
```

Resultado no GitHub:
```
josemaramorim/rde-platform
  ├── main       ✅ (existente)
  └── dev-merge  ✅ (nova)
```

---

### ✅ ETAPA 2 — Criar a branch `icp-fixes` no repositório secundário

Execute dentro da pasta do **OUTRO projeto**:

```powershell
# Garante que está na main do outro projeto
git checkout main
git pull origin main

# Cria e sobe a branch de exportação
git checkout -b icp-fixes
git add .
git commit -m "chore: prepara correções para merge com josemaramorim/rde-platform"
git push -u origin icp-fixes
```

---

### ✅ ETAPA 3 — Integrar as correções no repositório principal

Volte para o terminal dentro de `C:\Users\WIN10\Downloads\RDE_5`:

```powershell
# Entra na branch de integração
git checkout dev-merge

# Adiciona o outro repositório como remote secundário
git remote add outro-repo https://github.com/OUTRO_USUARIO/rde-platform.git

# Baixa as branches do outro repositório
git fetch outro-repo

# Lista as branches disponíveis do outro repo (para confirmar)
git branch -r | findstr outro-repo

# Faz o merge das correções na branch dev-merge
git merge outro-repo/icp-fixes --allow-unrelated-histories
```

---

### ⚠️ Resolvendo Conflitos (se houver)

Se o Git encontrar arquivos modificados nos dois repositórios, ele listará os conflitos:

```
CONFLICT (content): Merge conflict in src/main.py
CONFLICT (content): Merge conflict in requirements.txt
Automatic merge failed; fix conflicts and then commit the result.
```

**Para ver todos os arquivos em conflito:**
```powershell
git status
```

**Cada arquivo conflitante terá marcadores assim:**
```python
<<<<<<< HEAD (sua versão — dev-merge)
    # código do josemaramorim/rde-platform
=======
    # código do outro repositório
>>>>>>> outro-repo/icp-fixes
```

**Resolva editando cada arquivo** (escolha qual versão manter ou combine as duas), e depois:

```powershell
git add src/main.py
git add requirements.txt
git commit -m "merge: integração das correções do outro repositório"
git push origin dev-merge
```

---

### ✅ ETAPA 4 — Visualizar as diferenças antes do merge

Para ver exatamente o que mudou antes de aplicar:

```powershell
# Ver todos os arquivos que diferem entre as branches
git diff main..dev-merge --name-only

# Ver as mudanças detalhadas de um arquivo específico
git diff main..dev-merge -- src/main.py
```

---

### ✅ ETAPA 5 — Aplicar em Produção (merge na `main`)

Após testar que a `dev-merge` está funcionando corretamente:

```powershell
# Volta para a main
git checkout main

# Faz o merge da branch integrada
git merge dev-merge

# Envia para o GitHub (dispara o deploy automático no ICP!)
git push origin main
```

> [!TIP]
> Após o push, acompanhe o build em:
> `https://github.com/josemaramorim/rde-platform/actions`
>
> Quando o ícone ficar ✅ verde, faça o **Redeploy** no ICP Compose (Editar → Confirmar) para atualizar o container.

---

## 🔄 Fluxo Resumido

```
[Outro Repo]                    [Repo Principal]
    │                                  │
    ├── main                           ├── main (produção/ICP)
    │                                  │
    └── icp-fixes ──── fetch ────→    └── dev-merge
                        merge                │
                                             │ (testa e aprova)
                                             │
                                        merge ↓
                                           main
                                             │
                                      git push origin main
                                             │
                                      GitHub Actions ↓
                                      Nova imagem no GHCR
                                             │
                                      ICP Compose Redeploy ↓
                                      Container atualizado ✅
```

---

## 📋 Comandos de Referência Rápida

| Ação | Comando |
|------|---------|
| Criar branch | `git checkout -b nome-da-branch` |
| Listar branches locais | `git branch` |
| Listar branches remotas | `git branch -r` |
| Adicionar remote | `git remote add nome-do-remote URL` |
| Listar remotes | `git remote -v` |
| Baixar branches de um remote | `git fetch nome-do-remote` |
| Ver diferenças entre branches | `git diff branch1..branch2` |
| Fazer merge | `git merge branch-origem` |
| Cancelar merge com conflito | `git merge --abort` |
| Deletar branch local | `git branch -d nome-da-branch` |
| Deletar branch remota | `git push origin --delete nome-da-branch` |

---

## ⚡ Dica: Manter as Branches Sincronizadas

Para manter a `dev-merge` atualizada com a `main` ao longo do tempo:

```powershell
git checkout dev-merge
git merge main
git push origin dev-merge
```

---

> [!NOTE]
> Após a integração bem-sucedida, você pode **deletar** a `dev-merge` e a `icp-fixes` se não precisar mais delas, mantendo o repositório limpo:
> ```powershell
> git branch -d dev-merge
> git push origin --delete dev-merge
> ```

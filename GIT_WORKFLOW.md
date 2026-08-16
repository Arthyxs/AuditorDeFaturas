# Fluxo Git e GitHub — InvoiceAuditor

O GitHub privado é o checkpoint externo do projeto.

## Regra principal

Ao terminar um milestone:

```text
implementar
↓
testar
↓
validar Docker
↓
atualizar documentação/memória
↓
revisar git diff/status
↓
commit
↓
push GitHub
↓
registrar hash
↓
milestone concluído
```

Um milestone não está concluído antes do push.

## Nunca versionar

- `.env`;
- senhas;
- API keys;
- documentos reais;
- faturas reais;
- tarifários reais;
- dumps reais;
- `data/`;
- logs sensíveis.

## Commits

Preferir Conventional Commits:

```text
feat(imap): add canonical message deduplication
feat(tariffs): add persistent tariff catalog
feat(ai): implement OpenAI provider
feat(audit): add per-document invoice auditing
feat(reanalysis): add manual Sol reanalysis
fix(email): preserve identity after IMAP folder move
test(audit): cover mixed pending and incorrect documents
```

## Checkpoints intermediários

Milestones grandes podem ter commits estáveis intermediários. Cada checkpoint deve representar estado coerente e, quando aplicável, testado.

## Antes do commit

Executar/revisar:

```bash
git status
git diff
git diff --staged
```

Verificar que não há segredo, `.env`, dado real ou arquivo temporário irrelevante.

## Push

Depois do commit:

```bash
git push
```

Registrar o hash final em `PROJECT_STATUS.md`.

## Branches

No começo, um único agente sequencial pode trabalhar na `main` para simplificar.

Quando houver worktrees/agentes paralelos/feature arriscada, usar branches como:

```text
feat/imap-ingestion
feat/audit-engine
feat/frontend-reports
fix/tariff-selection
```

## Não reescrever histórico

Não usar automaticamente force push, rebase ou reset destrutivo sobre histórico publicado. Só mediante pedido explícito.

## Troca de máquina

Em nova máquina:

```bash
git clone <repo>
cd InvoiceAuditor
```

Depois:
1. recriar `.env`;
2. iniciar Docker;
3. restaurar `data/` e banco somente se precisar dos dados operacionais;
4. abrir no Codex;
5. usar o prompt de retomada de `README_BOOTSTRAP.md`.

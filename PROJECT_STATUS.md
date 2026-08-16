# InvoiceAuditor — Estado do Projeto

**Atualizado em:** 2026-08-16
**Especificação:** v3.0, fechada para implementação
**Fase atual:** runtime e configuração segura concluídos; persistência é a próxima etapa
**Macroetapa atual:** B — Fundação executável, segura e persistente
**Milestone atual:** nenhum em execução; M03 validado e concluído, M04 desbloqueado

## Resumo executivo

M00–M03 estão concluídos. Além do runtime canônico, a aplicação agora carrega configuração
tipada e validada, recusa segredos internos inseguros e mantém valores secretos redigidos.
Os scripts Windows/Linux criam uma instalação idempotente, geram os segredos internos e
iniciam o Compose sem edição manual do `.env`.

Nenhuma regra de negócio, modelo de persistência, migration, integração, autenticação ou
job futuro foi antecipado. O worker do M02 mantém apenas o processo e seu heartbeat; jobs
duráveis permanecem no M09.

## Milestones concluídos

- **M00 — Aprovação do plano e prontidão do ambiente:** concluído em 2026-08-15.
- **M01 — Estrutura executável e qualidade básica:** concluído em 2026-08-16.
- **M02 — Runtime Docker Compose e PostgreSQL:** concluído em 2026-08-16.
- **M03 — Configuração, segredos e setup multiplataforma:** concluído em 2026-08-16.

## Estrutura entregue até M03

- `pyproject.toml` com Python 3.12+, dependências FastAPI/Uvicorn e grupo de desenvolvimento;
- pacote `app/` organizado pelas camadas aprovadas: API, aplicação, domínio, portas,
  cálculo, infraestrutura, relatórios e worker;
- factory e entry point FastAPI mínimos, sem efeitos de infraestrutura ou endpoints futuros;
- `tests/` com smoke tests e diretórios reservados para as suítes aprovadas;
- Ruff para lint e formatação;
- mypy em modo estrito como solução documentada de type checking Python;
- frontend mínimo React/TypeScript/Vite com estrutura `api`, `auth`, `components`,
  `features`, `pages` e `routes`;
- ESLint, TypeScript type check, build de produção e lockfile npm;
- `README.md` com requisitos, comandos de desenvolvimento, gates e limites do M01.
- `Dockerfile` multi-stage com build Vite e runtime Python 3.12 não-root;
- `docker-compose.yml` com `app`, `worker` e PostgreSQL 17;
- imagem compartilhada para os dois processos da aplicação;
- volume nomeado para PostgreSQL e bind mounts persistentes sob `data/`;
- health checks dos três serviços, endpoint `/api/health/live` e heartbeat do worker.
- `Settings` Pydantic tipado para dev/test/prod, timezone, banco e opções aprovadas;
- segredos obrigatórios como `SecretStr`, validação de força/placeholder e resumo redigido;
- `setup.ps1` e `setup.sh` idempotentes, com geração criptográfica de segredos internos;
- `.env.example` sem credenciais/placeholders e `.env` operacional ignorado pelo Git;
- timezone IANA portável no Windows/Linux por `tzdata`.

## Trabalho não iniciado

- M04–M26;
- modelo de banco, sessão, repositories, unit of work e migrations;
- autenticação, storage, tarifários e interfaces de produto;
- IMAP, OpenAI e demais integrações;
- regras financeiras, auditoria, relatórios e golden cases.

## Estado do repositório e Git

- branch atual: `main`;
- upstream: `main` rastreia `origin/main`;
- remoto: `origin` configurado para `https://github.com/Arthyxs/AuditorDeFaturas.git`;
- commit técnico de conclusão do M01 presente em `origin/main`:
  `5609f919b967b163dd9c495a5b8c9e55779f7395`;
- commit técnico de conclusão do M02 presente localmente e em `origin/main`:
  `1c9c4adf2feeb2b88a653b0a89899f184efe1043`;
- commit técnico de conclusão do M03 presente localmente e em `origin/main`:
  `53d5196a9a24862aa4130ead2536caf48d0d79b1`;
- divergência local/remoto após o push do M03: `0` à frente, `0` atrás;
- revisão pré-commit: sem `.env`, segredos, dados operacionais ou artefatos gerados no
  conjunto destinado ao commit.

## Estado do ambiente

### Toolchains usados no M01

- Python 3.12.13 em ambiente virtual local ignorado pelo Git;
- FastAPI 0.141.1 e Uvicorn 0.52.3;
- pytest 9.1.1, Ruff 0.16.3 e mypy 1.20.2;
- Node.js 24.19.0 e npm 11.17.0;
- React 19.2.8, TypeScript 6.0.3 e Vite 8.2.1;
- ESLint 10.8.1.

### Runtime canônico validado no M02

- WSL2: distribuição padrão `docker-desktop`, versão padrão 2;
- Docker Client/Engine: 29.7.2;
- Docker Desktop: 4.86.0, contexto `desktop-linux`, Engine Linux `amd64`;
- Docker Compose: 5.3.1;
- build limpo multi-stage: aprovado;
- `app`, `worker` e `postgres`: `healthy` após subida inicial e recriação;
- endpoint HTTP `/api/health/live`: aprovado;
- path Windows `C:\Users\Arthur\Documents\auditordefaturas` resolvido corretamente pelo Compose;
- marker PostgreSQL sobreviveu a `docker compose down` e recriação dos containers;
- tabela descartável de smoke removida após o teste; volume persistente preservado.

### Configuração e setup validados no M03

- setup Windows limpo: `.env`, segredos internos de 96 caracteres, diretórios, build e
  startup sem edição manual;
- setup Linux: duas execuções em Bash 5.3/container, idempotência, path com espaços e
  ausência de segredos no output;
- senha PostgreSQL gerada: autenticação real aprovada;
- configuração do app no container: carregamento tipado aprovado;
- logs do Compose: nenhum segredo interno encontrado;
- recriação de containers: persistência do M02 preservada, tabela de regressão removida.

## Status de testes, build e execução

- backend/unit/integration tests: **PASS**, 20 testes; 1 skip condicional do setup Linux no
  host Windows, executado separadamente com sucesso em container Linux;
- Python lint (`ruff check`): **PASS**;
- Python format check (`ruff format --check`): **PASS**, 52 arquivos formatados;
- Python type check (`mypy`, modo estrito): **PASS**, 44 arquivos verificados;
- frontend lint (`eslint`): **PASS**;
- frontend TypeScript type check (`tsc -b`): **PASS**;
- frontend production build: **PASS** dentro do build Docker sem cache, Vite 8.2.1;
- Compose config: **PASS**;
- Compose health: **PASS**, três serviços saudáveis;
- persistência PostgreSQL entre recriações: **PASS**;
- scan de segredos/artefatos: **PASS**, `.env` ignorado e nenhum segredo real versionado;
- artefatos locais `.venv`, caches, `node_modules` e `frontend/dist`: ignorados pelo Git;
- configuração válida/inválida e segredo ausente: **PASS**;
- idempotência/paths/logs de setup: **PASS** Windows e Linux;
- migrations: ainda não aplicável; começam no M04.

## Bloqueios, riscos e findings

Nenhum bloqueio técnico ou finding aberto para iniciar M04. Dependências externas futuras
continuam documentadas no plano e não afetam M04.

`CODE_REVIEW.md` permanece sem findings. `DECISIONS.md` não foi alterado porque o M03
concretizou a especificação e ADR-015 sem introduzir nova decisão arquitetural.

## Último commit estável

`53d5196a9a24862aa4130ead2536caf48d0d79b1` — `feat: establish secure M03 configuration`

Este commit contém a implementação, os testes, os gates e a memória de conclusão do M03.

## Próxima ação recomendada

Iniciar somente M04 — Persistência, migrations e transações.

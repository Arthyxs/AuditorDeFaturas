# InvoiceAuditor — Estado do Projeto

**Atualizado em:** 2026-08-16
**Especificação:** v3.0, fechada para implementação
**Fase atual:** fundação executável, segura e persistente concluída até M06
**Macroetapa atual:** B — Fundação executável, segura e persistente
**Milestone atual:** nenhum em execução; M06 validado e concluído, M07 desbloqueado e não iniciado

## Resumo executivo

M00–M06 estão concluídos. Além da autenticação/RBAC, a aplicação agora possui porta de
storage substituível e adapter local imutável, atômico e persistente, com nomes internos,
SHA-256, metadata, leitura verificada, exclusão física controlada e validação segura dos
formatos documentais aprovados.

Nenhuma regra de negócio, entidade futura, integração ou job foi antecipado.
O worker do M02 mantém apenas o processo e seu heartbeat; jobs duráveis permanecem no M09.

## Milestones concluídos

- **M00 — Aprovação do plano e prontidão do ambiente:** concluído em 2026-08-15.
- **M01 — Estrutura executável e qualidade básica:** concluído em 2026-08-16.
- **M02 — Runtime Docker Compose e PostgreSQL:** concluído em 2026-08-16.
- **M03 — Configuração, segredos e setup multiplataforma:** concluído em 2026-08-16.
- **M04 — Persistência, migrations e transações:** concluído em 2026-08-16.
- **M05 — Autenticação, RBAC e primeiro administrador:** concluído em 2026-08-16.
- **M06 — Storage local imutável e uploads seguros:** concluído em 2026-08-16.

## Estrutura entregue até M06

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
- SQLAlchemy 2/psycopg, engine UTC, session factory e contexto transacional;
- repository SQLAlchemy genérico e unit of work explícito;
- base declarativa com UUID, UTC, JSONB, enums/constraints e `NUMERIC(20,6)`;
- Alembic e baseline `20260816_0001`, sem tabelas futuras simuladas;
- setup Windows/Linux executando `alembic upgrade head` após o startup;
- override Compose de teste expondo PostgreSQL somente em `127.0.0.1:55432`.
- modelos `users`/`sessions` e migration `20260816_0002` reversível;
- senha Argon2id e sessão opaca com somente digest SHA-256 persistido;
- bootstrap único e concorrente protegido por token gerado pelo setup e advisory lock;
- login, identidade, logout, expiração/revogação, cookie HTTPOnly/SameSite Strict/Secure
  sob HTTPS e proteção de origem;
- dependências reutilizáveis de autenticação e matriz RBAC;
- telas React de bootstrap, login, sessão autenticada e logout.
- porta `StorageProvider`, metadata imutável e adapter `LocalStorageProvider`;
- streaming com limite, SHA-256, `fsync` e publicação atômica do blob+sidecar;
- nomes internos UUID, integridade revalidada em leitura e colisões sem overwrite;
- validação de nome/extensão/MIME/conteúdo/tamanho para PDF/XLSX/XLS/CSV/PNG/JPEG/TIFF;
- bloqueio de traversal, conteúdo truncado/divergente, ZIP bomb e executáveis;
- exclusão física negada por padrão e liberada somente com motivo/referências verificadas;
- persistência comprovada no bind mount após recriação real do container `app`.

## Trabalho não iniciado

- M07–M26;
- tarifários e interfaces de produto;
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
- commit técnico de conclusão do M04 presente localmente e em `origin/main`:
  `622581af718d73898438372bcc41e1a0c16f4906`;
- commit técnico de conclusão do M05 presente localmente e em `origin/main`:
  `fa78c0b47530c659af3f388768cdea3c8b46e737`;
- commit técnico de conclusão do M06 presente localmente e em `origin/main`:
  `cb112e223018b939bca646007633caae2510234a`;
- divergência local/remoto após o push do M06: `0` à frente, `0` atrás;
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

### Persistência e migrations validadas no M04

- migration de banco vazio até head: **PASS** em PostgreSQL real descartável;
- base → head, downgrade base e novo upgrade: **PASS**;
- transações/repository/unit of work: **PASS** para commit, rollback e recuperação;
- constraints únicas/check/enum: **PASS**;
- `Decimal`/`NUMERIC(20,6)`, JSONB, UUID e UTC: **PASS**;
- `alembic current`: `20260816_0001 (head)`;
- `alembic check`: **PASS**, nenhum drift;
- revisão e dado decimal sobreviveram à recriação; tabela descartável removida;
- nenhum banco descartável de teste permaneceu no cluster.

## Status de testes, build e execução

- suíte com PostgreSQL real: **PASS**, 23 testes; 1 skip condicional do setup Linux no host
  Windows, já executado separadamente em container Linux;
- suíte local sem exposição do banco: **PASS**, 20 testes; 4 skips condicionais esperados;
- Python lint (`ruff check`): **PASS**;
- Python format check (`ruff format --check`): **PASS**, 61 arquivos formatados;
- Python type check (`mypy`, modo estrito): **PASS**, 50 arquivos verificados;
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
- migrations: **PASS**, head aplicado, downgrade/upgrade e drift check aprovados.
- segurança M05 em PostgreSQL real: **PASS**, hash/verificação Argon2id, bootstrap
  concorrente, bloqueio do segundo admin, expiração, revogação, logout, CSRF/origin,
  cookies e matriz RBAC;
- suíte com PostgreSQL real: **PASS**, 32 testes e 1 skip Linux condicional já coberto no
  milestone de setup;
- migration atual: `20260816_0002 (head)`; `alembic check`: **PASS**, sem drift;
- build Docker e frontend: **PASS**; `app`, `worker` e `postgres`: **healthy**.
- storage M06: **PASS**, 30 testes unitários de integridade, atomicidade, colisão,
  truncamento/corrupção, traversal, MIME/extensão/conteúdo, limite, ZIP bomb, não execução e
  exclusão controlada;
- persistência após recriação real do container `app`: **PASS**, arquivo sintético verificado
  e removido ao final;
- suíte completa com PostgreSQL real: **PASS**, 63 testes e 2 skips condicionais esperados;
- Ruff/format/mypy/ESLint/TypeScript: **PASS**; Docker build e três health checks: **PASS**;
- Alembic permanece em `20260816_0002 (head)` e sem drift; M06 não exige schema novo.

## Bloqueios, riscos e findings

Nenhum bloqueio técnico ou finding aberto. M07 está tecnicamente desbloqueado, mas não foi
iniciado neste chat conforme instrução explícita.

`CODE_REVIEW.md` permanece sem findings. ADR-004 foi concretizada com publicação atômica de
diretório, sidecar mínimo, verificação em leitura e autorização explícita para exclusão.

## Último commit estável

`cb112e223018b939bca646007633caae2510234a` — `feat: add immutable M06 local storage`

Este commit contém a implementação, os testes, os gates e a memória de conclusão do M06.

## Próxima ação recomendada

Em uma nova execução autorizada, iniciar M07 — Catálogo e API de tarifários.

# InvoiceAuditor — Estado do Projeto

**Atualizado em:** 2026-08-17
**Especificação:** v3.0, fechada para implementação
**Fase atual:** entrada por e-mail em implementação; ingestão idempotente concluída até M11
**Macroetapa atual:** D — Entradas IMAP/manual e preparação de faturas
**Milestone atual:** M11 concluído; M12 está desbloqueado, mas não foi iniciado

## Resumo executivo

M00–M11 estão implementados. A revisão independente de 2026-08-17 não encontrou CRITICAL
e abriu quatro findings HIGH; todos foram corrigidos e revalidados no commit
`97fb4da3811983e2c6e26d8558cb9989b56a5d2b`. A SPA agora é servida pelo runtime canônico, todo o
`STORAGE_ROOT` é persistente, o `.env` recebe permissões restritivas e uploads usam
parsers reais com limites de segurança.

M07 adicionou catálogo PostgreSQL e API de tarifários com upload múltiplo, paginação, detalhe,
download verificado, metadata, ativação, versionamento append-only e soft delete. Nenhuma regra
tarifária, parser de negócio ou associação fixa com parceiro foi criada.

M08 adicionou a gestão React do catálogo com feedback por arquivo, filtros, detalhe, integridade,
linhagem e ações condicionadas por papel. O bundle de produção executa os testes frontend durante
o build e foi carregado no runtime canônico sem erros de console.

M09 adicionou a fila PostgreSQL durável, scheduler, lease/heartbeat, retry/backoff, recuperação de
crash, modo `--once`, lock transacional por fatura e endpoint manual idempotente. O tick operacional
não implementa IMAP, classificação ou qualquer regra pertencente a M10 e milestones posteriores.

M10 adicionou `EmailProvider`/`IMAPEmailProvider`, identidade UID/UIDVALIDITY, recuperação
`BODY.PEEK`, parser MIME de cabeçalhos/corpos/anexos, criação e movimento de pastas com `COPYUID`,
reconnect seguro para leituras, TLS/timeout configuráveis e contexto de thread limitado que combina
IDs, participantes e assunto, nunca assunto isolado.

M11 adicionou as tabelas de conta/mensagem/anexo, fingerprint canônico, server key independente de
pasta, preservação append-only do RFC original e anexos, locks transacionais de deduplicação e job
de ingestão. Recoleta, movimento e corridas convergem para uma única mensagem e um único conjunto
de blobs recuperáveis por hash.

## Milestones concluídos

- **M00 — Aprovação do plano e prontidão do ambiente:** concluído em 2026-08-15.
- **M01 — Estrutura executável e qualidade básica:** concluído em 2026-08-16.
- **M02 — Runtime Docker Compose e PostgreSQL:** concluído em 2026-08-16.
- **M03 — Configuração, segredos e setup multiplataforma:** concluído em 2026-08-16.
- **M04 — Persistência, migrations e transações:** concluído em 2026-08-16.
- **M05 — Autenticação, RBAC e primeiro administrador:** concluído em 2026-08-16.
- **M06 — Storage local imutável e uploads seguros:** concluído em 2026-08-16.
- **M07 — Catálogo e API de tarifários:** concluído em 2026-08-17;
  `f3c8538f7d45575557c3ef347723edccd8b8b499`.
- **M08 — Interface de gestão de tarifários:** concluído em 2026-08-17;
  `17fbdabdd0d87796fc783e6ae06e8b9888729776`.
- **M09 — Worker durável, scheduler e locks:** concluído em 2026-08-17;
  `de9f7faa1eb41778075f8312f9dcc52f48b10955`.
- **M10 — Provider IMAP, MIME e contexto de thread:** concluído em 2026-08-17;
  `7517a274c13cc8eb3afd9e1347b54d45f20e18a9`.
- **M11 — Ingestão, fingerprint e deduplicação de e-mails:** concluído em 2026-08-17;
  `b7b82f98645fabefc09648463e43f2c63f3a514c`.

## Estrutura entregue até M11

- `pyproject.toml` com Python 3.12+, dependências FastAPI/Uvicorn e grupo de desenvolvimento;
- pacote `app/` organizado pelas camadas aprovadas: API, aplicação, domínio, portas,
  cálculo, infraestrutura, relatórios e worker;
- factory e entry point FastAPI com routers de fundação e entrega segura do bundle React;
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
- volume nomeado para PostgreSQL e bind mount persistente de todo `STORAGE_ROOT` sob `data/`;
- health checks dos três serviços, endpoint `/api/health/live` e heartbeat do worker.
- `Settings` Pydantic tipado para dev/test/prod, timezone, banco e opções aprovadas;
- segredos obrigatórios como `SecretStr`, validação de força/placeholder e resumo redigido;
- `setup.ps1` e `setup.sh` idempotentes, com geração criptográfica de segredos internos,
  ACL/modo restritivos para `.env` e CA de build opcional via BuildKit secret;
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
- validação por parser de nome/extensão/MIME/conteúdo/tamanho para
  PDF/XLSX/XLS/CSV/PNG/JPEG/TIFF;
- bloqueio de traversal, conteúdo fabricado/truncado/divergente, XML perigoso, ZIP bomb,
  polyglot detectável e executáveis;
- exclusão física negada por padrão e liberada somente com motivo/referências verificadas;
- persistência comprovada após recriação real do container para seis áreas, inclusive
  `emails` e `attachments`.
- entidade/migration `tariff_files` com metadata, SHA-256, linhagem de versão e soft delete;
- porta de catálogo independente de SQLAlchemy e repository PostgreSQL com row lock de versão;
- API `/api/tariffs` com upload múltiplo, paginação/filtros, detalhe, download, PATCH,
  versionamento e DELETE lógico;
- RBAC de leitura para todos os papéis e escrita apenas para `ADMIN`/`OPERATOR`.
- cliente API frontend com propagação segura de detalhes de validação;
- workspace de tarifários responsivo com upload/progresso, filtros, detalhe, download,
  metadata, status, soft delete e histórico de versões;
- Vitest, Testing Library e jsdom integrados ao build Docker com 6 testes de componentes/cliente.
- migration `20260817_0004` e fila `processing_jobs` com chave idempotente, estados, prioridade,
  disponibilidade, tentativas, lease/heartbeat, backoff e erro explícito;
- aquisição concorrente com `FOR UPDATE SKIP LOCKED` e recuperação transacional de jobs stale;
- scheduler por janela configurável, runner contínuo e `python -m app.worker.main --once`;
- advisory lock transacional e estável por UUID de fatura;
- endpoint `POST /api/worker/run-now` protegido por origem e RBAC de escrita.
- porta de e-mail independente do protocolo e modelos imutáveis para localização, mensagem,
  anexo e contexto de thread;
- adapter IMAP com TLS implícito/STARTTLS configuráveis, timeout, reconnect de leitura,
  UID/UIDVALIDITY, `BODY.PEEK`, criação de pasta e movimento com rastreabilidade `COPYUID`;
- parser MIME para cabeçalhos, texto/HTML, charsets, anexos e bytes RFC originais;
- resolver de thread limitado por mensagens/caracteres, priorizando Message-ID/In-Reply-To/
  References e exigindo participantes quando usa assunto normalizado como fallback.
- migration/tabelas `mail_accounts`, `mail_messages` e `mail_attachments` com constraints únicas,
  metadata MIME e referências imutáveis de storage;
- server key `account + UIDVALIDITY + UID` sem pasta e fingerprint SHA-256 de JSON canônico;
- normalização Unicode, remetente/assunto/Message-ID, datas UTC/ambíguas, corpo e anexos ordenados;
- serviço/repository de ingestão com advisory locks transacionais antes da criação de blobs;
- operação de storage para originais opacos e limitados, mantendo uploads documentais sob parsing;
- job `email.ingest` com payload validado e testes de concorrência/idempotência PostgreSQL.

## Trabalho não iniciado

- M12–M26;
- OpenAI e demais integrações;
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
- commit técnico da remediação da revisão:
  `97fb4da3811983e2c6e26d8558cb9989b56a5d2b`;
- commit técnico de conclusão do M07 presente localmente e em `origin/main`:
  `f3c8538f7d45575557c3ef347723edccd8b8b499`;
- commit técnico de conclusão do M08 presente localmente e em `origin/main`:
  `17fbdabdd0d87796fc783e6ae06e8b9888729776`;
- commit técnico de conclusão do M09 presente localmente e em `origin/main`:
  `de9f7faa1eb41778075f8312f9dcc52f48b10955`;
- commit técnico de conclusão do M10 presente localmente e em `origin/main`:
  `7517a274c13cc8eb3afd9e1347b54d45f20e18a9`;
- commit técnico de conclusão do M11 presente localmente e em `origin/main`:
  `b7b82f98645fabefc09648463e43f2c63f3a514c`;
- divergência local/remoto após o push desta remediação: `0` à frente, `0` atrás;
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

- suíte completa com PostgreSQL real: **PASS**, 84 testes; 3 skips condicionais identificados
  (setup Linux e 2 testes Docker de storage); os 2 testes de storage passaram separadamente;
- regressões de revisão: **PASS** para SPA/API na origem canônica, seis áreas persistentes,
  ACL Windows, modo Linux `0600`, parsers válidos e casos adversariais;
- Ruff lint e format check: **PASS**, 88 arquivos;
- mypy estrito: **PASS**, 82 arquivos;
- frontend ESLint, TypeScript e Vite: **PASS** no stage Docker;
- Docker build sem cache com CA oficial via secret: **PASS**; nenhum bypass de TLS;
- Compose config e health: **PASS**, `app`, `worker` e `postgres` saudáveis;
- raiz `/`: **PASS**, shell React; `/api/health/live`: **PASS**;
- migration atual após M09: `20260817_0004 (head)`; `alembic check`: **PASS**, sem drift;
- aceitação M07: **PASS**, 3 testes API cobrindo sete formatos, papéis, integridade,
  paginação, versão, nomes duplicados e soft delete;
- aceitação M08: **PASS**, 6 testes frontend; ESLint, TypeScript, Vite e inspeção visual do
  bundle canônico sem erro de console;
- aceitação M09: **PASS**, 8 testes PostgreSQL cobrindo dois workers, duplicidade, retry/backoff,
  crash/recovery, heartbeat, agendamento, lock, `--once`, endpoint, origem e RBAC;
- worker `--once` na imagem final: **PASS**, saída zero e tick persistido como `SUCCEEDED`;
- scan pré-commit: **PASS**, sem `.env`, CA, segredos, dados operacionais ou artefatos.
- aceitação M10: **PASS**, 5 testes fake/mock cobrindo MIME, UID/UIDVALIDITY, anexos,
  pasta/movimento, reconnect, TLS/timeout e thread limitada;
- regressão após M10 com PostgreSQL real: **PASS**, `89 passed, 3 skipped`;
- build Docker após M10: **PASS** com a CA confiável do Windows entregue somente como secret;
  Compose com `app`, `worker` e `postgres` saudáveis.
- aceitação M11: **PASS**, vetores de fingerprint e 2 testes PostgreSQL de recoleta, movimento,
  ordem de anexos, recuperação do original e corrida por conteúdo;
- regressão final após M11: **PASS**, `95 passed, 3 skipped`; o único flake de handle Windows no
  teste de setup passou isolado e na repetição completa;
- migration `20260817_0005 (head)`, upgrade/downgrade e `alembic check`: **PASS**, sem drift;
- build Docker M11 e Compose: **PASS**, três serviços saudáveis.

## Bloqueios, riscos e findings

Não há finding CRITICAL ou HIGH aberto. Permanecem abertos REVIEW-005–008 (MEDIUM) e
REVIEW-009 (LOW); REVIEW-010 e REVIEW-011 foram corrigidos por serem seguros e diretamente
relacionados à validação da fundação. Nenhum deles bloqueou a aceitação de M07; a nova camada de
tarifários não repete a inversão de dependência registrada em REVIEW-005.

O smoke IMAP real do M10 está pendente: o host respondeu com certificado interceptado pelo Norton
emitido por `Norton Web/Mail Shield Untrusted Root`, e tanto o trust store padrão quanto o bundle
Certifi recusaram a cadeia antes da autenticação. A verificação TLS não foi desabilitada; nenhuma
mensagem ou pasta foi alterada. O contrato fake/mock obrigatório passou integralmente.

## Último commit estável

`b7b82f98645fabefc09648463e43f2c63f3a514c` — `feat: add M11 email ingestion and deduplication`

Este é o commit técnico final do M11, enviado a `origin/main`.

## Próxima ação recomendada

M12 — fundação do provider de IA e telemetria — está tecnicamente desbloqueado. Deve manter o SDK
OpenAI exclusivamente no adapter e não iniciar classificação M13.

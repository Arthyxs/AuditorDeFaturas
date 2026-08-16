# InvoiceAuditor — Estado do Projeto

**Atualizado em:** 2026-08-16
**Especificação:** v3.0, fechada para implementação
**Fase atual:** fundação executável iniciada
**Macroetapa atual:** B — Fundação executável, segura e persistente
**Milestone atual:** nenhum em execução; M01 concluído e M02 desbloqueado, ainda não iniciado

## Resumo executivo

M00 e M01 estão concluídos. O repositório agora contém o esqueleto executável final do
backend modular em Python/FastAPI e do frontend React/TypeScript/Vite, além dos gates de
teste, lint, formatação, type check e build previstos para o M01.

Nenhuma regra de negócio, persistência, migration, integração, autenticação, worker
funcional, endpoint de produto ou runtime Docker do projeto foi antecipado. Esses itens
permanecem nos milestones próprios, a partir do M02.

## Milestones concluídos

- **M00 — Aprovação do plano e prontidão do ambiente:** concluído em 2026-08-15.
- **M01 — Estrutura executável e qualidade básica:** concluído em 2026-08-16.

## Estrutura entregue no M01

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

## Trabalho não iniciado

- M02–M26;
- Dockerfile, Docker Compose e PostgreSQL do projeto;
- endpoint de liveness e processo worker executável;
- configuração operacional, banco e migrations;
- autenticação, storage, tarifários e interfaces de produto;
- IMAP, OpenAI e demais integrações;
- regras financeiras, auditoria, relatórios e golden cases.

## Estado do repositório e Git

- branch atual: `main`;
- upstream: `main` rastreia `origin/main`;
- remoto: `origin` configurado para `https://github.com/Arthyxs/AuditorDeFaturas.git`;
- commit técnico de conclusão do M01 presente localmente e em `origin/main`:
  `5609f919b967b163dd9c495a5b8c9e55779f7395`;
- divergência local/remoto após o push do M01: `0` à frente, `0` atrás;
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

### Runtime canônico validado no M00

- WSL2: distribuição padrão `docker-desktop`, versão padrão 2;
- Docker Client/Engine: 29.7.2;
- Docker Desktop: 4.86.0, contexto `desktop-linux`, Engine Linux `amd64`;
- Docker Compose: 5.3.1;
- `docker run --rm hello-world`: aprovado no M00.

Uma reinspeção dentro da sessão restrita do M01 confirmou o Docker CLI e o Compose, mas
o acesso ao daemon foi negado pelo sandbox desta sessão. Isso não afeta o M01, que não
possui build ou serviços Docker; a evidência operacional bloqueante permanece a validação
concluída no M00.

## Status de testes, build e execução

- backend smoke tests: **PASS**, 2 testes;
- Python lint (`ruff check`): **PASS**;
- Python format check (`ruff format --check`): **PASS**, 43 arquivos formatados;
- Python type check (`mypy`, modo estrito): **PASS**, 35 arquivos verificados;
- frontend lint (`eslint`): **PASS**;
- frontend TypeScript type check (`tsc -b`): **PASS**;
- frontend production build (`vite build`): **PASS**, Vite 8.2.1;
- backend em modo de desenvolvimento: **PASS**, startup completo e HTTP 200 em `/docs`;
- frontend em modo de desenvolvimento: **PASS**, startup completo e HTTP 200 na raiz;
- scan de segredos/artefatos: **PASS**, apenas placeholders `CHANGE_ME` no `.env.example`;
- artefatos locais `.venv`, caches, `node_modules` e `frontend/dist`: ignorados pelo Git;
- migrations: não aplicável ao M01; começam no M04;
- Docker build/Compose do projeto: não aplicável ao M01; começam no M02.

## Bloqueios, riscos e findings

Nenhum bloqueio técnico ou finding aberto para iniciar M02. Dependências externas futuras
continuam documentadas no plano e não afetam o M01.

`CODE_REVIEW.md` permanece sem findings. `DECISIONS.md` não foi alterado porque o M01 não
exigiu nova decisão arquitetural; mypy já era uma escolha prevista pelo plano e foi apenas
concretizado como ferramenta de qualidade.

## Último commit estável

`5609f919b967b163dd9c495a5b8c9e55779f7395` — `feat: establish executable M01 skeleton`

Este commit contém a implementação, os gates e a memória de conclusão do M01. O commit
documental subsequente registra este hash em `PROJECT_STATUS.md`.

## Próxima ação recomendada

Em uma nova sessão autorizada, iniciar somente M02 — Runtime Docker Compose e PostgreSQL.

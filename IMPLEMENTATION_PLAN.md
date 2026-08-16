# InvoiceAuditor — Plano de Implementação

**Base:** `ESPECIFICACAO_COMPLETA_AUDITOR_FATURAS_V3.md` v3.0
**Estado:** FECHADO E APROVADO — M00 e M01 concluídos; M02 desbloqueado e não iniciado
**Atualizado em:** 2026-08-16
**Regra:** este plano organiza a implementação sem reduzir a especificação e incorpora os requisitos adicionais aprovados em 2026-08-15 para auditoria manual e homologação do auditor.

## 1. Objetivo e guardrails

O produto será construído como uma aplicação de produção capaz de receber faturas por IMAP ou submissão manual autenticada, preservar os originais, selecionar tarifários, reinterpretar os arquivos originais em cada auditoria, calcular valores de forma determinística e demonstrar divergências por CT-e, AWB ou documento equivalente.

Guardrails aplicáveis a todos os milestones:

- nenhuma regra ou parser fixo por parceiro;
- nenhuma classificação baseada somente no assunto do e-mail;
- toda auditoria reinterpreta os tarifários originais selecionados;
- interpretações anteriores são apenas histórico e fonte de alertas, nunca verdade reutilizada;
- IA interpreta documentos e regras; o backend executa a aritmética autorizada;
- dinheiro usa `Decimal` no Python e `NUMERIC/DECIMAL` no PostgreSQL;
- originais, auditorias e relatórios são imutáveis e versionados;
- qualquer pendência impede a consolidação como `CORRECT`;
- Terra é o modelo padrão de auditoria e Sol somente reanálise manual, por configuração;
- OpenAI, IMAP e filesystem permanecem atrás de portas substituíveis;
- Docker Compose é o runtime canônico;
- IMAP e upload manual convergem para o mesmo pipeline depois da captura, sem duplicação de regras de negócio;
- WSL2 não é dependência do código, das imagens ou do Compose; é somente requisito do ambiente Windows atual para executar Docker Desktop;
- a qualidade do auditor é medida por documento e falso negativo é falha de severidade máxima;
- nenhum segredo ou documento operacional entra no Git.

## 2. Arquitetura final aprovada

### 2.1 Visão operacional

- **Modular monolith:** um código backend e uma imagem de aplicação, executada em dois processos independentes: `app` e `worker`.
- **Frontend:** React/TypeScript/Vite; em produção, os artefatos compilados são servidos pelo `app`. Em desenvolvimento, Vite pode executar separadamente.
- **Canais de entrada:** IMAP e auditoria manual autenticada criam uma submissão canônica. A origem é preservada, mas ambos acionam os mesmos casos de uso de criação de fatura, seleção de tarifário e auditoria.
- **Persistência:** PostgreSQL para estado transacional, índices, jobs, sessões, histórico e metadata.
- **Arquivos:** `LocalStorageProvider` em diretórios persistentes sob `data/`, com gravação atômica, SHA-256 e nomes internos; o banco guarda metadata e referências.
- **Trabalho assíncrono:** tabela durável de jobs no PostgreSQL, processada pelo `worker` com transações, `FOR UPDATE SKIP LOCKED` e/ou advisory locks. Não haverá Redis, Celery ou broker externo.
- **IA:** portas por capacidade, adapter OpenAI inicial usando Responses API, saídas estruturadas e tool calls. SDK e detalhes OpenAI ficam somente no adapter.
- **Documentos:** ferramentas genéricas para PDF, planilhas e imagens; nenhum layout ou parceiro é codificado no domínio.
- **Portabilidade:** as imagens e o Compose dependem de Docker Engine/Compose, não de WSL2. O mesmo artefato executa em Docker Desktop no Windows ou Docker Engine no Linux.

### 2.2 Fluxo de dependências

```text
IMAP → ingestão/classificação ─┐
                              ├→ Invoice intake canônico → jobs
Frontend/API → upload manual ─┘                         ↓
                                              seleção de tarifário
                                                       ↓
                              Application services / use cases
     ↓
Domain + calculation rules
     ↓ interfaces (ports)
Infrastructure adapters
     ↓
PostgreSQL / IMAP / OpenAI / filesystem
```

O domínio não importa FastAPI, SQLAlchemy, SDK da OpenAI, IMAP ou implementação de storage.

### 2.3 Estrutura aprovada do repositório

```text
auditordefaturas/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   ├── api/
│   │   ├── routes/
│   │   ├── schemas/
│   │   ├── pagination.py
│   │   └── error_handlers.py
│   ├── application/
│   │   ├── commands/
│   │   ├── queries/
│   │   ├── services/
│   │   └── orchestration/
│   ├── domain/
│   │   ├── common/
│   │   ├── intake/
│   │   ├── email/
│   │   ├── invoices/
│   │   ├── tariffs/
│   │   ├── audits/
│   │   ├── reports/
│   │   └── finance/
│   ├── ports/
│   │   ├── ai.py
│   │   ├── email.py
│   │   ├── storage.py
│   │   └── clock.py
│   ├── calculation/
│   │   ├── calculator.py
│   │   ├── expressions.py
│   │   ├── money.py
│   │   └── tolerance.py
│   ├── infrastructure/
│   │   ├── ai/
│   │   │   ├── openai_provider.py
│   │   │   ├── router.py
│   │   │   ├── schemas.py
│   │   │   ├── pricing.py
│   │   │   └── prompts/
│   │   ├── email/
│   │   ├── storage/
│   │   ├── documents/
│   │   ├── persistence/
│   │   │   ├── models/
│   │   │   ├── repositories/
│   │   │   └── session.py
│   │   ├── security/
│   │   └── observability/
│   ├── reports/
│   │   └── templates/
│   └── worker/
│       ├── main.py
│       ├── scheduler.py
│       └── jobs/
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── auth/
│   │   ├── components/
│   │   ├── features/
│   │   ├── pages/
│   │   └── routes/
│   ├── public/
│   └── package.json
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── api/
│   ├── e2e/
│   ├── fixtures/
│   └── golden_cases/
├── data/                 # ignorado pelo Git
│   ├── tariffs/
│   ├── invoices/
│   ├── reports/
│   ├── temp/
│   └── backups/
├── scripts/
├── pyproject.toml
├── docker-compose.yml
├── Dockerfile
├── README.md
├── INSTALL.md
├── ARCHITECTURE.md
├── SECURITY.md
└── CHANGELOG.md
```

### 2.4 Estratégia de dados e versionamento

- O esquema recomendado na especificação será implementado por migrations incrementais, acrescido apenas de entidades necessárias para operação segura, como sessões, jobs e preços versionados de IA.
- `invoice_submissions` será a entrada canônica, com `source_type` (`IMAP` ou `MANUAL`), ator/origem, chave idempotente e arquivos associados. A origem IMAP mantém referência ao `mail_message`; a origem manual mantém o usuário. A fatura referencia a submissão, preservando toda a rastreabilidade sem exigir e-mail fictício.
- Arquivos são append-only. “Editar” metadata não altera o blob. Uma nova versão de tarifário recebe novo registro/arquivo e vínculo de versão.
- Cada `audit_run` é imutável e possui escopo, origem e linhagem. A revisão publicada de uma fatura apresenta um conjunto completo de resultados; uma reanálise de um documento gera nova revisão completa, reaproveitando por referência/cópia auditável apenas os resultados não reanalisados.
- `report_json` é a fonte de verdade do relatório e cada revisão mantém snapshot completo, além do diff e motivo.
- Campos financeiros armazenam valor bruto e arredondado, moeda e regra de arredondamento aplicável.
- Timestamps são UTC no banco; a interface apresenta `America/Sao_Paulo` por padrão.

## 3. Decisões de produto aprovadas

Não foi encontrada contradição que torne a especificação inexequível. As quatro definições antes abertas foram aprovadas em 2026-08-15:

1. **Limiar de baixa confiança:** `EMAIL_CLASSIFICATION_MIN_CONFIDENCE` inicia em `0.80`, é configurável sem código e o valor efetivo é registrado em cada classificação.
2. **Primeiro administrador:** token único gerado por `setup`, obrigatório na tela de bootstrap e invalidado após a criação do primeiro `ADMIN`.
3. **Correção humana:** `audit_run` permanece imutável; toda correção cria revisão humana completa com autor, motivo, antes/depois e evento, tornando-se ativa somente por ação explícita.
4. **Reanálise de um documento:** toda revisão publicada é completa; resultados não reanalisados mantêm valor e linhagem explícita do run pai, sem nova chamada de IA.

Pontos condicionais já explicitados na especificação não são conflitos: suporte a XLS/TIFF, exportação PDF e CSV/XLSX serão avaliados nos milestones próprios e nunca anunciados como operacionais antes de passarem nos testes.

## 4. Macroetapas de execução

Os milestones M00–M26 continuam sendo as unidades canônicas de implementação, teste, revisão, commit e aceite. As macroetapas abaixo são apenas uma visão executiva agrupada; elas não substituem nem relaxam dependências ou critérios individuais.

### Macroetapa A — Prontidão bloqueante

**Milestones:** M00.
**Resultado:** CONCLUÍDO em 2026-08-15 — plano/ADRs aprovados, Docker Desktop e WSL2 validados no ambiente Windows atual e upstream Git operacional.

### Macroetapa B — Fundação executável, segura e persistente

**Milestones:** M01–M06.
**Resultado:** estrutura, qualidade, Docker Compose, PostgreSQL, configuração, migrations, autenticação/RBAC e storage imutável.

### Macroetapa C — Tarifários e execução durável

**Milestones:** M07–M09.
**Resultado:** catálogo/API/UI de tarifários e worker durável com idempotência, retry e locks no PostgreSQL.

### Macroetapa D — Entradas IMAP/manual e preparação de faturas

**Milestones:** M10–M15.
**Resultado:** IMAP, deduplicação, provider de IA, classificação, submissão canônica manual/IMAP, criação de fatura e seleção semântica de tarifários.

### Macroetapa E — Motor de auditoria e homologação

**Milestones:** M16–M20.
**Resultado:** ferramentas documentais, calculadora determinística, orquestração, auditoria Terra, golden cases por dificuldade, métricas de qualidade, consolidação, inconsistências e relatórios.

### Macroetapa F — Operação humana e reanálise

**Milestones:** M21–M24.
**Resultado:** frontend operacional, auditoria manual pelo frontend, revisão humana imutável, reanálise Terra/Sol, observabilidade, custos e recuperação de erros.

### Macroetapa G — Recuperabilidade e aceite de produção

**Milestones:** M25–M26.
**Resultado:** backup/restore, portabilidade Windows/Linux, hardening, documentação, CI e aceite final evidenciado.

## 5. Homologação do motor de auditoria

### 5.1 Conjunto de referência versionado

O baseline inicial terá no mínimo 16 golden cases sintéticos/licenciados, quatro por dificuldade, sob `tests/golden_cases/reference/v1/`:

```text
reference/v1/
├── simple/
├── medium/
├── difficult/
├── very_difficult/
└── manifest.json
```

Cada caso contém fatura, anexos, tarifários, origem simulada (`IMAP` e/ou `MANUAL`), `expected.json`, ground truth por documento e metadata de dificuldade/versão.

- **Simples:** documento textual legível, um tarifário, uma regra direta e dados completos.
- **Médio:** múltiplos documentos/componentes, mais de um arquivo tarifário complementar e regras de mínimo/percentual/faixa.
- **Difícil:** layouts heterogêneos, planilhas/PDFs combinados, regras territoriais, cubagem, exceções e dados parcialmente ausentes que exigem pendência correta.
- **Muito difícil:** documentos digitalizados, muitos documentos internos, tarifários complementares com regras cruzadas, ambiguidades reais, inconsistências ou conteúdo adversarial, exigindo evidência/tool calls rigorosos.

Documentos reais anonimizados poderão ampliar a homologação posteriormente em área privada ignorada pelo Git, com controle de acesso e hashes no manifesto de execução. Mesmo anonimizados, documentos oriundos da operação não serão commitados sem mudança explícita das regras do repositório.

### 5.2 Métricas obrigatórias por documento

Para a matriz de referência, “positivo” significa documento realmente `INCORRECT`:

- **Document accuracy:** documentos cujo status esperado foi reproduzido / total de documentos avaliados.
- **False positive rate:** documentos realmente `CORRECT` classificados como `INCORRECT` / total realmente `CORRECT`.
- **False negative rate:** documentos realmente `INCORRECT` classificados como `CORRECT` / total realmente `INCORRECT`.
- **Pending rate:** documentos classificados em `PENDING_*` ou `MANUAL_REVIEW` / total avaliado, reportado também somente sobre casos com ground truth conclusiva.

Resultados são publicados no agregado e separados por dificuldade, formato, origem e modelo/prompt. `ERROR` é medido separadamente e nunca convertido em pendência ou acerto.

Qualidade mínima para aceite do release:

- false negative rate igual a `0%` em todas as execuções de homologação; qualquer falso negativo é finding `CRITICAL`, bloqueia o milestone/release e tem prioridade superior a falso positivo ou pendência;
- document accuracy geral de pelo menos `95%` e `100%` nos casos simples;
- false positive rate geral de no máximo `5%`;
- pending rate sempre reportado; pending inesperado em caso conclusivo deve ser analisado, mas é menos grave que falso negativo porque não aprova cobrança incorreta;
- valores esperados, diferenças e evidências também devem atender os critérios financeiros/auditáveis da especificação, não bastando acertar o status.

Durante desenvolvimento, uma execução completa por revisão relevante é suficiente. No gate final de M26, cada caso com integração real deve ser repetido três vezes para medir estabilidade; todas as execuções entram nas métricas.

O gate de false negative rate igual a `0%` significa **zero falsos negativos observados no conjunto de homologação versionado efetivamente executado**. É um critério empírico de aceite dessa matriz e dessas execuções; não constitui garantia estatística de taxa zero sobre documentos de produção futuros, distribuições ainda não vistas ou formatos fora do conjunto avaliado. Casos de produção devem alimentar monitoramento contínuo e, quando anonimizados/permitidos, ampliar novas versões do conjunto de referência.

## 6. Regras globais de conclusão

Além do critério específico de cada milestone, sua conclusão exige, quando aplicável:

1. critérios de aceite atendidos;
2. testes relevantes, lint e type checks passando;
3. migrations validadas e reversibilidade avaliada;
4. build e serviços Docker Compose saudáveis;
5. ausência de segredos e documentos privados no diff/staging;
6. atualização de `PROJECT_STATUS.md` e deste plano;
7. atualização de `DECISIONS.md` e `CODE_REVIEW.md` quando aplicável;
8. commit claro, push no remoto configurado e hash registrado em `PROJECT_STATUS.md`.

## 7. Milestones

### M00 — Aprovação do plano e prontidão do ambiente

**Status:** COMPLETED — concluído em 2026-08-15; evidências registradas em `PROJECT_STATUS.md`.

**Objetivo:** remover impedimentos de infraestrutura antes de iniciar código.

**Funcionalidades:** nenhuma funcionalidade de produto; registrar a aprovação do plano, instalar/ativar Docker Desktop com backend WSL2 neste computador e validar o acesso/upstream Git. WSL2 permanece requisito somente deste ambiente Windows, não do produto.

**Principais componentes:** Windows, WSL2, Docker Desktop, Docker Compose, Git/GitHub.

**Dependências:** satisfeitas — aprovação do usuário, instalação administrativa concluída e acesso ao repositório remoto validado.

**Testes necessários:** `wsl --status`; `docker version`; `docker compose version`; `docker run --rm hello-world`; `git fetch origin`; verificação do upstream; `git push --dry-run origin main`.

**Critério objetivo de conclusão:** plano/ADRs aprovados; WSL2 e Docker Desktop respondem neste computador; Engine, Compose e `hello-world` passam; `main` rastreia `origin/main`; fetch e push dry-run autenticam; `PROJECT_STATUS.md` registra versões e resultados. Somente então M01 é desbloqueado.

### M01 — Estrutura executável e qualidade básica

**Status:** COMPLETED — concluído em 2026-08-16; M02 desbloqueado.

**Objetivo:** criar a estrutura final sem implementar regras de negócio.

**Funcionalidades:** pacote Python, FastAPI mínimo, frontend Vite mínimo, suíte de testes vazia porém executável, lint, format e type check.

**Principais componentes:** `pyproject.toml`, `app/`, `frontend/`, `tests/`, Ruff, mypy/pyright conforme escolha documentada, pytest, ESLint e TypeScript.

**Dependências:** M00.

**Testes necessários:** import do pacote; teste unitário de smoke; build TypeScript; lint e type check dos dois projetos.

**Critério objetivo de conclusão:** backend e frontend iniciam em modo de desenvolvimento; todos os gates configurados passam; não há funcionalidade simulada apresentada como pronta.

**Evidências de conclusão:** pacote Python 3.12+ e aplicação FastAPI mínima importáveis; estrutura de camadas aprovada criada sem implementações futuras simuladas; `pytest` com 2 testes de smoke aprovados; Ruff lint aprovado; Ruff format check aprovado em 43 arquivos; mypy estrito aprovado em 35 arquivos; frontend React/TypeScript/Vite com ESLint aprovado; TypeScript type check aprovado; build Vite 8.2.1 aprovado; backend Uvicorn em modo de desenvolvimento respondeu HTTP 200 em `/docs`; frontend Vite em modo de desenvolvimento respondeu HTTP 200 na raiz; revisão de segredos e artefatos confirmou somente placeholders `CHANGE_ME` no `.env.example` e diretórios gerados corretamente ignorados pelo Git.

### M02 — Runtime Docker Compose e PostgreSQL

**Objetivo:** estabelecer o runtime canônico e portável.

**Funcionalidades:** imagem compartilhada para `app`/`worker`, serviço PostgreSQL, volumes persistentes, health checks e endpoint básico de liveness.

**Principais componentes:** `Dockerfile`, `docker-compose.yml`, `.dockerignore`, entrypoints, PostgreSQL.

**Dependências:** M01.

**Testes necessários:** build limpo; `docker compose up`; health dos três serviços; reinício sem perda do volume PostgreSQL; execução em paths Windows.

**Critério objetivo de conclusão:** Compose sobe `app`, `worker` e `postgres` saudáveis e os dados de smoke sobrevivem à recriação dos containers.

### M03 — Configuração, segredos e setup multiplataforma

**Objetivo:** centralizar configuração validada e automatizar instalação segura.

**Funcionalidades:** settings tipados; validação de segredos; geração de `APP_SECRET_KEY`/senha PostgreSQL; criação de diretórios; scripts Windows e Linux; ambientes dev/test/prod. O script Windows chama Docker/Compose nativos e não expõe WSL2 como dependência da aplicação.

**Principais componentes:** `app/config.py`, `.env.example`, `scripts/setup.ps1`, `scripts/setup.sh`.

**Dependências:** M02.

**Testes necessários:** configurações válidas/inválidas; segredos ausentes; idempotência dos scripts; paths com espaços; garantia de que valores secretos não aparecem em logs.

**Critério objetivo de conclusão:** uma instalação limpa exige somente os dados externos previstos, gera os segredos internos e inicia o Compose sem edição manual adicional.

### M04 — Persistência, migrations e transações

**Objetivo:** criar a fundação consistente do modelo de dados.

**Funcionalidades:** sessão SQLAlchemy 2; Alembic; tipos/enums compartilhados; convenções de IDs, UTC, JSONB e `NUMERIC`; repositories e unit of work.

**Principais componentes:** `app/infrastructure/persistence`, `migrations/`, modelos base e fixtures de banco.

**Dependências:** M02 e M03.

**Testes necessários:** upgrade em banco vazio; upgrade a partir da revisão anterior; constraints e transações; rollback; precisão de `NUMERIC`; timestamps UTC.

**Critério objetivo de conclusão:** migrations criam o esquema-base em PostgreSQL real, testes de transação passam e nenhum valor monetário usa float.

### M05 — Autenticação, RBAC e primeiro administrador

**Objetivo:** proteger o produto desde o primeiro acesso.

**Funcionalidades:** usuários `ADMIN`/`OPERATOR`/`VIEWER`; hash Argon2id; sessão server-side; cookie HTTPOnly/SameSite; logout; bootstrap único do primeiro admin; autorização de rotas.

**Principais componentes:** modelos `users`/`sessions`, segurança backend, telas de login/bootstrap e middleware de autorização.

**Dependências:** M03 e M04.

**Testes necessários:** hash/verificação; expiração e revogação; CSRF conforme estratégia; matriz RBAC; bootstrap concorrente; impossibilidade de criar segundo admin pelo fluxo inicial.

**Critério objetivo de conclusão:** primeiro admin é criado uma única vez de forma protegida; cada papel acessa somente ações permitidas; testes de segurança e sessão passam.

### M06 — Storage local imutável e uploads seguros

**Objetivo:** preservar arquivos com integridade e segurança.

**Funcionalidades:** porta `StorageProvider`; adapter local; gravação atômica; SHA-256; nomes internos; leitura/metadata; exclusão controlada; validação MIME/extensão/tamanho/path traversal.

**Principais componentes:** `app/ports/storage.py`, `app/infrastructure/storage`, validação de uploads e diretórios `data/`.

**Dependências:** M03 e M04.

**Testes necessários:** gravação/leitura/hash; colisão; arquivo truncado; path traversal; MIME divergente; tamanho excedido; reinício do container; negação de execução.

**Critério objetivo de conclusão:** arquivos aceitos permanecem íntegros após recriação dos containers e uploads maliciosos dos casos de teste são rejeitados sem sair da raiz configurada.

### M07 — Catálogo e API de tarifários

**Objetivo:** tornar tarifários originais gerenciáveis e rastreáveis.

**Funcionalidades:** upload múltiplo; lista paginada; detalhe; download; descrição/observação; ativar/desativar; versão; soft delete; bloqueio de exclusão física quando referenciado.

**Principais componentes:** domínio/repository de tarifários, `tariff_files`, rotas `/api/tariffs` e storage.

**Dependências:** M05 e M06.

**Testes necessários:** API por papel; upload de todos os formatos declarados tecnicamente suportados; hash; paginação; soft delete; arquivo referenciado; nomes duplicados.

**Critério objetivo de conclusão:** a API mínima de tarifários funciona com persistência, autorização e integridade; nenhum update sobrescreve o blob original.

### M08 — Interface de gestão de tarifários

**Objetivo:** entregar gestão de tarifários pelo frontend.

**Funcionalidades:** upload múltiplo com progresso/erro; listagem; filtros; detalhe; download; descrição; ativação; soft delete; hash e histórico de uso quando disponível.

**Principais componentes:** frontend `features/tariffs`, cliente API, componentes de upload e permissões.

**Dependências:** M07.

**Testes necessários:** componentes; fluxo e2e de upload/edição/download/desativação; erros de validação; permissões `VIEWER`.

**Critério objetivo de conclusão:** um `ADMIN`/`OPERATOR` gerencia tarifários pela interface e um `VIEWER` não executa ações de escrita.

### M09 — Worker durável, scheduler e locks

**Objetivo:** executar tarefas idempotentes e recuperáveis sem broker externo.

**Funcionalidades:** fila PostgreSQL; estados/tentativas; backoff; erro explícito; heartbeat; modo contínuo; `--once`; agendamento; lock por fatura; endpoint “Processar agora”.

**Principais componentes:** `processing_jobs`, `app/worker`, scheduler, repositories de job e advisory locks.

**Dependências:** M04.

**Testes necessários:** concorrência com dois workers; retry; crash/recovery; job duplicado; lock; modo único; polling configurável.

**Critério objetivo de conclusão:** dois workers não processam a mesma chave idempotente simultaneamente e um job interrompido pode ser retomado ou falhar explicitamente sem simular sucesso.

### M10 — Provider IMAP, MIME e contexto de thread

**Objetivo:** encapsular acesso a e-mail sem acoplar o domínio a IMAP.

**Funcionalidades:** listar/obter mensagens; UID/UIDVALIDITY; cabeçalhos; corpo texto/HTML; anexos; criação/movimentação de pastas; contexto limitado de thread.

**Principais componentes:** `EmailProvider`, `IMAPEmailProvider`, parser MIME, resolver de thread e modelos de transporte.

**Dependências:** M03 e M06.

**Testes necessários:** servidor IMAP fake/mock; mensagens multipart, encodings e anexos; Message-ID/References; pasta ausente; reconnect; TLS; timeout; limite de histórico.

**Critério objetivo de conclusão:** o contract test do provider recupera e move mensagens representativas sem perder anexos/cabeçalhos e sem depender do assunto.

### M11 — Ingestão, fingerprint e deduplicação de e-mails

**Objetivo:** persistir originais exatamente uma vez.

**Funcionalidades:** `mail_accounts`, `mail_messages`, `mail_attachments`; server key; fingerprint canônico; normalização; armazenamento do e-mail bruto e anexos; idempotência após movimento.

**Principais componentes:** domínio de e-mail, repositories, storage, job de ingestão e constraints únicas.

**Dependências:** M09 e M10.

**Testes necessários:** vetores unitários de fingerprint; duplicação por UID; duplicação por conteúdo após mover; Message-ID ausente; anexos em ordem diferente; corrida de ingestão.

**Critério objetivo de conclusão:** repetir a coleta ou mover a mensagem não duplica mensagem, anexo ou blob, e o original continua recuperável pelo hash.

### M12 — Fundação do provider de IA e telemetria

**Objetivo:** integrar IA de forma substituível, observável e validada.

**Funcionalidades:** portas por tarefa; router por provider/modelo; `OpenAIProvider`; Responses API; Structured Outputs; tool loop controlado; prompts versionados; `ai_calls`; preços por vigência; teste de provider.

**Principais componentes:** `app/ports/ai.py`, `app/infrastructure/ai`, schemas Pydantic, prompts, `ai_calls` e `ai_price_versions`.

**Dependências:** M03, M04 e M09.

**Testes necessários:** adapter com transporte mock; schema inválido; timeout/rate limit; contabilização de tokens/cache/custo; ausência de API key; isolamento do SDK; contrato com provider fake.

**Critério objetivo de conclusão:** uma chamada estruturada de teste registra provider, modelo, prompt/hash, latência, tokens e status; nenhuma camada fora do adapter importa o SDK OpenAI.

### M13 — Classificação, revisão e movimentação de e-mails

**Objetivo:** classificar mensagens com Luna e movê-las de forma segura.

**Funcionalidades:** classes `INVOICE`, `DUE_NOTICE`, `GENERAL`, `MANUAL_REVIEW`; evidências; parceiro provável; anexos relevantes; `EMAIL_CLASSIFICATION_MIN_CONFIDENCE=0.80` por padrão e configurável; movimento idempotente; erros/retry.

**Principais componentes:** prompt/classification schema, serviço de classificação, jobs, estados de e-mail e UI/API mínima de revisão.

**Dependências:** M11 e M12.

**Testes necessários:** fixtures com assunto enganoso e threads; valores abaixo/em/acima de `0.80`; mudança de configuração; registro do limiar efetivo; saída inválida; falha ao mover; repetição após movimento; nenhuma exclusão local.

**Critério objetivo de conclusão:** conjunto de classificação aceito roteia corretamente e toda baixa confiança vai para revisão; falha IMAP aparece como erro recuperável sem perder o original.

### M14 — Entrada canônica, auditoria manual e criação de fatura

**Objetivo:** transformar uma entrada IMAP ou manual em agregado persistente e acionar o mesmo pipeline sem inventar dados nem duplicar lógica.

**Funcionalidades:** `invoice_submissions` com origem `IMAP`/`MANUAL`; parceiros históricos; fatura; vínculos com originais; schemas canônicos de documento/componentes; campos nulos; estados iniciais; chave idempotente/hash; `POST /api/invoices/manual` multipart para `ADMIN`/`OPERATOR`, com fatura, anexos auxiliares e metadata/nota opcionais; `VIEWER` somente leitura. O caminho manual ignora classificação/movimentação de e-mail e enfileira exatamente os mesmos casos de uso de criação, seleção de tarifário e auditoria usados após um e-mail `INVOICE`.

**Principais componentes:** `invoice_submissions`, `submission_files`, serviço `InvoiceIntake`, rota manual, `partners`, `invoices`, `invoice_documents`, `document_charge_items` e schemas de origem/evidência.

**Grafo de dependências internas:**

```text
M05 auth ─────┐
M06 storage ──┼→ InvoiceIntake + entrada MANUAL
M09 jobs ─────┘

M11 ingestão de e-mail ─┐
M13 classificação ──────┴→ adapter de entrada IMAP → InvoiceIntake
```

**Dependências:** o núcleo `InvoiceIntake` e a entrada `MANUAL` dependem somente de M05, M06 e M09. A entrada `IMAP` depende adicionalmente de M11 e M13. M14 conserva sua posição atual depois de M13 para rastreabilidade do plano, mas a capacidade manual não possui dependência técnica da conclusão da classificação IMAP.

**Testes necessários:** RBAC do endpoint; upload multipart seguro; idempotência por chave/hash; parceiro conhecido/desconhecido; campos ausentes; moedas/decimais; centenas de documentos sintéticos; constraint de origem; comparação provando que submissões IMAP e manual equivalentes geram o mesmo comando/job downstream sem duplicação de serviço.

**Critério objetivo de conclusão:** uma mensagem `INVOICE` ou submissão manual autorizada produz exatamente uma fatura rastreável; originais e ator/origem permanecem identificáveis; campos desconhecidos ficam nulos; ambos os canais entram no mesmo pipeline a partir de `InvoiceIntake`.

### M15 — Seleção semântica de tarifários

**Objetivo:** selecionar somente os candidatos prováveis antes da auditoria.

**Funcionalidades:** catálogo ativo; metadata contextual; seletor Terra configurável; seleção múltipla; confiança/motivo; vínculo dos arquivos selecionados; `PENDING_NO_TARIFF` em nível de fatura.

**Principais componentes:** prompt/schema de seleção, serviço de catálogo, `pending_items`, job de seleção.

**Dependências:** M07, M12 e M14.

**Testes necessários:** zero/um/múltiplos candidatos; tarifário inativo; saída com ID inexistente; baixa confiança; repetição; garantia de que arquivos não escolhidos não entram na auditoria; resultados equivalentes para submissão IMAP e manual com os mesmos documentos.

**Critério objetivo de conclusão:** seleção válida persiste exatamente os arquivos escolhidos; nenhum candidato cria fatura `PENDING` e pendência explícita, nunca `CORRECT`.

### M16 — Ferramentas genéricas de PDF, planilha e imagem

**Objetivo:** oferecer acesso auditável e econômico aos documentos sem layouts hardcoded.

**Funcionalidades:** listar/extrair/pesquisar/renderizar PDF; listar abas/dimensões/intervalos/células/fórmulas; metadata e preview de imagens; referências de página/aba/range; detecção de formato não suportado.

**Principais componentes:** `app/infrastructure/documents`, schemas de tool calls e evidências, PyMuPDF, openpyxl/CSV e biblioteca XLS escolhida após teste.

**Dependências:** M06 e M12.

**Testes necessários:** PDFs textuais/digitalizados; XLSX com fórmulas; CSV com encodings/separadores; imagens; arquivos corrompidos; limites de página/range; XLS/TIFF em spike de viabilidade.

**Critério objetivo de conclusão:** ferramentas retornam conteúdo e coordenadas reproduzíveis para fixtures suportadas, limitam leituras excessivas e retornam `DOCUMENT_UNSUPPORTED`/erro explícito nos casos não suportados.

### M17 — Calculadora determinística e regras financeiras comuns

**Objetivo:** executar aritmética solicitada pela IA com segurança e precisão.

**Funcionalidades:** DSL declarativa allowlist; soma/subtração/multiplicação/divisão/max/min/percentual/round/ceil/floor/comparação; tolerância absoluta/percentual; consolidação; margem bruta.

**Principais componentes:** `app/calculation`, domínio financeiro, trace estruturado e regras de arredondamento.

**Dependências:** M04.

**Testes necessários:** propriedades e casos de borda com `Decimal`; divisão por zero; escala; arredondamento; expressão proibida; tolerâncias combinadas; receita zero/ausente; consolidação de estados.

**Critério objetivo de conclusão:** todos os vetores financeiros retornam resultado e trace determinísticos; código e banco não usam float para dinheiro; nenhuma expressão arbitrária é executada.

### M18 — Modelo e orquestração de auditoria com provider fake

**Objetivo:** implementar o ciclo de auditoria independentemente do fornecedor de IA.

**Funcionalidades:** `audit_runs`, resultados por documento, interpretações, pendências, evidências, ambiguidades, cálculos, seleção de originais, transações e estados de erro.

**Principais componentes:** domínio/aplicação de auditoria, repositories, migrations, provider fake e fixtures.

**Dependências:** M14, M15, M16 e M17.

**Testes necessários:** auditoria correta/incorreta/pendente/erro; entrada IMAP e manual pelo mesmo orquestrador; centenas de documentos; rollback parcial; retry; lock por fatura; obrigatoriedade dos campos de `INCORRECT`; originais selecionados em cada run.

**Critério objetivo de conclusão:** com provider fake, uma auditoria completa persiste todos os resultados e evidências, consolida corretamente e rejeita qualquer `INCORRECT` sem os dados obrigatórios.

### M19 — Auditoria Terra funcional e golden cases

**Objetivo:** executar o Objetivo 001 com o adapter OpenAI real.

**Funcionalidades:** prompt de auditoria; interpretação do zero; identificação de CT-e/AWB/equivalente; tool calls documentais e de cálculo; resultados estruturados; falhas/pendências explícitas; rastreamento de custo.

**Principais componentes:** OpenAI audit adapter, prompt versionado, orchestration loop, baseline `reference/v1` com no mínimo 16 golden cases em quatro dificuldades, executor de métricas e contract tests com credencial.

**Dependências:** M12 e M18; chave/API e acesso aos modelos para teste ao vivo.

**Testes necessários:** quatro ou mais casos simples, médios, difíceis e muito difíceis; entradas IMAP/manual; PDF/planilha/imagem; ausência de dado; regra ambígua; múltiplos tarifários; divergência por componente; prompt injection em documento; resposta truncada; cálculo de document accuracy, false positive rate, false negative rate e pending rate; teste real controlado Terra.

**Critério objetivo de conclusão:** o baseline versionado executado cumpre os gates da seção 5.2, incluindo zero falso negativo observado nessa matriz; todos os casos aprovados demonstram documento, cobrado, esperado, diferença, regra, tarifário, evidência, entradas e cálculo; cada run fornece novamente os originais e nunca usa interpretação histórica como entrada autoritativa.

### M20 — Consolidação, inconsistências e relatórios imutáveis

**Objetivo:** gerar visão completa, rastreável e comparável da auditoria.

**Funcionalidades:** validação dos totais; consolidação de status; comparação estruturada de interpretações; alertas sem decisão automática; `report_json`; HTML/print; snapshots e histórico.

**Principais componentes:** `interpretation_inconsistencies`, `reports`, `report_revisions`, builders/templates.

**Dependências:** M18 e M19.

**Testes necessários:** combinações de status; totais não reconciliados; interpretações divergentes; determinismo do relatório; escaping HTML; preservação de revisões; margem agregada.

**Critério objetivo de conclusão:** relatório JSON/HTML reproduz a auditoria por documento e fatura, alerta totais/inconsistências e nenhuma revisão anterior é alterada.

### M21 — Frontend operacional de auditoria

**Objetivo:** permitir que o operador use e compreenda o resultado ponta a ponta.

**Funcionalidades:** dashboard; faturas paginadas/filtradas; detalhe e tabs; lista/detalhe de documentos; evidência/cálculo/margem; pendências; histórico global; arquivos e custos; tela “Auditoria manual” para `ADMIN`/`OPERATOR` enviar fatura/anexos, acompanhar a submissão e abrir a auditoria resultante.

**Principais componentes:** APIs de dashboard/faturas/documentos/pendências/auditorias/submissão manual e features React correspondentes.

**Dependências:** M05, M20 e M08.

**Testes necessários:** APIs paginadas/filtros; componentes de valores/status; e2e de upload manual até resultado usando provider fake; equivalência com pipeline IMAP; dados ausentes; centenas de documentos; RBAC; acessibilidade e responsividade básica.

**Critério objetivo de conclusão:** um operador consegue enviar manualmente uma fatura, acompanhar o mesmo pipeline de seleção/auditoria do IMAP, localizar o resultado e responder às nove perguntas financeiras da especificação usando somente a interface e suas evidências.

### M22 — Revisão humana e trilha de auditoria

**Objetivo:** permitir correção e decisão humana sem destruir a saída da IA.

**Funcionalidades:** comentar; marcar revisado; aceitar/rejeitar; corrigir campos permitidos; resolver/dismiss pendências e inconsistências; revisão completa; `audit_events`.

**Principais componentes:** modelo de revisão humana, APIs/UI de edição e comparação, trilha append-only.

**Dependências:** M20 e M21.

**Testes necessários:** autorização; before/after; motivo obrigatório; concorrência otimista; revisão anterior intacta; eventos para toda ação; rejeição de edição de originais.

**Critério objetivo de conclusão:** toda ação humana é atribuída, datada e reversível por nova revisão; nenhum `audit_run`, arquivo ou relatório anterior é sobrescrito.

### M23 — Reanálise manual Terra/Sol e comparação

**Objetivo:** permitir segunda análise controlada em fatura inteira ou documento.

**Funcionalidades:** solicitação com nota; Terra ou Sol explícito; escopo total/parcial; novo run/revisão; linhagem; visão lado a lado; retry; ausência de fallback automático.

**Principais componentes:** `reanalysis_requests`, parent/scope de runs, jobs, APIs/UI e comparador.

**Dependências:** M19, M20 e M21.

**Testes necessários:** reanálise total/parcial; demais documentos preservados com origem; Terra/Sol configurados; comparação dos campos obrigatórios; falha de provider; garantia de zero fallback automático.

**Critério objetivo de conclusão:** o operador reanalisa uma fatura ou documento com o modelo escolhido, obtém revisão completa comparável e todas as versões anteriores permanecem acessíveis.

### M24 — Operação, observabilidade, custos e recuperação de erros

**Objetivo:** tornar o sistema diagnosticável e operável pelo frontend.

**Funcionalidades:** logs estruturados/redigidos; correlação por IDs; health liveness/readiness/dependencies; status de IMAP/IA/storage/worker; retry explícito; custo por modelo/período; tela de configurações sem segredos.

**Principais componentes:** observabilidade, `/api/health`, `/api/settings/status`, APIs de retry, dashboards operacionais.

**Dependências:** M09, M12, M13 e M21.

**Testes necessários:** dependência degradada; segredo em payload/log; health sem credencial; retry autorizado; cálculo com mudança de preço vigente; latência e correlação.

**Critério objetivo de conclusão:** falhas previstas aparecem com estado correto e ação segura de retry; health identifica cada dependência; logs e frontend não expõem segredos.

### M25 — Backup, restore, retenção e migração Windows/Linux

**Objetivo:** provar recuperabilidade do banco e dos originais.

**Funcionalidades:** dump diário; backup de tariffs/invoices/reports; manifesto/hash; retenção; restore; migração local para servidor; proteção contra limpeza de originais.

**Principais componentes:** scripts de backup/restore, job agendado, `data/backups`, documentação operacional.

**Dependências:** M09, M20 e M24.

**Testes necessários:** backup/restore em ambiente descartável; corrupção de arquivo; retenção sem apagar originais; paths Windows/Linux; execução do mesmo Compose em Docker Desktop e Docker Engine sem comando/path WSL específico; banco mais arquivos consistentes; smoke após restore.

**Critério objetivo de conclusão:** um ambiente vazio é restaurado de backup testado e recupera hashes, auditorias, relatórios e arquivos originais com smoke test aprovado.

### M26 — Hardening, documentação e aceite final

**Objetivo:** validar a especificação completa como produto instalável.

**Funcionalidades:** README/INSTALL/ARCHITECTURE/SECURITY/CHANGELOG; CI; instalação limpa Windows/Linux; exportação HTML/print e PDF se validada; avaliação final XLS/TIFF e CSV/XLSX; revisão de segurança e performance.

**Principais componentes:** documentação, GitHub Actions, scripts de smoke, matriz de requisitos e `CODE_REVIEW.md`.

**Dependências:** M00–M25.

**Testes necessários:** suíte completa; lint/types; Docker build; Compose; migrations; e2e incluindo auditoria manual; golden cases repetidos três vezes; métricas por dificuldade/origem/formato/modelo; restore; instalação limpa; segurança de upload/auth/logs; carga representativa de ~100 faturas/mês.

**Critério objetivo de conclusão:** os 24 critérios de aceite da seção 63, os 14 passos do critério de sucesso da seção 88 e o fluxo adicional de auditoria manual têm evidência de teste/documentação; nenhum falso negativo é observado no conjunto versionado durante o gate repetido; não há finding crítico/alto aberto; commit final está no remoto e registrado. Esse resultado não é declarado como garantia estatística sobre dados de produção não vistos.

## 8. Dependências externas e stop conditions

Os milestones afetados devem parar e registrar o bloqueio, sem simular sucesso, quando faltarem:

- Docker Engine/Compose para validar o runtime canônico; no computador Windows atual, isso exige Docker Desktop com backend WSL2 operacional;
- credenciais IMAP para teste real além do provider fake;
- API key e acesso da conta aos modelos configurados para contract test real;
- exemplos sintéticos/licenciados dos formatos necessários aos golden cases.

Mocks são válidos para testes de contrato e falhas; não contam como prova de que a integração real está operacional.

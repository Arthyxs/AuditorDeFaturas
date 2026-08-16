# InvoiceAuditor — Decisões Arquiteturais

**Estado do documento:** decisões aceitas
**Atualizado em:** 2026-08-16

Somente decisões arquiteturais relevantes são registradas aqui. A arquitetura geral e as decisões abaixo foram aprovadas pelo usuário em 2026-08-15. A especificação v3.0 permanece autoridade superior, acrescida dos requisitos explicitamente aprovados para auditoria manual e homologação.

## ADR-001 — Modular monolith com processos app e worker

**Status:** ACCEPTED
**Contexto:** o volume inicial é de aproximadamente 100 faturas/mês; a especificação exige app, worker e PostgreSQL, e veda complexidade distribuída sem necessidade.

**Decisão:** manter um único codebase backend e uma única imagem, executada como processo web `app` e processo assíncrono `worker`, mais PostgreSQL no Docker Compose. Não adotar microserviços, Redis, Celery ou broker externo.

**Consequências:** implantação e transações permanecem simples; app e worker compartilham contratos e adapters; cada processo escala separadamente no Compose se necessário.

## ADR-002 — Camadas de domínio, aplicação, portas e adapters

**Status:** ACCEPTED
**Contexto:** IA, e-mail e storage devem ser substituíveis, e o domínio não pode depender de SDKs/infraestrutura.

**Decisão:** organizar dependências em `domain` → `application` → `ports`, com implementações em `infrastructure`. FastAPI e worker chamam casos de uso; SQLAlchemy, IMAP, OpenAI e filesystem ficam nos adapters.

**Consequências:** providers podem mudar sem reescrever o domínio; exige contract tests das portas e disciplina para impedir imports invertidos.

## ADR-003 — Jobs duráveis e concorrência no PostgreSQL

**Status:** ACCEPTED
**Contexto:** polling, classificação, auditoria, retry e backup precisam sobreviver a reinícios e não podem processar a mesma fatura simultaneamente.

**Decisão:** usar tabela de jobs no PostgreSQL com chave idempotente, estados, tentativas e agendamento. Aquisição usa transação com `FOR UPDATE SKIP LOCKED`; faturas usam advisory lock ou lock transacional por ID.

**Consequências:** não há dependência de fila externa; a operação é adequada ao volume inicial; queries, índices e recuperação de jobs abandonados precisam de testes de concorrência.

## ADR-004 — Originais em storage append-only com integridade no banco

**Status:** ACCEPTED
**Contexto:** e-mails, anexos, tarifários e relatórios devem ser imutáveis, persistentes e migráveis entre Windows e Linux.

**Decisão:** `LocalStorageProvider` grava blobs atomicamente em `data/` com nome interno, SHA-256, tamanho e metadata no PostgreSQL. Alterações criam nova versão; soft delete altera visibilidade, não remove o blob referenciado. Exclusão física exige fluxo administrativo explícito e bloqueio de referências.

**Consequências:** integridade e rastreabilidade são verificáveis; backup precisa manter consistência entre banco e filesystem; cresce o uso de disco, administrado por retenção apenas de temporários/backups, nunca de originais.

## ADR-005 — PostgreSQL e Decimal como autoridade financeira

**Status:** ACCEPTED
**Contexto:** a auditoria financeira exige precisão, tolerância e reprodutibilidade.

**Decisão:** usar `Decimal` no backend e `NUMERIC/DECIMAL` no PostgreSQL. Valores monetários atravessam APIs como strings decimais. A calculadora aceita somente uma DSL declarativa com operações permitidas e gera trace; `eval` é proibido.

**Consequências:** resultados são determinísticos; schemas e serializers precisam rejeitar float para campos monetários; arredondamento e escala devem ser explícitos e testados.

## ADR-006 — Responses API, saídas estruturadas e modelos configuráveis

**Status:** ACCEPTED
**Contexto:** a implementação inicial exige OpenAI, visão, ferramentas, respostas estruturadas, Luna/Terra/Sol e substituição futura do provider.

**Decisão:** o adapter OpenAI usará Responses API, Structured Outputs e tool calls controladas. IDs de provider/modelo e reasoning effort ficam em configuração. Luna classifica; Terra seleciona/audita; Terra ou Sol somente por reanálise manual explícita. Não existe fallback automático Terra → Sol.

**Consequências:** o domínio recebe schemas próprios e não conhece o SDK; prompts são versionados por nome/hash; cada chamada registra modelo/tokens/custo; disponibilidade na conta precisa de teste real com credencial.

## ADR-007 — Cada auditoria reinterpreta os originais

**Status:** ACCEPTED
**Contexto:** a regra central da especificação proíbe tratar interpretação anterior como verdade.

**Decisão:** o input semântico de cada `audit_run` inclui novamente a fatura, contexto e arquivos tarifários originais selecionados. Interpretações antigas nunca alimentam o cálculo como regra. Elas são consultadas somente depois do novo resultado para comparação e alertas. Caching técnico do provider é permitido sem omitir o original do contexto.

**Consequências:** maior custo variável, compensado por seleção prévia e ferramentas de leitura; auditabilidade e independência entre runs são preservadas; testes devem provar a presença dos originais em cada execução.

## ADR-008 — Revisões completas, imutáveis e com linhagem

**Status:** ACCEPTED
**Contexto:** relatórios são editáveis, auditorias reanalisáveis e uma reanálise pode afetar apenas um documento, mas nenhuma versão pode ser apagada.

**Decisão:** `audit_run` e seus resultados são imutáveis. Cada revisão publicada fornece uma visão completa da fatura e aponta para o run/revisão pai. Em reanálise parcial, o documento escolhido recebe novo resultado e os demais mantêm valor e linhagem explícita do pai, sem nova chamada de IA. Correção humana cria revisão separada com snapshot, diff, autor e motivo.

**Consequências:** qualquer revisão pode ser reconstruída e comparada; o modelo de dados precisa de `parent_run_id`, escopo/origem e referência de proveniência; há duplicação controlada de snapshots ou referências para favorecer leitura consistente.

## ADR-009 — Sessões server-side e bootstrap por token único

**Status:** ACCEPTED
**Contexto:** o primeiro acesso deve criar admin, e a aplicação local/VPS precisa de autenticação simples sem expor tokens ao JavaScript.

**Decisão:** autenticar por sessão opaca armazenada no PostgreSQL e cookie HTTPOnly, Secure em HTTPS e SameSite Strict. Somente o SHA-256 do token de sessão é persistido e mutações autenticadas exigem origem exatamente igual a `APP_BASE_URL`. O setup gera um token de bootstrap de uso único para criar o primeiro `ADMIN`; um advisory lock transacional serializa tentativas concorrentes e, após existir um `ADMIN`, o endpoint fecha permanentemente para esse fluxo.

**Consequências:** revogação e RBAC são simples; exige tabela/limpeza de sessões, proteção CSRF e configuração correta de proxy/HTTPS; evita JWT persistido no browser.

## ADR-010 — Frontend SPA compilado e servido pelo app em produção

**Status:** ACCEPTED
**Contexto:** a especificação pede React/Vite e três serviços canônicos (`app`, `worker`, `postgres`), sem exigir container frontend separado.

**Decisão:** desenvolver o frontend com Vite separado, mas incluir o build estático na imagem final e servi-lo pelo FastAPI/reverse static handler no processo `app`.

**Consequências:** uma única origem simplifica cookies, instalação e Compose; o build Docker torna-se multi-stage; em desenvolvimento continuam disponíveis hot reload e execução separada.

## ADR-011 — Ferramentas documentais genéricas e evidência reproduzível

**Status:** ACCEPTED
**Contexto:** formatos e layouts variam, parsers por parceiro são proibidos e cada conclusão precisa apontar evidência.

**Decisão:** expor ferramentas genéricas de leitura limitada para PDF, planilha e imagem, com resposta estruturada e coordenadas de página/aba/range. A IA escolhe como usá-las; o backend valida limites e nunca executa uploads. PDFs digitalizados usam visão no release inicial, não OCR local obrigatório.

**Consequências:** novos parceiros não exigem código; formatos não suportados falham explicitamente; fixtures precisam validar que referências retornadas são reproduzíveis.

## ADR-012 — UTC no banco e timezone somente na apresentação

**Status:** ACCEPTED
**Contexto:** e-mails misturam datas de cabeçalho/servidor e a aplicação deve operar no Windows e Linux com apresentação em São Paulo.

**Decisão:** persistir instantes com timezone em UTC; preservar separadamente datas originais e origem; converter para `APP_TIMEZONE`, inicialmente `America/Sao_Paulo`, apenas nas bordas de apresentação/exportação.

**Consequências:** ordenação e deduplicação ficam consistentes; conversões e horário de verão histórico precisam de testes; datas sem timezone permanecem marcadas como ambíguas em vez de inventadas.

## ADR-013 — Relatório JSON versionado como fonte de verdade

**Status:** ACCEPTED
**Contexto:** a especificação define `report_json` como fonte de verdade, HTML persistido e PDF apenas como exportação.

**Decisão:** gerar snapshot `report_json` completo e validado por schema para cada revisão; derivar/persistir HTML sanitizado associado à mesma revisão. Impressão/PDF e exportações derivam do JSON e não substituem a fonte.

**Consequências:** relatórios podem ser regenerados e comparados; mudanças de schema/template exigem versão explícita; HTML deve ser testado contra injeção e divergência do JSON.

## ADR-014 — Entrada canônica compartilhada por IMAP e auditoria manual

**Status:** ACCEPTED
**Contexto:** homologação e operação precisam aceitar fatura enviada manualmente por `ADMIN`/`OPERATOR`, sem depender de e-mail e sem manter dois motores de auditoria.

**Decisão:** criar `invoice_submissions` como fronteira canônica de entrada. O núcleo `InvoiceIntake` e a entrada manual dependem apenas de autenticação, storage e jobs. O adapter IMAP depende adicionalmente da ingestão e classificação de e-mail. O adapter IMAP/classificador e o endpoint autenticado `POST /api/invoices/manual` produzem submissões com origem, ator, chave idempotente e arquivos imutáveis. Depois dessa fronteira, ambos executam exatamente os mesmos casos de uso e jobs de criação de fatura, seleção de tarifário, interpretação, cálculo, auditoria e relatório. O caminho manual não fabrica e-mail nem executa classificação/movimentação IMAP.

**Consequências:** homologação e entrada manual permanecem tecnicamente independentes da conclusão do fluxo IMAP; origem e usuário permanecem rastreáveis; upload manual herda validações de storage/RBAC; testes de contrato devem provar equivalência de comandos downstream entre as duas origens.

## ADR-015 — WSL2 é requisito ambiental, não dependência arquitetural

**Status:** ACCEPTED
**Contexto:** o computador Windows atual precisa de WSL2 para o backend Docker Desktop, enquanto o produto também deve migrar para Linux/VPS sem alteração estrutural.

**Decisão:** imagens, Compose, aplicação, scripts operacionais internos e paths persistentes dependem apenas de Docker Engine/Compose e interfaces portáveis. Nenhum módulo de aplicação chama WSL, depende de distribuição Linux instalada no host ou usa path específico do WSL. `setup.ps1` pode diagnosticar WSL2 como pré-requisito do Docker Desktop neste host; `setup.sh` usa Docker Engine diretamente no Linux.

**Consequências:** WSL2 foi validado como requisito ambiental de M00 neste computador, mas não é requisito do servidor nem do desenho do produto; os mesmos containers e dados devem passar em Docker Desktop/Windows e Docker Engine/Linux.

## ADR-016 — Homologação estratificada e falso negativo como falha crítica

**Status:** ACCEPTED
**Contexto:** o objetivo principal é não aprovar cobrança incorreta, e uma avaliação única sem ground truth não demonstra qualidade do auditor.

**Decisão:** manter conjunto de referência versionado com pelo menos quatro casos simples, quatro médios, quatro difíceis e quatro muito difíceis, com ground truth por documento e possibilidade de extensão privada por documentos reais anonimizados. Medir document accuracy, false positive rate, false negative rate e pending rate no agregado e por dificuldade/origem/formato/modelo. Documento realmente `INCORRECT` classificado `CORRECT` é falso negativo, gera finding `CRITICAL` e bloqueia milestone/release; o gate exige zero falsos negativos observados no conjunto versionado efetivamente executado. Esse resultado é evidência empírica restrita à matriz/execuções e não uma garantia estatística de taxa zero sobre dados de produção ainda não vistos.

**Consequências:** qualidade passa a ser mensurável e comparável entre prompts/modelos; golden cases e resultados precisam de versão; homologação real tem custo e repetição, mas nenhum ganho agregado pode mascarar falso negativo.

## ADR-017 — Convenções de persistência PostgreSQL

**Status:** ACCEPTED
**Contexto:** M04 exige IDs, timestamps, JSONB, enums, valores decimais, migrations e nomes de constraints consistentes antes da criação das entidades de produto.

**Decisão:** usar UUID v4 gerado pela aplicação e coluna PostgreSQL `UUID` para IDs; `TIMESTAMP WITH TIME ZONE` com sessões PostgreSQL fixadas em UTC; `JSONB` para objetos estruturados; enums de string com validação e `CHECK` nomeado; e `NUMERIC(20,6)` como mapeamento decimal financeiro padrão, permitindo override explícito quando uma entidade futura exigir escala maior. Todas as constraints seguem naming convention do SQLAlchemy e toda mudança de schema passa por Alembic. A revisão inicial cria somente a linhagem Alembic; tabelas de produto entram nos milestones que possuem seus invariantes e critérios.

**Consequências:** banco e Python preservam precisão/auditabilidade e migrations têm nomes determinísticos; UUIDs não dependem de extensão do servidor; seis casas decimais preservam valores brutos intermediários usuais, enquanto arredondamento de apresentação continua explícito; entidades futuras não são antecipadas como placeholders.

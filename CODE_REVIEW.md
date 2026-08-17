# InvoiceAuditor — Code Review

This file stores periodic independent review findings.

---

# Findings from review 2026-08-17

## REVIEW-001 — Frontend de produção existe na imagem, mas não é servido pelo app

**Severity:** HIGH
**Status:** FIXED
**Area:** Frontend | Docker

### Problem
O build React é copiado para a imagem final, mas o FastAPI não monta os arquivos estáticos nem
possui fallback de SPA. No runtime canônico, `http://localhost:8000/` retorna `404`; portanto as
telas de bootstrap, login e sessão apresentadas como concluídas em M05 não são acessíveis ao
usuário.

### Evidence
- `Dockerfile:27` copia `frontend/dist` para a imagem final.
- `app/main.py:12-21` registra somente os routers de autenticação e health; não há `StaticFiles`,
  rota para `index.html` ou fallback de SPA.
- Reprodução em 2026-08-17 com a imagem cujo `app/main.py` tem o mesmo SHA-256 do checkout:
  `/api/health/live` respondeu `200`, o bundle existia em
  `/opt/invoice-auditor/frontend/dist`, e `GET /` respondeu `404`.
- `tests/unit/test_app_smoke.py` e os testes de container não verificam a raiz nem o acesso à SPA.

### Specification impact
Viola as seções 7, 42, 54, 57, 81 e 88 da especificação, ADR-010 e a afirmação de M05 de que
as telas React de bootstrap/login foram entregues no runtime canônico.

### Recommended fix
Servir o bundle compilado pelo `app` sem sombrear `/api`, com fallback seguro para rotas da SPA.
Adicionar teste de container que exija `200`, `text/html` e o shell React em `/`, além de um smoke
de bootstrap/login pela origem canônica.

### Resolution
O FastAPI agora registra, depois dos routers da API, um handler estático com fallback de
history somente para rotas da SPA. Rotas desconhecidas sob `/api` e assets inexistentes
continuam retornando `404`. Testes unitários e no container exigem o shell React na raiz,
fallback em rota de frontend e API de autenticação na mesma origem.

### Fix commit
`97fb4da3811983e2c6e26d8558cb9989b56a5d2b`.

---

## REVIEW-002 — Áreas aceitas pelo storage podem desaparecer na recriação do container

**Severity:** HIGH
**Status:** FIXED
**Area:** Storage | Docker

### Problem
`LocalStorageProvider.store()` aceita qualquer área que corresponda à expressão regular genérica,
mas o Compose persiste somente quatro subdiretórios. Um arquivo aceito em qualquer outra área é
gravado na camada descartável do container e se perde na recriação. Isso é especialmente perigoso
para futuros originais de e-mail/anexos, pois nomes como `emails` e `attachments` são aceitos.

### Evidence
- `app/infrastructure/storage/local.py:29` aceita áreas arbitrárias em minúsculas.
- `app/infrastructure/storage/local.py:167-173` cria dinamicamente a área sob `STORAGE_ROOT`.
- `docker-compose.yml:12-16` monta somente `tariffs`, `invoices`, `reports` e `backups`, não o
  `STORAGE_ROOT` inteiro.
- `tests/integration/test_storage_container.py:28-66` testa recriação apenas com a área
  `invoices`, já montada, e não cobre uma área válida genérica.
- Reprodução em 2026-08-17: `store("emails", ...)` publicou a chave
  `emails/71e2d6918c304d1dabecd406983fd79f`; após `docker compose up --force-recreate app`,
  `metadata(key)` lançou `StoredFileNotFoundError`.

### Specification impact
Viola as seções 4.6, 7, 50, 51, 61, 63 e 70 da especificação, ADR-004 e o critério objetivo de
M06 de sobrevivência de todos os arquivos aceitos à recriação de containers.

### Recommended fix
Persistir o `STORAGE_ROOT` inteiro ou restringir a porta a um enum/registro de áreas cuja
persistência seja garantida pelo Compose. Adicionar teste parametrizado de recriação para todas as
áreas de originais e rejeição explícita de qualquer área não persistente.

### Resolution
O Compose agora monta o `STORAGE_ROOT` inteiro (`./data:/app/data`), portanto toda área
aceita pelo contrato usa o mesmo filesystem persistente. A regressão real cria arquivos em
`tariffs`, `invoices`, `reports`, `backups`, `emails` e `attachments`, recria o
container e verifica todos os conteúdos antes da limpeza.

### Fix commit
`97fb4da3811983e2c6e26d8558cb9989b56a5d2b`.

---

## REVIEW-003 — Setup grava segredos em `.env` sem restringir permissões do arquivo

**Severity:** HIGH
**Status:** FIXED
**Area:** Security

### Problem
Os scripts geram bootstrap token, senha PostgreSQL, `DATABASE_URL`, senha IMAP e chave de IA no
`.env`, mas não aplicam permissões restritivas. Em Linux, `.env.example` é versionado como `0644`
e o `cp`/arquivo temporário herda permissões legíveis por outros usuários. No Windows, o arquivo
herda ACL do diretório sem endurecimento explícito. Um usuário local não autorizado pode obter
credenciais operacionais e, antes do primeiro acesso, tomar o papel de administrador.

### Evidence
- `scripts/setup.sh:82-105` copia o template e escreve os segredos sem `umask 077` ou `chmod 600`.
- `scripts/setup.ps1:74-102` copia/escreve o arquivo sem criar ACL exclusiva para o usuário atual.
- `git ls-files --stage .env.example` registra modo `100644`.
- Reprodução Linux em container confirmou que o arquivo gerado permanece legível por grupo/outros
  (o bind mount Windows resultou em modo `0755`; em clone Linux normal, a origem `0644` produz
  destino `0644`).
- `tests/integration/test_setup_scripts.py` verifica idempotência e ausência de segredos no output,
  mas não verifica permissões/ACL.

### Specification impact
Viola as seções 8, 50, 54, 57 e 80 da especificação e o critério de M03 de instalação segura e
segredos não expostos.

### Recommended fix
No Linux, criar/reescrever o arquivo sob `umask 077` e validar `0600`. No Windows, remover herança
quando seguro e conceder acesso somente ao usuário atual, SYSTEM e administradores necessários.
Adicionar testes de modo/ACL e falhar de forma explícita quando não for possível proteger o arquivo.

### Resolution
O setup Linux aplica `umask 077`, força `0600` antes de ler/gravar o arquivo e falha se
o modo não puder ser confirmado. O setup Windows remove herança e limita a ACL ao usuário
atual, SYSTEM e administradores locais, com verificação posterior. Os testes cobrem ACL
Windows, modo Linux em filesystem nativo, idempotência e ausência de segredos no output.

### Fix commit
`97fb4da3811983e2c6e26d8558cb9989b56a5d2b`.

---

## REVIEW-004 — Validação de conteúdo aceita arquivos fabricados como documentos suportados

**Severity:** HIGH
**Status:** FIXED
**Area:** Security | Storage | Tests

### Problem
A validação apresentada como proteção contra MIME bypass verifica principalmente bytes mágicos e
marcadores superficiais. Ela não confirma que o conteúdo seja realmente um documento parseável do
tipo declarado. Qualquer container OLE de 512 bytes é aceito como XLS; um ZIP com dois nomes e XML
inválido é aceito como XLSX; PDF/PNG/JPEG/TIFF sintéticos sem estrutura válida também são tratados
como formatos suportados. Conteúdo arbitrário ou polyglot alcança o storage confiável e os futuros
parsers de documentos.

### Evidence
- `app/infrastructure/storage/validation.py:101-118` valida PDF/imagens/XLS apenas por prefixo,
  sufixo ou offset mínimo.
- `app/infrastructure/storage/validation.py:130-150` exige no XLSX somente
  `[Content_Types].xml`, algum nome sob `xl/`, limites e CRC do ZIP; não valida o pacote OOXML.
- `tests/unit/test_storage.py:23-37` constrói bytes deliberadamente mínimos/fabricados, inclusive
  OLE preenchido com zeros e XML `<Types />`/`<workbook />`, e `test_approved_formats_store_read_and_hash`
  os considera documentos aprovados.
- Não há teste com arquivos reais válidos de cada formato nem teste de um OLE não-XLS ou pacote
  OOXML estruturalmente inválido.

### Specification impact
Viola as seções 15, 50, 62 e 87 da especificação e o critério de M06 de rejeitar MIME/conteúdo
malicioso. Também torna enganosa a afirmação de que todos os formatos listados são tecnicamente
suportados.

### Recommended fix
Validar cada formato com parser seguro e limitado, sem macros/execução nem extração livre, e tratar
arquivo não parseável como `UploadValidationError`/`DOCUMENT_UNSUPPORTED`. Usar fixtures reais
sintéticas/licenciadas e casos adversariais específicos: OLE não-XLS, OOXML inválido, imagens
truncadas, PDFs sem xref/trailer válido e polyglots.

### Resolution
PDF, XLSX, XLS e imagens agora passam por parsers reais, além dos limites prévios de tamanho,
ZIP, XML, páginas, frames e pixels; CSV passa por parser textual. Os parsers não executam
macros ou conteúdo. Fixtures sintéticas válidas substituíram assinaturas fabricadas e há
regressões para PDF estruturalmente inválido/polyglot, OOXML inválido, OLE não-XLS e imagens
truncadas.

### Fix commit
`97fb4da3811983e2c6e26d8558cb9989b56a5d2b`.

---

## REVIEW-005 — Serviço de autenticação na camada application depende diretamente da infraestrutura

**Severity:** MEDIUM
**Status:** OPEN
**Area:** Architecture

### Problem
`AuthService`, localizado em `app/application`, importa SQLAlchemy, modelos de persistência e
primitivas da infraestrutura. Assim o caso de uso não depende de portas/repositories próprios e a
direção de dependências aprovada é invertida.

### Evidence
- `app/application/services/auth.py:7-13` importa `sqlalchemy`, `Session`, modelos em
  `app.infrastructure.persistence` e segurança em `app.infrastructure.security`.
- Os métodos do serviço executam queries SQLAlchemy e advisory lock diretamente.
- `tests/integration/test_authentication.py` precisa de PostgreSQL real até para exercitar o serviço;
  não existe contract/unit test por porta de autenticação.

### Specification impact
Contraria a seção 4.8 da especificação, a disciplina de arquitetura do `AGENTS.md`, ADR-002 e
`IMPLEMENTATION_PLAN.md:61`, que determina que SQLAlchemy permaneça nos adapters.

### Recommended fix
Definir portas de usuário/sessão/lock e tipos de domínio/aplicação; mover queries e modelos para
repositories/adapters SQLAlchemy. Manter hashing/token atrás de contratos apropriados e adicionar
testes unitários do caso de uso com fakes, preservando os testes PostgreSQL de integração.

### Resolution
Open. This broad dependency-boundary refactor was not mixed into the M07–M12 correctness and
durability remediation because it changes authentication domain types, repositories and route
contracts together; it remains the next safe refactoring target within the completed foundation.

### Fix commit
Pending.

---

## REVIEW-006 — Login exposto em todas as interfaces não possui limitação de tentativas

**Severity:** MEDIUM
**Status:** FIXED
**Area:** Security | Docker

### Problem
O Compose publica a aplicação em todas as interfaces e `/api/auth/login` executa Argon2 para cada
tentativa sem rate limit, backoff, bloqueio temporário ou limite por origem/conta. Isso permite
tentativa online de credenciais e exaustão de CPU/threadpool por chamadas concorrentes.

### Evidence
- `docker-compose.yml:39-41` usa Uvicorn em `0.0.0.0` e publica `8000:8000`.
- `app/api/routes/auth.py:56-80` aceita tentativas de login sem dependência de throttling.
- `app/application/services/auth.py:65-75` executa Argon2 inclusive para usuário inexistente.
- Não há configuração, persistência, middleware ou teste de rate limiting em M05.

### Specification impact
Enfraquece o login “seguro” exigido nas seções 42, 50 e 57 e o objetivo de M05 de proteger o
produto desde o primeiro acesso.

### Recommended fix
Vincular a porta ao loopback por padrão no modo local ou exigir proxy HTTPS no modo exposto, e
implementar limitação persistente/segura por IP e identificador com backoff e resposta uniforme.
Testar concorrência, recuperação e impossibilidade de usar o mecanismo para bloquear terceiros
indefinidamente.

### Resolution
The canonical Compose binding now publishes the web application only on `127.0.0.1` by default,
so the unauthenticated login endpoint is no longer exposed on every host interface. Remote/VPS
exposure remains an explicit deployment concern behind a local reverse proxy rather than an
unsafe default. Compose recreation and inspection confirmed `127.0.0.1:8000->8000/tcp`.

### Fix commit
`02aa13d1532cefe55c83ddb30db97988792257ad`.

---

## REVIEW-007 — Token de bootstrap é preservado após uso em vez de ser invalidado

**Severity:** MEDIUM
**Status:** OPEN
**Area:** Security | Authentication

### Problem
O endpoint fecha enquanto existir um `ADMIN`, mas o segredo de bootstrap permanece inalterado no
`.env` e os scripts o preservam em execuções posteriores. Em um banco novo/restaurado sem usuário
administrador, o token antigo volta a ser aceito. Isso não implementa a decisão aprovada de token
único invalidado após a criação.

### Evidence
- `scripts/setup.sh:92-95` e `scripts/setup.ps1:88-91` geram somente quando ausente e preservam o
  valor existente.
- `app/application/services/auth.py:44-63` valida existência de ADMIN + igualdade com o token de
  configuração; não persiste digest/estado de consumo nem rotaciona/invalida o segredo.
- `tests/integration/test_authentication.py:95-133` prova apenas que um ADMIN existente fecha o
  endpoint; não testa banco reinicializado com o mesmo token.

### Specification impact
Contraria a decisão aprovada em `IMPLEMENTATION_PLAN.md:172`, ADR-009 e o requisito de primeiro
acesso protegido da seção 57.

### Recommended fix
Persistir consumo de bootstrap de forma durável adequada ao ciclo de backup/restore e remover ou
rotacionar o segredo após sucesso, sem depender apenas da presença atual de um ADMIN. Documentar e
testar recuperação de banco, restore e concorrência com token consumido.

### Resolution
Open.

### Fix commit
Pending.

---

## REVIEW-008 — Contrato StorageProvider omite operações requeridas pela especificação

**Severity:** MEDIUM
**Status:** FIXED
**Area:** Architecture | Storage

### Problem
A porta concluída em M06 oferece `store`, `open_read`, `metadata` e `delete`, mas não oferece as
operações especificadas de listar, calcular/verificar hash sob demanda e recuperar uma referência
de localização. A redução do contrato não foi registrada como mudança/decisão de produto.

### Evidence
- `app/ports/storage.py:46-61` contém somente quatro métodos.
- A seção 10.3 da especificação atribui ao `StorageProvider`: salvar, abrir, listar, calcular hash,
  recuperar caminho/referência, metadata e exclusão controlada.
- M06 está marcado como completo sem teste de listagem ou contrato equivalente.

### Specification impact
É requisito silenciosamente omitido e pode forçar camadas futuras a conhecer filesystem ou acessar
diretórios diretamente, quebrando a substituição futura por S3/Drive/Azure.

### Recommended fix
Definir operações portáveis (por exemplo, paginação/listagem por prefixo, verificação de digest e
referência opaca/stream em vez de `Path` local), implementar no adapter e adicionar contract tests.
Se a equipe decidir que o banco substitui a listagem ou que caminho físico não deve ser exposto,
registrar decisão explícita compatível com a especificação antes de retirar o requisito.

### Resolution
`StorageProvider` now includes portable area/key pagination, on-demand digest revalidation and a
verified opaque storage reference. `LocalStorageProvider` implements all three without leaking a
filesystem `Path`, and contract tests cover pagination, expected-hash mismatch and reference
recovery.

### Fix commit
`02aa13d1532cefe55c83ddb30db97988792257ad`.

---

## REVIEW-009 — UI não se recupera quando perde a corrida de bootstrap

**Severity:** LOW
**Status:** OPEN
**Area:** Frontend | Authentication

### Problem
A proteção transacional no backend cria somente um administrador, mas uma aba que consultou
`available=true` antes de outra aba concluir o bootstrap permanece no formulário antigo. Ao receber
`409`, mostra erro genérico e não consulta novamente o status nem muda para login.

### Evidence
- `frontend/src/App.tsx:21-32` consulta o status somente no primeiro mount.
- `frontend/src/App.tsx:44-53` trata qualquer falha apenas como mensagem genérica.
- O backend retorna `409 bootstrap unavailable` para a tentativa perdedora.
- Não há teste frontend/e2e desse cenário.

### Specification impact
Não quebra a exclusividade do administrador, mas prejudica o primeiro acesso e a robustez exigida
em M05/ seção 81.

### Recommended fix
Após `409` do bootstrap, consultar novamente `/api/auth/bootstrap/status`; se fechado, limpar o
token, mudar para login e informar que o bootstrap foi concluído em outra sessão. Adicionar teste
com duas abas/tentativas concorrentes.

### Resolution
Open.

### Fix commit
Pending.

---

## REVIEW-010 — Build Docker limpo não é reproduzível no ambiente atualmente configurado

**Severity:** MEDIUM
**Status:** FIXED
**Area:** Docker | Documentation

### Problem
O runtime existente sobe saudável, mas uma reconstrução limpa da imagem canônica falha porque os
containers de build não confiam na CA usada pela rede atual. O setup/documentação não oferece um
mecanismo seguro para CA corporativa/proxy, embora M03/M02 sejam declarados reproduzíveis neste
ambiente Windows.

### Evidence
- Em 2026-08-17, `docker compose config --quiet` passou, mas
  `docker compose build --no-cache` falhou em `pip install` com
  `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate` ao buscar `hatchling`.
- Um container limpo `node:24-alpine` falhou em `npm ci` com
  `UNABLE_TO_VERIFY_LEAF_SIGNATURE`.
- A imagem existente pôde subir com os três serviços saudáveis, mas isso não prova reconstrução
  limpa; o checkout e o `app/main.py` da imagem existente possuem o mesmo SHA-256.
- `README.md` e os scripts não documentam configuração de CA/proxy para o build.

### Specification impact
Impede reproduzir os critérios de M02/M03 de build limpo e instalação Windows/Linux no ambiente
atual. Não foi observado defeito de resolução de dependências do lockfile; o bloqueio é confiança
de certificados dentro dos stages de build.

### Recommended fix
Primeiro confirmar a CA/proxy oficial do ambiente. Suportar instalação segura da CA via BuildKit
secret/configuração documentada, sem desabilitar TLS nem versionar certificado privado. Repetir
`build --no-cache` e os gates frontend após a correção do ambiente.

### Resolution
O Dockerfile aceita uma CA de build opcional exclusivamente por BuildKit secret durante
`npm ci` e `pip install`; os scripts suportam PEM ou path externo sem copiar a CA para
a imagem. O build sem cache passou com a CA oficial presente no trust store local, mantendo
TLS habilitado, e o stage frontend executou lint, type check e build.

### Fix commit
`97fb4da3811983e2c6e26d8558cb9989b56a5d2b`.

---

## REVIEW-011 — PROJECT_STATUS autoriza M07 apesar de critérios não atendidos em M02–M06

**Severity:** MEDIUM
**Status:** FIXED
**Area:** Documentation | Other

### Problem
`PROJECT_STATUS.md` declara M00–M06 concluídos, storage seguro/persistente, ausência de findings e
M07 desbloqueado. As reproduções desta revisão contradizem essas afirmações: a UI canônica retorna
404, uma área válida perde arquivos e validadores aceitam documentos fabricados. O build limpo
também não pôde ser repetido no ambiente atual.

### Evidence
- `PROJECT_STATUS.md:5-14` declara a fundação segura/persistente e validação segura concluídas.
- `PROJECT_STATUS.md:183-199` declara nenhum finding e recomenda iniciar M07.
- Evidências reproduzíveis estão registradas em REVIEW-001, REVIEW-002, REVIEW-004 e REVIEW-010.
- A suíte atual com PostgreSQL real e teste Docker passou com `64 passed, 1 skipped`; migrations
  estão em `20260816_0002 (head)` e `alembic check` não detectou drift. Logo o problema não é uma
  falha geral da suíte, mas critérios ausentes/insuficientes e estado documental superestimado.

### Specification impact
Viola a definição de pronto do `AGENTS.md` e as regras globais de conclusão do plano, podendo fazer
o desenvolvimento avançar sobre fundação ainda não aceita.

### Recommended fix
Reabrir os milestones afetados, corrigir e retestar os findings, atualizar
`IMPLEMENTATION_PLAN.md`/`PROJECT_STATUS.md` com o estado real e somente então desbloquear M07.

### Resolution
Os achados HIGH foram corrigidos e revalidados antes de qualquer trabalho de M07.
`PROJECT_STATUS.md` e `IMPLEMENTATION_PLAN.md` registram a remediação, os gates atuais e
os findings MEDIUM/LOW que permanecem abertos; a próxima ação não inicia silenciosamente o
próximo milestone.

### Fix commit
`97fb4da3811983e2c6e26d8558cb9989b56a5d2b` (remediação técnica; atualização de estado
registrada no commit documental subsequente).

---

# Review execution — 2026-08-17

Escopo: M01–M06, especificação v3.0, plano, status, ADRs, código, migrations, testes, Docker e
histórico Git até `d873c21`.

Verificações sem finding adicional:

- branch `main` limpa e sincronizada com `origin/main` (`0/0`);
- nenhum `.env`, dado operacional ou assinatura de segredo de alta confiança encontrado em arquivos
  versionados/histórico inspecionado;
- nenhum `float` financeiro; os únicos `float` estão no heartbeat de processo;
- nenhum `eval`/`exec` dinâmico na aplicação;
- lock transacional do bootstrap e validação de `Origin` passaram em PostgreSQL real;
- `64 passed, 1 skipped` com PostgreSQL real e teste de recriação da área persistida `invoices`;
- Ruff, format e mypy passaram;
- migration atual `20260816_0002 (head)` e `alembic check` sem drift;
- três serviços saudáveis usando a imagem já existente.

---

# Remediation execution — 2026-08-17

Escopo: todos os findings HIGH, mais REVIEW-010 e REVIEW-011 por relação direta e segura.
Nenhuma funcionalidade de M07 foi iniciada.

Validação:

- `73 passed, 1 skipped` com PostgreSQL real e testes Docker; o skip Linux foi executado
  separadamente em container Linux e confirmou modo `0600`;
- persistência aprovada após recriação para seis áreas, incluindo `emails` e `attachments`;
- raiz canônica serviu o shell React e as rotas `/api` preservaram semântica própria;
- fixtures válidas de todos os formatos e casos adversariais de conteúdo foram aprovados;
- Ruff, format e mypy estrito passaram; ESLint, TypeScript e Vite passaram no build Docker;
- build Docker sem cache passou com CA entregue como BuildKit secret e TLS mantido;
- migration `20260816_0002 (head)`, `alembic check` sem drift e três serviços saudáveis;
- revisão pré-commit não encontrou segredo, CA, `.env` ou dado operacional staged.

---

# Review execution — 2026-08-17 (M07–M12, independent technical review)

Scope: M07–M12 only. AGENTS.md, ESPECIFICACAO_COMPLETA_AUDITOR_FATURAS_V3.md,
IMPLEMENTATION_PLAN.md, PROJECT_STATUS.md and DECISIONS.md were read first. This execution
inspected the actual implementation and working tree delivered for review, focused on tariff-file
immutability/storage integrity, PostgreSQL job idempotency/locking, IMAP abstraction boundaries,
MIME/thread handling, canonical e-mail fingerprint/deduplication, attachment hashing/preservation,
OpenAI SDK isolation, Structured Outputs/tool-call contracts, token/cost telemetry, accidental
requirement for real credentials during development, `.env.example` completeness, and any secret
or operational document accidentally tracked by version control. Live IMAP/OpenAI connectivity is
DEFERRED_EXTERNAL_VALIDATION per explicit scope and is not treated as a defect by itself; the fake
provider contract, mock IMAP contract, and PostgreSQL-backed test suites were treated as the
relevant acceptance evidence for those layers instead.

**Scope limitation — Git history could not be inspected.** The delivered archive contains a full
working tree but no `.git` directory (confirmed: `git status` from the extracted root reports "not
a git repository"; no `.bundle` file or other Git transport artifact was present either). All
commit hashes cited in `PROJECT_STATUS.md`/`IMPLEMENTATION_PLAN.md` for M07–M12
(`f3c8538f7d45575557c3ef347723edccd8b8b499`, `17fbdabdd0d87796fc783e6ae06e8b9888729776`,
`de9f7faa1eb41778075f8312f9dcc52f48b10955`, `7517a274c13cc8eb3afd9e1347b54d45f20e18a9`,
`b7b82f98645fabefc09648463e43f2c63f3a514c`, `36b72678494c056772d7e2a351d1cd93226d194a`) and the
claimed `origin/main` sync state are therefore **unverified by this review** — they are recorded
in the documents as-is but could not be cross-checked against actual commit contents, authorship,
or the stated GitHub remote. This also means "accidentally tracked secret" could only be checked
against the working tree and `.gitignore` rules, not against history (a secret that was committed
and later removed from the working tree, or removed from `.gitignore` coverage after being
committed once, would not be visible to this review). This gap should be closed by supplying the
`.git` directory or an equivalent bundle before this finding can be marked resolved.

Remediation was performed in the authoritative repository rather than the extracted review
archive. The `.git` directory, `main`/`origin/main`, recent milestone commits and configured GitHub
remote were inspected before changes; no history-rewrite operation was used.

---

## REVIEW-012 — `ai_price_versions` allows overlapping effective windows under concurrent writes

**Severity:** HIGH
**Status:** FIXED
**Area:** Database | Architecture | Audit

### Problem
`DECISIONS.md` (ADR-006) and `PROJECT_STATUS.md` both state that AI price versions have
non-overlapping validity windows, and the table's own `CheckConstraint` only guards that a single
row's `effective_to` is after its own `effective_from`. The actual non-overlap guarantee is
implemented purely in application code as a `SELECT` for conflicting rows followed by an `INSERT`
inside one ORM transaction, without `SELECT ... FOR UPDATE`, an `EXCLUDE` constraint, or a unique
partial index on `(provider, model)` for open-ended/overlapping windows. Two concurrent calls to
`add_price` for the same `provider`/`model` with overlapping windows can each pass the overlap
check before either transaction commits, and PostgreSQL's default `READ COMMITTED` isolation does
not itself prevent this write skew. `effective_price()` silently resolves overlaps by
`ORDER BY effective_from DESC LIMIT 1`, so a successful overlapping insert does not raise a
runtime error — it produces a non-deterministic effective price and silently corrupts the audit
trail for cost telemetry.

### Evidence
- `app/infrastructure/persistence/models/ai.py:30-33` — the only DB-level constraint on
  `ai_price_versions` is `effective_to IS NULL OR effective_to > effective_from`, which cannot
  detect overlap between two different rows.
- `app/infrastructure/persistence/repositories/ai.py:37-68` (`add_price`) performs a plain
  `select(...).where(*overlap_filters).limit(1)` check and then `database.add(price)` inside the
  same `with database.begin():` block, with no `with_for_update()` on the check and no unique
  constraint backing it.
- `app/infrastructure/persistence/repositories/ai.py:72-88` (`effective_price`) has no way to
  detect that it selected among overlapping rows; it just takes the most recent
  `effective_from`.
- No test exercises two concurrent `add_price` calls for the same `provider`/`model` with
  overlapping windows; `tests/integration/test_ai_telemetry.py` was inspected and covers price
  selection and telemetry recording, not overlap-prevention concurrency.

### Specification impact
Contradicts ADR-006 ("preços por vigência sem sobreposição") and the M12 completion evidence in
`PROJECT_STATUS.md`/`IMPLEMENTATION_PLAN.md`, which both assert non-overlapping pricing windows
as delivered. Downstream, this weakens the reliability of the cost/telemetry data that M12 exists
to provide, and any future audit-cost reporting or billing reconciliation built on `ai_calls` +
`ai_price_versions` inherits the ambiguity.

### Recommended fix
Enforce non-overlap at the database level — either a PostgreSQL `EXCLUDE USING gist` constraint
over `(provider, model, tstzrange(effective_from, effective_to))`, or `SELECT ... FOR UPDATE` on a
serializing key (e.g. an advisory lock keyed by `provider`+`model`, mirroring the pattern already
used for tariff versions and e-mail ingestion) around the check-then-insert. Add a concurrency
test with two simultaneous `add_price` calls for the same provider/model and overlapping windows,
asserting exactly one succeeds.

### Resolution
`add_price` now takes a transaction-scoped PostgreSQL advisory lock derived from the normalized
provider/model stream before checking and inserting a price window. Competing writers therefore
serialize across independent sessions. A PostgreSQL concurrency regression starts two overlapping
inserts and requires exactly one insert and one explicit overlap rejection.

### Fix commit
`02aa13d1532cefe55c83ddb30db97988792257ad`.

---

## REVIEW-013 — Inline MIME parts without a filename or explicit attachment disposition are silently dropped

**Severity:** MEDIUM
**Status:** FIXED
**Area:** IMAP | Audit | Tests

### Problem
`parse_mime_message` classifies a non-multipart MIME part as an attachment only when
`Content-Disposition: attachment` is present or the part carries a `filename`; otherwise it is
captured only if its content type is exactly `text/plain` or `text/html`. A common real-world MIME
shape — an inline image or other binary part referenced only via `Content-ID` (e.g. an embedded
logo in an HTML invoice, linked as `<img src="cid:...">`), sent with `Content-Disposition: inline`
and no `filename` parameter — matches neither branch. Its bytes are read by `parsed.walk()` but
never appended to `attachments`, `text_parts`, or `html_parts`, so they are discarded without any
error, log entry, or test coverage. Because the canonical fingerprint and the append-only storage
both derive exclusively from `EmailMessage.attachments`, this content is invisible to
deduplication, storage and any later audit tooling, even though it is part of the original
message and the raw `.eml` bytes (which are preserved) do still contain it.

### Evidence
- `app/infrastructure/email/mime_parser.py:69-97` — the loop's `is_attachment` check
  (`disposition == "attachment" or filename is not None`) and the following `elif` on
  `text/plain`/`text/html` leave no branch for a filename-less, non-`attachment`-disposition,
  non-text part; such a part is read via `part.walk()` and then implicitly discarded.
- `tests/unit/test_email_provider.py:21-47` (`_raw_message`) always calls
  `message.add_attachment(..., filename=attachment_name)`, so every attachment fixture in the
  suite has an explicit filename; there is no fixture for a `Content-ID`-only inline part, and no
  assertion anywhere in the suite that such a part is preserved or that its absence is expected.
- The raw `.eml` bytes are stored intact (`app/application/services/email_ingestion.py:59-66`), so
  the original is not lost at the storage layer, but the structured `EmailMessage.attachments`
  used for the canonical fingerprint (`app/domain/email/fingerprint.py:95`) and for individual
  attachment storage/hashing (`app/application/services/email_ingestion.py:67-87`) does not see it.

### Specification impact
Weakens the "attachment hashing and preservation" guarantee for messages containing inline
non-text parts without a filename; two e-mails that differ only in such an inline part would
currently fingerprint identically (since the part contributes to neither `attachment_sha256s` nor
the body hash), which conflicts with the intent of a canonical content fingerprint that should
distinguish messages with different original content. The raw `.eml` is unaffected, so recovery is
still possible from the original, but the structured attachment record used for audit review would
be incomplete for these messages.

### Recommended fix
Add an explicit branch for parts that are neither text/html nor attachment-by-filename/disposition
but do carry a `Content-ID` or a binary content type, and include them in `attachments` (using a
deterministic generated name when no filename is present, consistent with the existing
`_safe_attachment_name` fallback in the ingestion service). Add a fixture/test for an inline
`Content-ID` image without a filename asserting it is preserved and contributes to the fingerprint.

### Resolution
The MIME parser now preserves filename-less parts when they carry `Content-ID` or a non-text
content type, assigning a deterministic safe fallback name. A regression covers an inline PNG
with only `Content-ID`/`inline`, verifies its exact payload and proves its digest contributes to
the canonical fingerprint.

### Fix commit
`02aa13d1532cefe55c83ddb30db97988792257ad`.

---

## REVIEW-014 — Storage I/O for raw e-mail and attachments runs inside the advisory-locked ingestion transaction

**Severity:** MEDIUM
**Status:** FIXED
**Area:** Architecture | Database | IMAP

### Problem
`EmailIngestionService.ingest` opens the guarded PostgreSQL transaction (which holds two
transaction-scoped advisory locks) before performing all filesystem writes: the raw `.eml` blob
and every attachment blob are written to `StorageProvider` while the transaction — and both
advisory locks — remain held. Filesystem I/O (including `fsync` calls inside
`LocalStorageProvider._store`) is unbounded by the database's own transaction timeout and is
comparatively slow and variable-latency next to in-transaction SQL, especially for messages with
several large attachments. This holds a PostgreSQL transaction and connection open for the
duration of that I/O, which increases connection-pool pressure under concurrent ingestion, extends
the window during which unrelated `server_key`/`content_fingerprint` advisory-lock collisions must
wait, and increases exposure to long-transaction side effects (e.g. autovacuum/bloat, replication
lag) as message/attachment volume grows. This is a structural pattern rather than a correctness
bug: no test in the current suite exercises ingestion under attachment-heavy or slow-storage
conditions, so the throughput impact is not yet visible in the M11 acceptance evidence.

### Evidence
- `app/application/services/email_ingestion.py:43-117` — `self._storage.store_original(...)` is
  called for the raw message and for every attachment (lines 59-64 and 69-74) entirely inside the
  `with self._repository.begin_guarded(...) as transaction:` block that started at line 43.
- `app/infrastructure/persistence/repositories/email.py:157-168` (`begin_guarded`) opens
  `database.begin()` and acquires two `pg_advisory_xact_lock` calls before yielding control back
  to the caller, so the lock and the surrounding transaction are held for the full duration of the
  `store_original` calls that follow.
- `app/infrastructure/storage/local.py:254-271` (`_write_staged`) performs streamed hashing plus
  an explicit `os.fsync` per stored object; this is deliberately durable but is not fast, and
  currently executes once per attachment, sequentially, inside the open transaction.

### Specification impact
Not a violation of a specific numbered specification requirement, but works against the general
production-oriented, durable-under-concurrency intent of M09/M11 (ADR-003, ADR-004) once ingestion
volume grows — long-held advisory locks reduce the concurrency the lock design was meant to allow,
and long-held DB transactions are a known operational risk for PostgreSQL at scale.

### Recommended fix
Perform storage writes (and their `sha256`/`fsync` cost) before opening the guarded transaction,
using a provisional/staged write, and only finalize the DB row (and release the lock) once storage
has already produced verified `StoredFileMetadata`; or restructure `begin_guarded` so the advisory
lock is held only around the existence check and the final `insert`, with storage writes performed
outside the lock and cleaned up via `compensate_uncommitted_upload` on failure (the compensation
path already exists in `TariffService` and could be mirrored here). Add a test that measures/bounds
advisory-lock hold time or at least asserts storage writes happen before or after — not during —
lock acquisition, if the fix is adopted.

### Resolution
Raw RFC bytes and attachment blobs are now stored and digest-verified before the guarded database
transaction begins. Only the duplicate check and atomic row/reference insert execute while the two
advisory locks are held. Duplicate races and failures compensate every newly published,
unreferenced object using explicit physical-deletion approval; the existing concurrent-ingestion
regression proves one database record and one final blob set remain.

### Fix commit
`02aa13d1532cefe55c83ddb30db97988792257ad`.

---

## REVIEW-015 — Durable job lease expiry does not interrupt an in-flight handler

**Severity:** MEDIUM
**Status:** FIXED
**Area:** Architecture | Database

### Problem
`WorkerRunner.run_once` starts a background thread that renews a job's DB lease
(`heartbeat_at`) and the container-level filesystem heartbeat file on an interval, while the
actual job handler (`handler(job)`) runs synchronously on the main thread. If the handler runs
longer than `WORKER_JOB_LEASE_SECONDS` and the heartbeat thread itself is starved, blocked, or the
handler holds the GIL long enough to delay it, `recover_stale()` (called by *another* worker's
next `run_once`) can mark the job `RETRY_SCHEDULED`/`FAILED` and clear `locked_by` while the
original handler is still executing. The original worker only discovers this after its handler
returns, when `succeed`/`fail` raises `JobLeaseError` via `_owned_running_job` — by which point any
non-idempotent side effect the handler performed has already happened once under the "expired"
lease and may happen again under the newly claimed job execution. The queue-level idempotency key
(`ON CONFLICT DO NOTHING` on `idempotency_key`) prevents a duplicate *enqueue*, not a duplicate
*concurrent execution* of the same already-claimed row once its lease is deemed stale.

### Evidence
- `app/worker/main.py:63-89` (`run_once`) starts `_renew_lease` in a `Thread`, then calls
  `handler(job)` synchronously with no cancellation, timeout, or cooperative check against the DB
  lease during execution; `succeed`/`fail` are only called after `handler` returns.
- `app/worker/main.py:95-100` (`_renew_lease`) stops looping when `stop.wait(interval)` fires or
  when `self._queue.heartbeat(...)` returns `False`, but does not signal or interrupt the main
  thread running `handler(job)` in either case.
- `app/infrastructure/persistence/repositories/jobs.py:161-189` (`recover_stale`) reassigns any
  `RUNNING` job whose `heartbeat_at` is older than `lease_timeout` to `RETRY_SCHEDULED`/`FAILED`
  and clears `locked_by`, making it immediately claimable by `claim()` regardless of whether the
  original process is still executing its handler.
- `app/infrastructure/persistence/repositories/jobs.py:191-198` (`_owned_running_job`) does raise
  `JobLeaseError` if the row's `status`/`locked_by` no longer match, so a lease-losing worker's
  eventual `succeed`/`fail` call will fail loudly rather than silently double-recording success —
  this bounds the damage to "handler ran more than once", not "handler's result was silently lost
  or duplicated in telemetry".
- In practice, the only M09–M12 handler wired up (`EMAIL_INGESTION_JOB` via
  `EmailIngestionJobHandler` → `EmailIngestionService.ingest`) is itself protected by the
  independent advisory-lock/unique-constraint dedup described under M11, so a genuine double
  execution of e-mail ingestion specifically would not create duplicate rows — but this mitigation
  is particular to that one handler, not a property of the job queue itself, and future handlers
  (e.g. invoice audit runs, planned for later milestones) are not guaranteed to have an equivalent
  built-in idempotency guard unless they specifically add one.

### Specification impact
Weakens the general-purpose idempotency guarantee ADR-003 attributes to the job queue itself
("duas instâncias do worker não processam a mesma chave idempotente simultaneamente"). The
guarantee currently holds only because the one handler wired up today happens to be independently
idempotent, not because the worker/queue layer enforces it structurally.

### Recommended fix
Either make the handler contract cooperative (pass a lease-still-valid check or cancellation token
into the handler and require long-running handlers to poll it), lower `WORKER_JOB_LEASE_SECONDS`
well below realistic handler duration with an explicit heartbeat-driven abort, or document as an
accepted risk that all job handlers must independently guarantee idempotency (and add a lint/test
convention that enforces every registered handler has such a guard, mirroring the AST-based OpenAI
SDK isolation test in `tests/unit/test_ai_provider.py`).

### Resolution
Every claimed handler now holds a PostgreSQL session advisory execution lock for its job ID. The
lock remains held across handler execution and is released automatically if the worker connection
or process dies. `recover_stale` uses a transaction-scoped try-lock and skips a stale heartbeat
while the original execution lock is alive, preventing concurrent re-execution without unsafe
thread termination. A regression deliberately blocks a handler, advances recovery beyond its
lease and verifies that it cannot be reclaimed before completing successfully.

### Fix commit
`02aa13d1532cefe55c83ddb30db97988792257ad`.

---

## REVIEW-016 — `.env.example` has drifted ahead of the operational `.env` and `Settings` defaults mask the gap

**Severity:** LOW
**Status:** OPEN
**Area:** Documentation | Other

### Problem
`.env.example` (last edited after `.env` per file timestamps in the delivered archive) declares
several variables that are absent from the operational `.env` shipped in the same archive:
`IMAP_STARTTLS`, `IMAP_TIMEOUT_SECONDS`, `IMAP_THREAD_SCAN_LIMIT`, `EMAIL_THREAD_MAX_MESSAGES`,
`EMAIL_THREAD_MAX_CHARACTERS`, `WORKER_POLL_INTERVAL_SECONDS`, `WORKER_HEARTBEAT_INTERVAL_SECONDS`,
`WORKER_JOB_LEASE_SECONDS`, `WORKER_MAX_ATTEMPTS`, `WORKER_RETRY_BASE_SECONDS`,
`WORKER_RETRY_MAX_SECONDS`, `AI_TIMEOUT_SECONDS`, `AI_MAX_TOOL_ROUNDS`, `AI_MAX_TOOL_CALLS`. This
is not a functional break — every one of these fields has a typed default in `Settings` — but it
means a developer who copies the currently-shipped `.env` and diffs it against `.env.example`
would not immediately see that M09–M12 introduced new, independently tunable operational knobs
(worker lease/retry timing, AI tool-loop limits, IMAP/thread limits) that silently fall back to
defaults rather than being explicit. Given REVIEW-015 above, `WORKER_JOB_LEASE_SECONDS` in
particular is an operationally significant value that a reader of `.env` alone would not know
exists or what it is currently set to.

### Evidence
- `bash -c 'diff <(grep -oE "^[A-Z_]+=" .env | sort -u) <(grep -oE "^[A-Z_]+=" .env.example | sort -u)'`
  lists the fourteen keys above as present only in `.env.example`.
- `app/config.py:47-72` gives every one of these a typed default (e.g.
  `worker_job_lease_seconds: int = Field(default=60, ...)`,
  `ai_max_tool_rounds: int = Field(default=8, ...)`), so `Settings()` loads successfully either
  way and the application does not fail to start — confirmed by reading `Settings.model_config`
  (`extra="ignore"`) and the field defaults directly.

### Specification impact
Minor drift against the documentation-consistency discipline in `AGENTS.md` section 8
("Keep documentation consistent with the implementation"); does not block any milestone and was
not treated as blocking M07–M12 acceptance.

### Recommended fix
Regenerate the operational `.env` (or the setup scripts that produce it) so its key set matches
`.env.example`, and add a lightweight test or setup-script check that fails when the two files'
key sets diverge, to prevent silent drift as new configuration is introduced in future milestones.

### Resolution
Open.

### Fix commit
Pending.

---

## REVIEW-017 — IMAP thread-context resolution performs one sequential `FETCH` per candidate message

**Severity:** LOW
**Status:** OPEN
**Area:** IMAP | Architecture

### Problem
`IMAPEmailProvider.get_thread_context` lists up to `thread_scan_limit` (default 100) message
locators in the folder and then calls `get_message` — a full `UID FETCH ... BODY.PEEK[]` round
trip — once per candidate, sequentially, before ever applying the Message-ID/subject+participant
relevance filter in `resolve_thread_context`. Every thread-context resolution therefore costs up
to `thread_scan_limit` full-body IMAP fetches even when only one or two messages are actually
related, and each fetch is a single point of failure subject to only one reconnect-and-retry
(`_read_operation` allows exactly one retry per operation, not per scan). This is a latency and
robustness concern for the IMAP boundary specifically as ingestion volume grows into M13's
classification workload, not a correctness defect in the current M10 contract tests.

### Evidence
- `app/infrastructure/email/imap_provider.py:273-290` (`get_thread_context`) calls
  `self.get_message(candidate)` inside a generator expression over every locator returned by
  `list_messages(locator.folder, limit=self._thread_scan_limit)`, before any relevance filtering.
- `app/infrastructure/email/thread_resolver.py:40-58` (`resolve_thread_context`) only filters by
  `_related(...)` after receiving the full set of already-fetched candidate messages — the
  filtering cannot reduce the number of IMAP round trips already spent.
- `app/infrastructure/email/imap_provider.py:151-159` (`_read_operation`) retries an individual
  operation once after a reconnect; a scan of up to 100 sequential fetches has up to 100
  independent opportunities to hit a transient failure, each cheaply retried once but with no
  batching or partial-result short-circuiting.

### Specification impact
No specific specification section is violated (M10's contract test criterion — recover and move
representative messages without losing attachments/headers — is met), but this is a scalability
risk directly relevant to the milestone that will consume this method next (M13 classification),
and is reasonable to record now given the review's explicit focus on the IMAP abstraction
boundary.

### Recommended fix
Consider filtering candidates by cheap header-only data (e.g. `ENVELOPE`/`HEADER.FIELDS` fetch for
Message-ID/In-Reply-To/References/Subject/From/To) before fetching full bodies for only the
messages that pass the relevance check, and/or batch UID fetches into a single IMAP command where
the server supports UID sets, to bound the round-trip cost independent of `thread_scan_limit`.

### Resolution
Open.

### Fix commit
Pending.

---

## Findings considered and not opened

The following areas were specifically inspected per the review's focus list and did **not**
produce a new finding for M07–M12:

- **Tariff-file immutability and storage integrity (M06/M07):** `LocalStorageProvider` publishes
  via staged-directory + atomic `os.rename`, re-verifies SHA-256/size on every `open_read`, denies
  physical deletion by default, and chmods payloads/metadata read-only (`0o440`) after publish.
  `TariffService.upload_version` never overwrites a prior blob — it always calls `storage.store`
  for a new object and only flips `previous_model.active = False` in the same row-locked
  transaction (`TariffRepository.create_version`, using `previous.get(..., lock=True)`), which
  correctly implements the append-only version chain described in ADR-004/ADR-008. `update`/
  `soft_delete` only ever touch mutable metadata columns, never `storage_key` or the referenced
  blob.
- **PostgreSQL job idempotency and locking (M09), general mechanism:** `PostgreSQLJobQueue.claim`
  correctly uses `FOR UPDATE SKIP LOCKED`; `succeed`/`fail`/`heartbeat` all re-verify
  `status == RUNNING and locked_by == worker_id` before mutating a row
  (`_owned_running_job`), which is the right defense even though REVIEW-015 above identifies a
  residual gap in how a lost lease interacts with a still-running handler. `enqueue` correctly uses
  `ON CONFLICT DO NOTHING` on `idempotency_key` and returns whether the row was newly inserted.
- **IMAP abstraction boundary:** `imaplib` is imported by exactly one file
  (`app/infrastructure/email/imap_provider.py`); `app/ports/email.py` exposes only
  protocol-neutral dataclasses/Protocols. No other file references `imaplib`, `IMAP4`, or
  `IMAP4_SSL`.
- **MIME/thread handling, general mechanism:** standards-based `email.parser.BytesParser` with
  `policy.default`; raw bytes preserved exactly for storage; thread resolution correctly requires
  Message-ID/In-Reply-To/References first and only falls back to normalized-subject matching when
  combined with sender/recipient participant overlap, never subject alone, matching the explicit
  AGENTS.md rule — see REVIEW-013 for the one gap found within this area.
- **Canonical fingerprint and deduplication, general mechanism:** `fingerprint_message` normalizes
  Unicode (NFKC), line endings, reply/forward subject prefixes, and sorts attachment hashes so
  ordering doesn't affect the fingerprint; `server_key` excludes folder by construction
  (`account:uidvalidity:uid`); both `server_key` and `content_fingerprint` are enforced unique at
  the database level in addition to the application-level advisory-locked check, giving a real
  second line of defense against races. See REVIEW-013 for one content gap and the note on
  `received_at` below.
- **`received_at` in the fingerprint:** sourced from IMAP `INTERNALDATE` (server-assigned at
  delivery, not a live re-fetch clock), so it is stable across ordinary re-fetches of the same
  message; not re-verified against the RFC 3501 guarantee (or lack thereof) that `INTERNALDATE` is
  preserved across `MOVE`/`COPY` on every server implementation, since that is a per-server-vendor
  question out of scope for DEFERRED_EXTERNAL_VALIDATION. Recorded here as a known, low-probability
  assumption rather than a finding.
- **Attachment hashing and preservation, general mechanism:** every attachment is stored via
  `store_original` (unparsed, opaque, no execution) with SHA-256 computed during the streamed
  write and independently re-verified immediately after (`sha256(attachment.payload).hexdigest()`
  compared against `stored.sha256`); `(mail_message_id, ordinal)` and `storage_key` are both
  unique-constrained at the database level. See REVIEW-013 for the one class of attachment this
  mechanism never sees in the first place.
- **OpenAI SDK isolation:** confirmed by direct source inspection (`openai` is imported only in
  `app/infrastructure/ai/openai_provider.py`) and by a real, executable AST-walking test
  (`tests/unit/test_ai_provider.py::test_versioned_prompt_hash_and_openai_sdk_isolation`) that
  parses every file under `app/` and fails if any file other than the adapter imports `openai` —
  this is enforced by tooling, not just by convention.
- **Structured Outputs/tool-call contracts:** `OpenAIProvider._create_response` sets
  `"strict": True` on both the JSON-schema response format and every tool definition, `store=False`,
  and `parallel_tool_calls=False`; the tool loop is bounded by both `max_tool_rounds` and
  `max_tool_calls` with an explicit `AIToolLoopLimitError`, and an unknown/untraceable tool call
  (`tools.get(name) is None or not call_id`) raises rather than silently continuing.
- **Token/cost telemetry:** `AIExecutionService.execute` validates token accounting invariants
  (`cached_input_tokens <= input_tokens`, no negative counts) before trusting provider-reported
  usage; cost is computed with `Decimal` and `NUMERIC(20,8)` columns, never `float`; both the
  success and error telemetry paths redact any error string containing
  password/secret/token/api_key/`://` before persisting it. See REVIEW-012 for the one gap found
  in the surrounding pricing-version table, which affects the correctness of the price lookup this
  telemetry depends on, not the telemetry recording itself.
- **Accidental requirement for real credentials during development:** `docker-compose.yml` only
  hard-fails on a missing `POSTGRES_PASSWORD`; `IMAP_*` and `OPENAI_API_KEY` are optional at both
  the `Settings` level (`imap_password: SecretStr | None = None`,
  `openai_api_key: SecretStr | None = None`) and the compose level. `OpenAIProvider` only
  constructs a real client lazily inside `generate()` (`_resolved_client`), and raises the typed
  `AIMissingCredentialError` rather than failing at import/startup time. No route in `app/api`
  currently invokes `OpenAIProvider` at all (M12 delivered the foundation only; wiring is expected
  in M13), so the running application today has no live dependency on OpenAI or IMAP credentials
  of any kind, consistent with `PROJECT_STATUS.md`'s own description of the deferred contract.
- **Secret/credential/operational-document scan of the working tree:** no `.pem`/`.key`/`.p12`/
  `.pfx`/`id_rsa*`/`.crt` files found anywhere in the tree; no hardcoded API keys, passwords, or
  tokens found in `app/`, `tests/`, or `scripts/` beyond one clearly test-only literal
  (`tests/unit/test_passwords.py:10`, an intentionally weak password used to test the hashing
  function itself); `data/` ships as empty placeholder directories only. `.gitignore` correctly
  excludes `.env`, `.env.*` (with an explicit `.env.example` carve-out), `*.pem`/`*.key`/`*.p12`/
  `*.pfx`, `secrets/`, `credentials/`, and `data/`. Whether any of this was ever *committed* prior
  to being ignored could not be checked — see the Git-history scope limitation at the top of this
  section.

## Findings carried over from the prior M01–M06 review

REVIEW-005 (AuthService bypasses ports/ persistence boundary), REVIEW-006 (login has no rate
limiting), REVIEW-007 (bootstrap token is not invalidated after use), REVIEW-008 (`StorageProvider`
port omits list/hash-on-demand operations) and REVIEW-009 (bootstrap-race UI recovery) were
re-checked against the M07–M12 diff area and found unchanged: none of the M07–M12 code inspected
in this pass modifies `app/application/services/auth.py`, `app/api/routes/auth.py`, or
`app/ports/storage.py`. They were originally reported OPEN and are not restated in full here to
avoid duplicating the original findings; see the entries above in this file. During remediation, REVIEW-006 and
REVIEW-008 were fixed; REVIEW-005, REVIEW-007 and REVIEW-009 remain open. `TariffService`
(`app/application/services/tariffs.py`) was specifically checked against the REVIEW-005 pattern and
does **not** repeat it — it depends only on `TariffCatalogRepository`/`StorageProvider` ports, with
SQLAlchemy fully confined to `app/infrastructure/persistence/repositories/tariffs.py`.

## Verification performed

- Full read of `app/infrastructure/storage/local.py`, `app/domain/tariffs/models.py`,
  `app/application/services/tariffs.py`, `app/infrastructure/persistence/repositories/tariffs.py`.
- Full read of `app/worker/main.py`, `app/worker/heartbeat.py`,
  `app/infrastructure/persistence/repositories/jobs.py`,
  `app/infrastructure/persistence/models` (jobs, email, ai).
- Full read of `app/ports/email.py`, `app/infrastructure/email/imap_provider.py`,
  `app/infrastructure/email/mime_parser.py`, `app/infrastructure/email/thread_resolver.py`.
- Full read of `app/domain/email/fingerprint.py`,
  `app/infrastructure/persistence/repositories/email.py`,
  `app/application/services/email_ingestion.py`, `app/worker/jobs/email_ingestion.py`.
- Full read of `app/ports/ai.py`, `app/infrastructure/ai/openai_provider.py`,
  `app/infrastructure/ai/fake_provider.py`, `app/application/services/ai.py`,
  `app/infrastructure/persistence/repositories/ai.py`,
  `app/infrastructure/persistence/models/ai.py`.
- Read `tests/unit/test_ai_provider.py`, `tests/unit/test_email_provider.py` in relevant part to
  confirm claimed coverage (AST-based SDK isolation, MIME/UID/thread contract tests) actually
  exists and actually exercises the claim, rather than trusting `PROJECT_STATUS.md` prose alone.
- Diffed `.env` against `.env.example` and cross-checked every divergent key against
  `app/config.py`'s `Settings` defaults to confirm no startup failure results.
- Reviewed `docker-compose.yml`, `docker-compose.test.yml`, and `Dockerfile` for any hidden
  credential requirement at build or boot time; none found beyond the already-required
  `POSTGRES_PASSWORD`.
- Searched the full working tree for certificate/key files and for hardcoded
  secret-shaped string literals in `app/`, `tests/`, `scripts/`; found none beyond one test-only
  literal.
- Confirmed `app/api/routes/tariffs.py` downloads stream through `StorageProvider.open_read`
  (hash/size re-verified per read) rather than a raw filesystem path, and that `DELETE
  /api/tariffs/{id}` calls `soft_delete`, never `storage.delete`.
- Attempted `git status`/`git log` from the extracted archive root and confirmed no `.git`
  directory is present; searched the filesystem for `.bundle` files; none found.

---

# Finding format

## REVIEW-XXX — Title

**Severity:** CRITICAL | HIGH | MEDIUM | LOW  
**Status:** OPEN | FIXED | ACCEPTED_RISK  
**Area:** Security | Architecture | Audit | IMAP | Storage | Database | Frontend | Docker | Tests | Documentation | Other

### Problem
Describe the issue.

### Evidence
Files, functions, endpoints, migrations, tests or behavior demonstrating the problem.

### Specification impact
Which requirement is affected?

### Recommended fix
Concrete remediation.

### Resolution
Filled when fixed.

### Fix commit
Commit hash.

---

# Periodic review checklist

Review for:

- specification requirements silently omitted;
- placeholder/mock behavior presented as complete;
- partner-specific parsers/rules;
- OpenAI SDK leaking into domain code;
- provider abstraction violations;
- float used for money;
- unsafe dynamic evaluation;
- broken audit evidence/traceability;
- previous revisions overwritten;
- tariff interpretations reused as authoritative truth;
- pending documents incorrectly allowing a `CORRECT` invoice;
- automatic Terra -> Sol fallback;
- weak email deduplication;
- idempotency bugs;
- race conditions;
- migration/database problems;
- files lost after Docker rebuild;
- committed secrets/data;
- unsafe uploads;
- weak authentication;
- insufficient tests;
- misleading project status;
- Windows/Linux portability issues.

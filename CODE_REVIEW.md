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
Open.

### Fix commit
Pending.

---

## REVIEW-006 — Login exposto em todas as interfaces não possui limitação de tentativas

**Severity:** MEDIUM
**Status:** OPEN
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
Open.

### Fix commit
Pending.

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
**Status:** OPEN
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
Open.

### Fix commit
Pending.

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

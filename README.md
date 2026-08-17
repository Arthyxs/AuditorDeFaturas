# InvoiceAuditor

Aplicação em construção para auditoria de faturas logísticas. O runtime canônico usa uma imagem
compartilhada pelos processos `app` e `worker`, acompanhada de PostgreSQL no Docker
Compose. A fundação, autenticação, storage imutável, catálogo de tarifários e fila durável
PostgreSQL estão operacionais; regras tarifárias e integrações de entrada/auditoria pertencem aos
próximos milestones.

## Requisitos de desenvolvimento

- Python 3.12 ou superior;
- Node.js 20.19 ou superior;
- npm 11 ou compatível.
- Docker Engine com Docker Compose.

## Runtime canônico

Para a primeira instalação, use o script do sistema operacional. Ele cria `.env`, gera os
segredos internos, preserva valores existentes em execuções posteriores, cria os
diretórios persistentes e inicia o Compose:

```powershell
.\scripts\setup.ps1
```

```bash
./scripts/setup.sh
```

Os scripts solicitam host/usuário/senha IMAP e chave OpenAI sem imprimir valores secretos.
Também aceitam as variáveis `INVOICE_AUDITOR_SETUP_IMAP_HOST`,
`INVOICE_AUDITOR_SETUP_IMAP_USER`, `INVOICE_AUDITOR_SETUP_IMAP_PASSWORD` e
`INVOICE_AUDITOR_SETUP_OPENAI_API_KEY` para instalação não interativa. `.env` é local e
ignorado pelo Git; `.env.example` contém somente valores públicos e campos vazios.
Os scripts restringem o `.env` a modo `0600` no Linux e, no Windows, a ACL do usuário
atual, SYSTEM e administradores locais; a instalação falha se essa proteção não puder ser
aplicada.

Em redes com inspeção TLS, configure a CA oficial fora do repositório em
`INVOICE_AUDITOR_BUILD_CA_PATH` ou forneça o PEM por
`INVOICE_AUDITOR_BUILD_CA_PEM`. O setup entrega a CA ao BuildKit como secret somente
durante `npm ci`/`pip install`; ela não entra nas camadas da imagem. Nunca desabilite a
verificação TLS nem versione certificados internos.

Após a configuração inicial:

```powershell
docker compose up -d --build
docker compose ps
```

O processo web é publicado somente no loopback por padrão, e o bundle React fica disponível em
`http://localhost:8000`; o liveness está em
`http://localhost:8000/api/health/live`. Os três serviços possuem health checks. O banco
usa volume nomeado e todo o `STORAGE_ROOT` usa um único bind mount sob `data/`, que é
ignorado pelo Git.

As configurações são validadas antes do processo iniciar. `APP_SECRET_KEY`,
`FIRST_ADMIN_BOOTSTRAP_TOKEN`, `POSTGRES_PASSWORD` e `DATABASE_URL` são obrigatórios;
placeholders, segredos internos
curtos, timezone desconhecido e URL de banco fora de `postgresql+psycopg` são rejeitados.
Representações e resumos operacionais mantêm valores secretos redigidos.

## Banco e migrations

PostgreSQL é o único banco operacional. Mudanças de schema usam Alembic e os scripts de
setup executam automaticamente o upgrade até a revisão atual. Para operação manual:

```powershell
docker compose exec -T app alembic current
docker compose exec -T app alembic upgrade head
```

A fundação usa UUID gerado pela aplicação, timestamps com timezone apresentados em UTC
pela sessão do banco, JSONB, enums de string com constraints nomeadas e `Decimal` mapeado
por padrão para `NUMERIC(20,6)`. A revisão inicial estabelece a linhagem Alembic; tabelas de
produto serão adicionadas somente nos milestones responsáveis por seus invariantes.

## Primeiro acesso e autenticação

O setup gera e preserva em `.env` o token secreto `FIRST_ADMIN_BOOTSTRAP_TOKEN`. No
primeiro acesso, a interface solicita esse token, um usuário e uma senha de pelo menos 12
caracteres. O fluxo cria um único `ADMIN`; depois disso ele permanece fechado, inclusive
para tentativas concorrentes. Não há credenciais de produção predefinidas.

Senhas usam Argon2id. Sessões ficam no PostgreSQL com token opaco armazenado no navegador
por cookie HTTPOnly, SameSite Strict e Secure quando `APP_BASE_URL` usa HTTPS; o banco
guarda somente o SHA-256 do token. Logout revoga a sessão no servidor. Rotas podem exigir
`ADMIN`, `OPERATOR` ou `VIEWER`, e mutações autenticadas validam a origem configurada.

## Storage local e uploads

`StorageProvider` mantém a aplicação independente do backend de arquivos;
`LocalStorageProvider` é o adapter operacional inicial sob `STORAGE_ROOT`. O limite padrão
de upload é 25 MiB e pode ser reduzido por `UPLOAD_MAX_SIZE_BYTES`. Arquivos aceitos recebem
UUID e nome interno, são gravados por streaming com SHA-256 e `fsync`, e o blob com seu
sidecar de metadata é publicado por rename atômico no mesmo filesystem. Leituras conferem
novamente tamanho e hash antes de retornar bytes.

Uploads aceitam tecnicamente PDF, XLSX, XLS, CSV, PNG, JPEG e TIFF, com conferência de nome,
extensão, MIME declarado e parse estrutural por bibliotecas específicas, sem executar conteúdo.
Traversal, conteúdo divergente, documentos fabricados ou truncados, XML perigoso, ZIPs com
expansão insegura, polyglots detectáveis, formatos executáveis e tamanho excedido são rejeitados.
Arquivos persistidos não recebem bits de execução. Exclusão física é negada sem motivo explícito
e confirmação de referências liberadas.

## Catálogo de tarifários

As rotas autenticadas `/api/tariffs` permitem upload múltiplo, lista paginada e filtrável,
detalhe, download com nova verificação de integridade, edição de descrição/observação,
ativação, nova versão append-only e soft delete. `ADMIN` e `OPERATOR` podem alterar o catálogo;
`VIEWER` possui somente leitura. Nomes originais repetidos são permitidos e nunca determinam
identidade ou versão. Um novo arquivo de versão recebe novo blob e registro ligados ao anterior;
PATCH nunca sobrescreve bytes e DELETE nunca remove fisicamente o original.

Depois da autenticação, a SPA apresenta esse catálogo com busca e filtro de status, detalhe,
hash completo, histórico de versões, download e indicação de uso quando houver auditorias
relacionadas. Uploads múltiplos mostram andamento e erro por arquivo. Controles de edição,
ativação e remoção aparecem somente para `ADMIN` e `OPERATOR`; `VIEWER` permanece em leitura.

## Worker durável

O worker usa exclusivamente PostgreSQL: `processing_jobs` possui chave idempotente única, estados
explícitos, disponibilidade agendada, tentativas, backoff, lease/heartbeat e erro terminal. Dois
processos disputam trabalho com `FOR UPDATE SKIP LOCKED`, e leases abandonados voltam para retry
ou falham ao atingir o limite. Cada handler mantém ainda um lock advisory de sessão liberado pelo
PostgreSQL quando o processo desconecta; a recuperação de lease não pode reexecutar concorrentemente
um handler ainda ativo. Locks advisory transacionais por UUID impedem processamento simultâneo da
mesma fatura.

O modo contínuo respeita `WORKER_POLL_INTERVAL_SECONDS`; a janela do scheduler usa
`EMAIL_CHECK_INTERVAL_MINUTES`. Uma execução limitada processa no máximo um job:

```powershell
docker compose run --rm worker python -m app.worker.main --once
```

`ADMIN` e `OPERATOR` podem enfileirar um tick manual por `POST /api/worker/run-now`; uma chave
opcional do cliente torna retries HTTP idempotentes. O tick de M09 estabelece somente a fronteira
durável de agendamento/controle. Polling IMAP e seus handlers pertencem ao M10 e posteriores.

## Backend

Crie e ative um ambiente virtual e instale o projeto com as dependências de desenvolvimento:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

Comandos de qualidade e execução:

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m mypy
.venv\Scripts\python -m uvicorn app.main:app --reload
```

O verificador de tipos Python escolhido é o **mypy**, configurado em modo estrito no
`pyproject.toml`. A mesma configuração cobre `app/` e `tests/`.

## Frontend

```powershell
cd frontend
npm install
npm run lint
npm run typecheck
npm run build
npm run dev
```

O build de produção é gerado em `frontend/dist/`, diretório ignorado pelo Git.

## Limites atuais

IMAP, classificação/movimentação, entrada canônica, seleção semântica e ferramentas documentais
genéricas estão implementados até M16.
ADMIN/OPERATOR podem enviar uma fatura manual por `POST /api/invoices/manual`; o canal manual e o
IMAP preservam originais/origem e usam o mesmo pipeline sem e-mail fictício. A integração de IA
continua testável com provider fake. As ferramentas de PDF, planilha e imagem operam somente sobre
originais verificados e retornam coordenadas reproduzíveis; cálculo, auditoria e relatórios começam
em M17.

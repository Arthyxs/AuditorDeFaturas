# InvoiceAuditor

Base executável do auditor de faturas logísticas. O runtime canônico usa uma imagem
compartilhada pelos processos `app` e `worker`, acompanhada de PostgreSQL no Docker
Compose. Regras de negócio e integrações ainda pertencem aos próximos milestones.

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

Após a configuração inicial:

```powershell
docker compose up -d --build
docker compose ps
```

O processo web fica disponível em `http://localhost:8000` e seu liveness em
`http://localhost:8000/api/health/live`. Os três serviços possuem health checks. O banco
usa volume nomeado e os diretórios operacionais usam bind mounts sob `data/`, que é
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
extensão, MIME declarado e estrutura/assinatura mínima. Traversal, conteúdo divergente,
arquivos vazios/truncados, ZIPs com expansão insegura, formatos executáveis e tamanho
excedido são rejeitados. Arquivos persistidos não recebem bits de execução. Exclusão física
é negada sem motivo explícito e confirmação de referências liberadas; soft delete pertence
às entidades de produto dos próximos milestones.

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

Esta etapa não expõe catálogo/API de tarifários, faturas ou auditoria, jobs duráveis, integrações ou
regras de auditoria. O worker do M02 publica somente o heartbeat de processo
necessário para validar o runtime; scheduling e jobs começam nos milestones próprios.

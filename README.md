# InvoiceAuditor

Base executável do auditor de faturas logísticas. O M01 contém somente o esqueleto
definitivo do backend e do frontend e seus gates de qualidade; regras de negócio,
persistência, integrações e runtime Docker do projeto pertencem aos próximos milestones.

## Requisitos de desenvolvimento

- Python 3.12 ou superior;
- Node.js 20.19 ou superior;
- npm 11 ou compatível.

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

Esta etapa não expõe APIs de produto, autenticação, persistência, worker, integrações ou
regras de auditoria. O runtime Docker Compose e o endpoint de liveness começam no M02.

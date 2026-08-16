# InvoiceAuditor — Agent Instructions

The authoritative product specification for this repository is:

`ESPECIFICACAO_COMPLETA_AUDITOR_FATURAS_V3.md`

Treat that specification as immutable unless the user explicitly requests a change to the product requirements.

The repository is the source of truth. Chat history is not.

Before making architectural or implementation decisions, read the relevant repository files and inspect the actual codebase.

---

## 1. Files that must be read at the start of a new development chat

Read, in this order:

1. `AGENTS.md`
2. `ESPECIFICACAO_COMPLETA_AUDITOR_FATURAS_V3.md` — relevant sections at minimum; read fully when making architectural decisions
3. `IMPLEMENTATION_PLAN.md`
4. `PROJECT_STATUS.md`
5. `DECISIONS.md`
6. `CODE_REVIEW.md` when it contains unresolved findings

Then inspect:

- `git status`
- recent `git log`
- current tests
- current Docker state when relevant

Do not rely on previous chat history to infer project state.

---

## 2. Product principles that must not be silently changed

- Build a production-oriented product, not a disposable prototype.
- The primary goal is to determine whether invoice charges are correct or incorrect and identify the exact CT-e/AWB/document-level divergences.
- Never silently simplify or remove a requirement from the specification.
- Do not create fixed parsers per partner.
- Do not depend on email subject text alone for classification.
- Every invoice audit must reinterpret the selected original tariff files independently.
- Never reuse a previous tariff interpretation as authoritative truth for a new invoice.
- Previous tariff interpretations may be stored and compared only for historical/audit consistency checks.
- AI interprets business/document rules; deterministic backend tools perform arithmetic whenever possible.
- Never use Python `float` for money. Use `Decimal`.
- PostgreSQL monetary fields must use `NUMERIC/DECIMAL`.
- Original emails, attachments, tariff files, audit results and previous report revisions must remain traceable and immutable.
- A pending or ambiguous CT-e/AWB/document must never silently make an invoice `CORRECT`.
- GPT-5.6 Terra is the default audit model through configuration.
- GPT-5.6 Sol is manual advanced reanalysis through the frontend.
- Do not implement automatic Terra -> Sol fallback unless the user explicitly changes this requirement.
- AI provider, model names, email provider and storage provider must remain replaceable behind interfaces/adapters.
- OpenAI-specific SDK usage must remain inside the OpenAI provider/integration layer.
- Local filesystem storage is the operational storage provider for the initial release.
- Docker Compose is the canonical runtime environment.
- PostgreSQL schema changes must use migrations.
- Never commit credentials, `.env`, API keys, passwords, real production documents or secrets.

---

## 3. Architecture discipline

Prefer straightforward, maintainable architecture.

Do not add the following unless there is a demonstrated technical need or the specification is explicitly changed:

- Kubernetes
- Redis
- Celery
- RabbitMQ
- Kafka
- microservices
- distributed queues

Keep business/domain logic independent from infrastructure integrations.

Expected replaceable boundaries include at minimum:

- `AIProvider`
- `EmailProvider`
- `StorageProvider`

---

## 4. Implementation workflow

Work in milestones defined in `IMPLEMENTATION_PLAN.md`.

Before implementing a milestone:

1. Read the relevant specification sections.
2. Inspect the existing implementation.
3. Inspect related tests and migrations.
4. Confirm the milestone dependencies are already satisfied.
5. Do not advance into unrelated future milestones.

During implementation:

- Keep the application runnable.
- Prefer small coherent changes.
- Add or update tests with the implementation.
- Treat errors explicitly.
- Do not present mocks/placeholders as completed core functionality.
- Do not hardcode model names outside configuration.
- Do not hardcode partner-specific invoice/tariff business rules.

---

## 5. Definition of done for a milestone

A milestone is not complete until all applicable steps below are finished:

1. Implementation satisfies its acceptance criteria.
2. Relevant tests pass.
3. Lint/type checks pass when configured.
4. Database migrations are valid when applicable.
5. Docker build succeeds when applicable.
6. Docker Compose services start correctly when applicable.
7. No secrets or production data are staged.
8. `PROJECT_STATUS.md` is updated.
9. `IMPLEMENTATION_PLAN.md` is updated.
10. `DECISIONS.md` is updated if a meaningful architectural/product decision occurred.
11. `CODE_REVIEW.md` is updated when resolving review findings.
12. A clear Git commit is created.
13. The commit is pushed to the configured GitHub remote.
14. The resulting commit hash is recorded in `PROJECT_STATUS.md`.

Never mark a milestone complete with knowingly failing tests or a knowingly broken repository.

---

## 6. Git rules

Use clear Conventional Commit-style messages where practical:

- `feat:`
- `fix:`
- `refactor:`
- `test:`
- `docs:`
- `chore:`

For large milestones, stable intermediate checkpoint commits are allowed and encouraged.

Before every commit:

- inspect `git status`;
- inspect the staged diff;
- ensure `.env`, secrets, credentials, production data and temporary files are not included.

Do not rewrite, squash or force-push previously completed milestone history unless explicitly requested by the user.

---

## 7. Persistent project memory

Maintain these files continuously:

### `IMPLEMENTATION_PLAN.md`

Contains milestones, dependencies, scope, acceptance criteria, test requirements and completion status.

### `PROJECT_STATUS.md`

Must always contain:

- current project phase;
- current milestone;
- completed milestones;
- unfinished work;
- known issues;
- test status;
- Docker/build status;
- last stable Git commit;
- next recommended action.

### `DECISIONS.md`

Record important architecture/product decisions in ADR-style entries.

### `CODE_REVIEW.md`

Used for periodic independent reviews and unresolved findings.

---

## 8. Documentation

Keep documentation consistent with the implementation.

When relevant, update:

- `README.md`
- `INSTALL.md`
- `ARCHITECTURE.md`
- `SECURITY.md`
- `CHANGELOG.md`

Never claim a feature is operational when it is only stubbed or mocked.

---

## 9. Security requirements

Never expose or log API keys, IMAP passwords, database passwords, auth secrets or session tokens.

Uploads must be validated and must never be executed.

Original user/business documents must remain outside Git.

---

## 10. Stop conditions

Stop and document instead of inventing behavior when:

- required external credentials are unavailable;
- a document format is unsupported;
- a business rule cannot be resolved safely;
- required information is missing;
- the specification contains a genuine contradiction that prevents safe implementation.

Record the blocker in `PROJECT_STATUS.md` and explain the exact missing information.

---

## 11. End-of-session discipline

Before ending a long implementation session, even if the milestone is not complete:

1. leave the repository in a clear state;
2. run the relevant tests if practical;
3. update `PROJECT_STATUS.md`;
4. record unresolved problems;
5. record the exact next action;
6. create a stable checkpoint commit when appropriate;
7. push the checkpoint when it is safe and useful.

Never rely on chat history as the only record of unfinished work.

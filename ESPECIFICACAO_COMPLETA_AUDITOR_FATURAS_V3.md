# Especificação Técnica Completa — Auditor Automático de Faturas Logísticas

**Versão:** 3.0  
**Data:** 14 de agosto de 2026  
**Status:** Especificação fechada para implementação  
**Idioma:** Português do Brasil  
**Nome provisório:** Auditor de Faturas Logísticas  
**Objetivo deste documento:** servir como especificação funcional, técnica e arquitetural completa para um agente de código implementar a aplicação como produto real, Dockerizado, utilizável localmente no Windows e facilmente migrável para um servidor Linux.

---

# 1. Missão do produto

Construir uma aplicação capaz de receber automaticamente e-mails por IMAP, classificar mensagens, identificar faturas e avisos de vencimento, armazenar documentos originais, selecionar entre os tarifários disponíveis aqueles provavelmente aplicáveis, interpretar **do zero** a fatura e o(s) tarifário(s) em cada auditoria, auditar a cobrança por documento interno e produzir relatórios persistentes, rastreáveis, editáveis e reanalisáveis.

O produto não deve depender de layout fixo de fatura, título padronizado de e-mail, parser específico por parceiro nem regra tarifária cadastrada manualmente.

A inteligência artificial é responsável por interpretar documentos heterogêneos e regras comerciais. O software é responsável por orquestração, persistência, segurança, rastreabilidade, cálculos, interface, versionamento e operação.

---

# 2. OBJETIVO 001 — prioridade absoluta

> **Determinar se a cobrança de cada fatura está correta ou errada. Quando estiver errada, identificar exatamente quais CT-es, AWBs ou documentos equivalentes estão divergentes, quanto foi cobrado, quanto deveria ter sido cobrado, qual é a diferença e qual regra/evidência do tarifário fundamenta essa conclusão.**

O sistema deve auditar:

1. a fatura como um todo;
2. cada documento que compõe a fatura;
3. cada componente de cobrança identificado dentro do documento, quando possível.

Exemplos de unidades auditáveis:

- CT-e;
- AWB;
- CTRC;
- conhecimento de transporte;
- remessa;
- embarque;
- viagem;
- documento equivalente utilizado pelo parceiro.

Nenhum recurso secundário pode comprometer o Objetivo 001.

---

# 3. Objetivos complementares

O sistema também deve:

1. separar os e-mails automaticamente em pastas;
2. identificar o parceiro da cobrança;
3. localizar o(s) tarifário(s) mais provável(is) a partir de um catálogo de arquivos disponíveis;
4. aceitar tarifários em múltiplos formatos e múltiplos arquivos complementares;
5. compreender regras territoriais, faixas de peso, cubagem, GRIS, ad valorem, pedágio, adicionais, mínimos, exceções e regras descritas em texto, tabelas ou planilhas;
6. detectar quando faltam dados;
7. nunca classificar como correta uma cobrança inconclusiva;
8. permitir reanálise manual usando modelo avançado;
9. armazenar todas as versões de auditoria;
10. armazenar a interpretação auditável feita pela IA;
11. detectar inconsistências entre interpretações do mesmo tarifário em auditorias diferentes;
12. permitir observações/correções humanas sem destruir histórico;
13. calcular margem bruta do frete quando houver receita/valor de venda disponível;
14. acompanhar tokens, custo estimado e modelo utilizado;
15. permitir troca de modelo e fornecedor de IA sem reescrever o sistema;
16. funcionar no Windows local por Docker e migrar para Linux/VPS sem alteração estrutural;
17. possuir frontend web operacional;
18. possuir gestão de tarifários pelo frontend.

---

# 4. Princípios arquiteturais não negociáveis

## 4.1 Não criar parser por parceiro

É proibido estruturar o sistema como:

```text
Parceiro A -> parser A
Parceiro B -> parser B
Parceiro C -> parser C
```

Novos formatos devem ser suportados sem alteração de código.

## 4.2 Não depender do assunto do e-mail

A classificação deve considerar, conforme disponível:

- remetente;
- destinatário;
- assunto;
- corpo textual;
- corpo HTML;
- histórico/thread;
- cabeçalhos;
- nomes dos anexos;
- conteúdo/prévia dos anexos;
- tipo MIME;
- contexto geral.

Um assunto `RE: Movimentações Julho` pode conter uma fatura.

## 4.3 O tarifário é reinterpretado em cada auditoria

**A primeira interpretação de um tarifário nunca vira verdade permanente.**

Para cada nova fatura:

```text
fatura atual
+
anexos atuais
+
tarifário(s) original(is)
+
contexto do e-mail
        ↓
nova interpretação independente
        ↓
nova auditoria
```

Interpretações anteriores ficam armazenadas para histórico e comparação, não como regra oficial automática.

## 4.4 IA interpreta; software calcula

A IA decide:

- qual regra se aplica;
- região/faixa;
- entradas do cálculo;
- componentes;
- fórmula/estrutura lógica.

A aritmética deve ser executada por ferramenta determinística do backend sempre que possível.

## 4.5 Nunca forçar conclusão

A IA deve poder retornar estados inconclusivos.

É melhor `PENDENTE` que aprovar uma cobrança errada.

## 4.6 Originais imutáveis

E-mails, anexos e tarifários utilizados nunca são sobrescritos.

## 4.7 Dinheiro nunca usa float

Usar `Decimal` no Python e `NUMERIC/DECIMAL` no PostgreSQL.

## 4.8 Providers substituíveis

O domínio não deve depender diretamente de OpenAI, Google, Anthropic, servidor IMAP específico ou storage específico.

---

# 5. Stack recomendada

## Backend

- Python 3.12+;
- FastAPI;
- Pydantic;
- SQLAlchemy 2;
- Alembic;
- PostgreSQL;
- HTTPX;
- IMAP encapsulado em provider;
- `Decimal` para valores financeiros.

## Frontend

- React;
- TypeScript;
- Vite;
- interface responsiva;
- nenhuma regra financeira crítica no frontend.

## Documentos

- PyMuPDF para PDF;
- openpyxl para XLSX;
- pandas somente quando útil;
- suporte a CSV;
- suporte a XLS quando viável;
- PNG/JPEG/TIFF;
- originais preservados.

OCR local não é obrigatório no primeiro release. PDFs digitalizados devem inicialmente usar visão multimodal da IA.

## Infraestrutura

- Docker;
- Docker Compose;
- aplicação;
- worker;
- PostgreSQL;
- volumes persistentes;
- health checks.

Não usar Kubernetes, Redis, RabbitMQ ou Celery sem necessidade comprovada.

---

# 6. Estrutura sugerida do repositório

```text
invoice-auditor/
│
├── app/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   ├── api/
│   │   ├── routes/
│   │   └── schemas/
│   ├── domain/
│   │   ├── email/
│   │   ├── invoices/
│   │   ├── tariffs/
│   │   ├── audits/
│   │   ├── reports/
│   │   └── finance/
│   ├── ai/
│   │   ├── interfaces.py
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── prompts/
│   │   │   ├── email_classifier.md
│   │   │   ├── tariff_selector.md
│   │   │   ├── invoice_auditor.md
│   │   │   ├── report_writer.md
│   │   │   └── advanced_reanalysis.md
│   │   └── providers/
│   │       ├── openai_provider.py
│   │       ├── anthropic_provider.py
│   │       └── google_provider.py
│   ├── email/
│   │   ├── interfaces.py
│   │   ├── imap_provider.py
│   │   ├── thread_resolver.py
│   │   └── fingerprint.py
│   ├── storage/
│   │   ├── interfaces.py
│   │   └── local_provider.py
│   ├── documents/
│   │   ├── pdf.py
│   │   ├── spreadsheet.py
│   │   ├── image.py
│   │   ├── metadata.py
│   │   └── tools.py
│   ├── calculation/
│   │   ├── calculator.py
│   │   ├── money.py
│   │   └── tolerance.py
│   ├── reports/
│   │   ├── builder.py
│   │   └── templates/
│   ├── persistence/
│   │   ├── models/
│   │   ├── repositories/
│   │   └── session.py
│   ├── worker/
│   │   ├── main.py
│   │   ├── scheduler.py
│   │   └── jobs/
│   └── services/
│
├── frontend/
│   ├── src/
│   ├── public/
│   └── package.json
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── golden_cases/
├── data/
│   ├── tariffs/
│   ├── invoices/
│   ├── reports/
│   ├── temp/
│   └── backups/
├── scripts/
│   ├── setup.ps1
│   ├── setup.sh
│   ├── backup.sh
│   ├── restore.sh
│   └── smoke_test.py
├── docker-compose.yml
├── Dockerfile
├── .dockerignore
├── .gitignore
├── .env.example
├── README.md
├── INSTALL.md
├── ARCHITECTURE.md
├── SECURITY.md
└── CHANGELOG.md
```

---

# 7. Containers e volumes

## `app`

- FastAPI;
- autenticação;
- frontend;
- gestão;
- relatórios;
- upload de tarifários;
- acionamento de reanálises.

## `worker`

Mesma imagem do backend, executando:

- polling IMAP;
- classificação;
- processamento;
- auditorias;
- tarefas agendadas.

## `postgres`

PostgreSQL com volume persistente.

## Bind mounts/volumes

```yaml
volumes:
  - ./data/tariffs:/app/data/tariffs
  - ./data/invoices:/app/data/invoices
  - ./data/reports:/app/data/reports
  - ./data/backups:/app/data/backups
```

Nenhum documento importante pode existir apenas dentro da camada descartável do container.

---

# 8. Experiência de instalação

Depois de instalar Docker, o usuário deve precisar fornecer essencialmente:

- IMAP host;
- IMAP port;
- SSL/TLS;
- e-mail/usuário;
- senha;
- API key;
- nomes dos modelos/providers.

Segredos internos como senha PostgreSQL e secret da aplicação devem ser gerados pelos scripts de setup.

---

# 9. `.env` esperado

```env
APP_ENV=production
APP_BASE_URL=http://localhost:8000
APP_TIMEZONE=America/Sao_Paulo

APP_SECRET_KEY=
POSTGRES_PASSWORD=

POSTGRES_DB=invoice_auditor
POSTGRES_USER=invoice_auditor
DATABASE_URL=

IMAP_HOST=
IMAP_PORT=993
IMAP_SSL=true
IMAP_USER=
IMAP_PASSWORD=

IMAP_INBOX=INBOX
IMAP_FOLDER_INVOICES=Faturas
IMAP_FOLDER_DUE_NOTICES=Avisos
IMAP_FOLDER_GENERAL=Gerais
IMAP_FOLDER_REVIEW=Revisao

EMAIL_CHECK_INTERVAL_MINUTES=60
EMAIL_PROCESS_BATCH_SIZE=50
WORKER_ENABLED=true

AI_EMAIL_PROVIDER=openai
AI_EMAIL_MODEL=gpt-5.6-luna

AI_TARIFF_SELECTOR_PROVIDER=openai
AI_TARIFF_SELECTOR_MODEL=gpt-5.6-terra

AI_AUDIT_PROVIDER=openai
AI_AUDIT_MODEL=gpt-5.6-terra

AI_ADVANCED_PROVIDER=openai
AI_ADVANCED_MODEL=gpt-5.6-sol

OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_AI_API_KEY=

STORAGE_PROVIDER=local
STORAGE_ROOT=/app/data

AUDIT_ABSOLUTE_TOLERANCE=0.01
AUDIT_PERCENT_TOLERANCE=0

BACKUP_ENABLED=true
BACKUP_RETENTION_DAYS=30
```

Modelos nunca devem ser hardcoded no domínio.

---
# 10. Providers

## 10.1 `AIProvider`

Interface conceitual:

```python
class AIProvider(Protocol):
    async def classify_email(...): ...
    async def select_tariffs(...): ...
    async def audit_invoice(...): ...
    async def reanalyze(...): ...
```

A implementação inicial completa deve ser `OpenAIProvider`.

O restante do sistema não deve importar SDK da OpenAI diretamente.

Adapters Google/Anthropic devem ficar isolados e poder ser implementados sem alteração no domínio.

## 10.2 `EmailProvider`

Responsável por:

- listar mensagens;
- obter mensagem completa;
- obter cabeçalhos;
- baixar anexos;
- mover mensagens;
- criar pasta;
- recuperar UID/UIDVALIDITY;
- recuperar thread quando possível.

Implementação inicial: `IMAPEmailProvider`.

## 10.3 `StorageProvider`

Responsável por:

- salvar;
- abrir;
- listar;
- calcular hash;
- recuperar caminho;
- metadata;
- exclusão controlada.

Implementação inicial: `LocalStorageProvider`.

Futuramente podem existir S3/Drive/Azure sem mudar o núcleo.

---

# 11. Deduplicação de e-mails

A combinação:

```text
assunto + remetente + data/hora de recebimento
```

é parte útil da impressão digital, mas **não é garantia suficiente isoladamente**.

Guardar:

- mailbox/account ID;
- UIDVALIDITY;
- UID;
- Message-ID, se existir;
- Date;
- received_at do servidor, quando disponível;
- remetente normalizado;
- assunto normalizado;
- hash do corpo;
- hashes dos anexos;
- hash canônico final.

## Server key

```text
mailbox_id + UIDVALIDITY + UID
```

## Canonical content fingerprint

Calcular SHA-256 de JSON canônico contendo:

```text
sender_normalized
subject_normalized
header_date
received_at
message_id_if_available
normalized_body_hash
sorted_attachment_sha256_list
```

Regra:

- se `server_key` já existe -> duplicado;
- ou se `canonical_content_fingerprint` já existe -> duplicado.

Isso cobre mensagens movidas de pasta/UID e reduz colisões.

---

# 12. Threads e respostas

Usar:

- Message-ID;
- In-Reply-To;
- References;
- assunto normalizado;
- participantes;
- proximidade temporal.

Fornecer contexto suficiente ao classificador quando a mensagem atual for resposta.

Não enviar histórico ilimitado.

---

# 13. Classificação de e-mails

Modelo padrão: Luna configurável.

Classes:

```text
INVOICE
DUE_NOTICE
GENERAL
MANUAL_REVIEW
```

Saída estruturada:

```json
{
  "classification": "INVOICE",
  "confidence": 0.97,
  "partner": {
    "name": "JPC Transportes",
    "document_id": null
  },
  "invoice_attachment_ids": ["att_123"],
  "supporting_attachment_ids": ["att_124"],
  "summary": "Mensagem encaminha cobrança de transportes.",
  "evidence": [
    "Anexo contém lista de CT-es e total",
    "Corpo informa vencimento"
  ]
}
```

Baixa confiança -> `MANUAL_REVIEW`.

---

# 14. Movimentação IMAP

```text
INVOICE       -> Faturas
DUE_NOTICE    -> Avisos
GENERAL       -> Gerais
MANUAL_REVIEW -> Revisao
```

Nomes configuráveis.

A movimentação nunca deve apagar o registro local.

---

# 15. Tarifários

Armazenamento local persistente e gestão por frontend.

Formatos:

- PDF;
- XLSX;
- XLS;
- CSV;
- PNG/JPEG;
- TIFF, se possível.

Metadata:

- ID;
- nome original;
- nome interno;
- extensão;
- MIME;
- tamanho;
- SHA-256;
- upload;
- usuário;
- ativo/inativo;
- descrição opcional;
- observação;
- caminho;
- versão;
- soft delete.

Organização:

```text
/data/tariffs/
    000001/JPC-2026.pdf
    000002/JPC-Reajuste-2026.pdf
    000003/Tabela-Cidades.xlsx
```

---

# 16. Catálogo automático de tarifários

O sistema gera JSON a partir do banco:

```json
[
  {
    "id": "tar_000001",
    "filename": "JPC-2026.pdf",
    "extension": "pdf",
    "description": null,
    "active": true
  },
  {
    "id": "tar_000002",
    "filename": "JPC-Reajuste-Jul-2026.pdf",
    "extension": "pdf",
    "description": null,
    "active": true
  }
]
```

**Não exigir mapeamento manual parceiro -> tarifário.**

---

# 17. Seleção semântica do tarifário

Entrada:

- parceiro provável;
- data;
- origem/destino se conhecida;
- metadata da fatura;
- catálogo.

Saída:

```json
{
  "selected_tariff_ids": ["tar_000001", "tar_000002"],
  "confidence": 0.96,
  "reason": "Arquivos parecem corresponder ao parceiro e vigência."
}
```

Nenhum candidato -> `PENDING_NO_TARIFF`.

Somente os arquivos escolhidos são carregados para auditoria.

---

# 18. Regra central do tarifário

**Os arquivos originais selecionados devem ser reinterpretados em toda auditoria.**

```text
Auditoria A: JPC-2026.pdf -> interpretação A
Auditoria B: JPC-2026.pdf -> interpretação B
```

A interpretação A não vira regra oficial da B.

Caching técnico do provider é permitido desde que o documento original continue sendo o contexto semântico da auditoria.

---

# 19. Interpretação auditável da IA

Não persistir cadeia de pensamento privada.

Persistir uma justificativa estruturada:

- fatos extraídos;
- regra identificada;
- página/aba/célula;
- premissas;
- ambiguidades;
- região;
- faixa;
- peso;
- taxas;
- chamadas de cálculo;
- resultados;
- resumo explicativo;
- confiança por decisão quando disponível.

Exemplo:

```json
{
  "destination_region": "Vale do Aço",
  "evidence": [
    {
      "file_id": "tar_000001",
      "page": 7,
      "description": "Ipatinga aparece na relação Vale do Aço."
    }
  ],
  "weight_rule": {
    "type": "greater_of_real_or_cubic",
    "cubic_factor": 300
  },
  "charges": [
    {
      "name": "GRIS",
      "rule": "0,30% do valor da mercadoria, mínimo R$ 40"
    }
  ]
}
```

---

# 20. Incoerência entre auditorias

Comparar campos estruturados da nova interpretação com históricos do mesmo tarifário.

Exemplo:

```text
#100: Ipatinga -> Região 3
#124: Ipatinga -> Região 4
```

Criar alerta:

```text
INTERPRETATION_INCONSISTENCY
```

Não decidir automaticamente qual interpretação é correta.

---

# 21. Documentos internos da fatura

Criar uma unidade `invoice_document` para cada:

- CT-e;
- AWB;
- CTRC;
- remessa;
- conhecimento;
- documento equivalente.

A fatura pode conter um ou centenas.

---

# 22. Campos canônicos por documento

Tentar normalizar:

```text
document_type
document_number
issue_date
origin_city
origin_state
destination_city
destination_state
origin_zip
destination_zip
real_weight
cubic_weight
chargeable_weight_declared
invoice_value
merchandise_value
volume_count
amount_charged
our_freight_revenue
currency
```

Campos ausentes permanecem nulos.

Nunca inventar.

---

# 23. Componentes de cobrança

Quando possível decompor:

```text
base_freight
weight_freight
minimum_freight
gris
ad_valorem
toll
dispatch
collection_fee
delivery_fee
difficult_access
fuel_surcharge
re-delivery
tax
other
```

Guardar nome original e normalizado.

---

# 24. Resultado por documento

Status:

```text
CORRECT
INCORRECT
PENDING_MISSING_INFO
PENDING_AMBIGUITY
PENDING_NO_TARIFF
MANUAL_REVIEW
ERROR
```

Para `INCORRECT`, obrigatoriamente:

- cobrado;
- esperado;
- diferença;
- componentes divergentes;
- regra;
- evidência;
- justificativa.

---

# 25. Consolidação da fatura

1. qualquer documento `INCORRECT` -> fatura `INCORRECT`;
2. nenhum incorreto, mas algum pendente -> `PENDING`;
3. somente todos corretos -> `CORRECT`;
4. impossível identificar unidades -> `MANUAL_REVIEW` ou `NOT_AUDITABLE`.

Nunca marcar correta se houver parte pendente.

---

# 26. Validação dos totais

Comparar quando possível:

```text
soma cobrados por documento vs total fatura
soma esperados vs total esperado
```

Diferença não explicada deve gerar alerta.

---

# 27. Calculadora determinística

Não usar `eval()` irrestrito.

Suportar operações autorizadas:

- soma;
- subtração;
- multiplicação;
- divisão;
- max/min;
- arredondamento;
- ceil/floor;
- percentuais;
- comparação;
- `Decimal`.

A IA solicita cálculo em estrutura declarativa.

---

# 28. Localidade/região

Prioridade:

1. definição do tarifário;
2. lista de cidades/CEPs do tarifário;
3. regra comercial do parceiro;
4. fonte externa apenas como apoio.

Região comercial do tarifário prevalece sobre classificação geográfica genérica.

---

# 29. Peso taxável

Não impor regra universal.

Guardar:

- peso real;
- cubado;
- fator;
- taxável declarado;
- usado;
- justificativa;
- evidência.

Se faltar informação necessária, pendência.

---

# 30. Margem bruta do frete

Quando houver receita do nosso frete:

```text
margem_bruta_efetiva = receita_frete - custo_parceiro_cobrado
margem_bruta_esperada = receita_frete - custo_parceiro_esperado
impacto_divergencia = custo_parceiro_cobrado - custo_parceiro_esperado
margem_percentual = margem_bruta_efetiva / receita_frete
```

Chamar de **margem bruta do frete**, não lucro contábil.

Não estimar receita ausente.

---

# 31. Relatório por CT-e/AWB

Deve mostrar:

- documento;
- status;
- origem/destino;
- pesos;
- cobrado;
- esperado;
- diferença;
- tarifários;
- componentes;
- divergências;
- evidências;
- cálculo;
- margem;
- pendências.

---

# 32. Relatório por fatura

Consolidar:

- parceiro;
- número;
- datas;
- vencimento;
- cobrado;
- esperado;
- diferença;
- tarifários;
- documentos totais;
- corretos/incorretos/pendentes;
- divergências;
- interpretação;
- inconsistências;
- margem agregada;
- modelo;
- tokens/custo;
- revisão;
- data/hora.

---

# 33. Relatório no banco

Fonte de verdade:

```text
report_json
```

Também guardar:

```text
report_html
```

PDF é exportação, não fonte de verdade.

---

# 34. Edição de relatório

Nunca sobrescrever original.

```text
revision 1 -> IA
revision 2 -> operador
```

Guardar:

- usuário;
- horário;
- campo anterior;
- campo novo;
- motivo.

---

# 35. Reanálise

Frontend:

```text
[ Reanalisar com Terra ]
[ Reanalisar com Sol ]
```

**Sem fallback automático Terra -> Sol.**

Operador decide quando usar modelo avançado.

---

# 36. Reanálise específica

Permitir reanalisar somente um documento.

Campo opcional:

```text
Observação do operador
```

Enviar contexto, originais, tarifários, resultado anterior e nota.

Nova revisão, sem apagar anterior.

---

# 37. Reanálise completa

Disponível quando:

- novo tarifário;
- arquivo adicional;
- incoerência;
- segunda opinião;
- troca de modelo;
- correção humana.

---

# 38. Histórico de auditoria

Cada run:

```text
audit_run_id
invoice_id
revision
provider
model
prompt_version
started_at
finished_at
status
initiated_by
reason
```

---

# 39. Controle de prompts

Prompts versionados em arquivos.

Guardar em cada call:

```text
prompt_name
prompt_version
prompt_hash
```

---

# 40. Chamadas de IA e custo

Tabela `ai_calls`:

- provider;
- model;
- task;
- request id;
- horário;
- duração;
- input tokens;
- cached input;
- output tokens;
- custo estimado;
- status;
- erro;
- prompt version;
- audit run.

Nunca guardar API key.

Preços por modelo devem estar em configuração/tabela versionada por vigência.

---
# 41. Modelo de dados recomendado

## `users`

- id;
- name;
- email;
- password_hash;
- role;
- active;
- created_at.

Roles:

```text
ADMIN
OPERATOR
VIEWER
```

## `mail_accounts`

- id;
- display_name;
- host;
- port;
- ssl;
- username;
- active.

## `mail_messages`

- id;
- mail_account_id;
- uidvalidity;
- uid;
- message_id;
- subject;
- normalized_subject;
- sender;
- recipients;
- header_date;
- received_at;
- body_text;
- server_key;
- content_fingerprint;
- classification;
- classification_confidence;
- partner_name;
- status;
- original_folder;
- current_folder;
- created_at.

## `mail_attachments`

- id;
- mail_message_id;
- filename;
- mime_type;
- size;
- sha256;
- storage_path;
- created_at.

## `tariff_files`

- id;
- original_filename;
- internal_filename;
- extension;
- mime_type;
- size;
- sha256;
- storage_path;
- description;
- active;
- uploaded_by;
- created_at;
- updated_at;
- deleted_at.

## `partners`

- id;
- normalized_name;
- document_id;
- aliases JSONB;
- created_at.

Serve para histórico/agregação, não para obrigar mapeamento de tarifário.

## `invoices`

- id;
- mail_message_id;
- partner_id;
- partner_name_raw;
- invoice_number;
- issue_date;
- due_date;
- currency;
- amount_charged;
- amount_expected;
- difference;
- status;
- active_audit_run_id;
- created_at.

## `invoice_documents`

- id;
- invoice_id;
- document_type;
- document_number;
- issue_date;
- origin_city/state;
- destination_city/state;
- origin_zip;
- destination_zip;
- real_weight;
- cubic_weight;
- chargeable_weight;
- merchandise_value;
- amount_charged;
- amount_expected;
- difference;
- our_freight_revenue;
- gross_margin_actual;
- gross_margin_expected;
- status;
- source_reference JSONB.

## `document_charge_items`

- id;
- invoice_document_id;
- name_raw;
- name_normalized;
- charged_amount;
- expected_amount;
- difference;
- status;
- evidence JSONB.

## `audit_runs`

- id;
- invoice_id;
- revision;
- provider;
- model;
- prompt_version;
- status;
- initiated_by;
- reason;
- started_at;
- finished_at;
- total_input_tokens;
- total_output_tokens;
- estimated_cost;
- currency.

## `audit_document_results`

- id;
- audit_run_id;
- invoice_document_id;
- status;
- charged_amount;
- expected_amount;
- difference;
- interpretation JSONB;
- evidence JSONB;
- assumptions JSONB;
- ambiguities JSONB;
- missing_information JSONB;
- calculation_trace JSONB;
- explanation;
- confidence JSONB.

## `tariff_interpretations`

- id;
- audit_run_id;
- tariff_file_id;
- interpretation JSONB;
- normalized_fingerprint JSONB;
- evidence JSONB;
- created_at.

Histórico; nunca regra oficial automática.

## `interpretation_inconsistencies`

- id;
- tariff_file_id;
- audit_run_a_id;
- audit_run_b_id;
- field;
- value_a;
- value_b;
- severity;
- status;
- created_at;
- resolved_at;
- resolution_note.

## `pending_items`

- id;
- invoice_id;
- invoice_document_id;
- audit_run_id;
- type;
- description;
- required_information;
- status;
- created_at;
- resolved_at.

## `reports`

- id;
- invoice_id;
- audit_run_id;
- revision;
- report_json JSONB;
- report_html;
- created_by;
- created_at.

## `report_revisions`

- id;
- report_id;
- revision;
- changed_by;
- changes JSONB;
- reason;
- created_at.

## `reanalysis_requests`

- id;
- invoice_id;
- invoice_document_id;
- requested_by;
- provider;
- model;
- user_note;
- previous_audit_run_id;
- new_audit_run_id;
- status;
- created_at.

## `audit_events`

- id;
- actor_type;
- actor_id;
- entity_type;
- entity_id;
- action;
- metadata JSONB;
- created_at.

## `ai_calls`

Conforme seção 40.

---

# 42. Frontend obrigatório

## Login

Seguro e simples.

## Dashboard

KPIs mínimos:

- faturas recebidas;
- corretas;
- incorretas;
- pendentes;
- revisão;
- valor auditado;
- divergência total;
- divergência a maior;
- divergência a menor;
- documentos auditados;
- custo de IA.

## Faturas

Filtros:

- período;
- parceiro;
- status;
- número;
- vencimento;
- diferença;
- margem;
- pendência.

Colunas:

```text
Fatura
Parceiro
Recebida
Vencimento
Documentos
Cobrado
Esperado
Diferença
Status
```

## Detalhe da fatura

Tabs:

```text
Resumo
Documentos
Tarifários
Interpretação
Histórico
IA / Custos
Arquivos
```

## Documentos

```text
Documento
Tipo
Origem
Destino
Cobrado
Esperado
Diferença
Margem
Status
```

## Detalhe CT-e/AWB

Mostrar:

- dados;
- componentes;
- regra;
- interpretação;
- evidências;
- cálculo;
- pendências;
- margem;
- histórico;
- reanalisar Terra;
- reanalisar Sol;
- observação humana.

## Tarifários

Permitir:

- upload múltiplo;
- listar;
- baixar;
- descrição;
- ativar/desativar;
- soft delete;
- hash;
- auditorias relacionadas.

## Pendências

Fila:

- sem tarifário;
- falta informação;
- ambiguidade;
- leitura impossível;
- inconsistência;
- revisão manual.

## Auditorias

Histórico global com filtros por:

- modelo;
- provider;
- status;
- período;
- custo;
- fatura;
- parceiro.

## Configurações

Mostrar sem expor segredos:

- IMAP status;
- modelos;
- provider;
- worker;
- storage;
- tolerância;
- saúde.

---

# 43. API mínima

```text
POST   /api/auth/login
GET    /api/health
GET    /api/dashboard

GET    /api/invoices
GET    /api/invoices/{id}
GET    /api/invoices/{id}/documents
GET    /api/invoices/{id}/reports
POST   /api/invoices/{id}/reanalyze

GET    /api/documents/{id}
POST   /api/documents/{id}/reanalyze

GET    /api/tariffs
POST   /api/tariffs
GET    /api/tariffs/{id}
PATCH  /api/tariffs/{id}
DELETE /api/tariffs/{id}
GET    /api/tariffs/{id}/download

GET    /api/pending
PATCH  /api/pending/{id}

GET    /api/audits
GET    /api/audits/{id}

POST   /api/worker/run-now
GET    /api/settings/status
```

Paginação obrigatória.

---

# 44. Fluxo operacional completo

```text
1. Worker consulta IMAP.
2. Recupera mensagens novas.
3. Calcula deduplicação.
4. Salva mensagem/anexos.
5. Luna classifica.
6. Move para pasta adequada.
7. Se não fatura: encerra.
8. Cria fatura.
9. Identifica parceiro/metadata.
10. Lista catálogo de tarifários.
11. Seletor escolhe candidatos.
12. Nenhum -> PENDING_NO_TARIFF.
13. Carrega arquivos selecionados.
14. Terra recebe:
    - fatura;
    - anexos;
    - e-mail;
    - tarifários originais;
    - ferramentas.
15. Terra identifica CT-es/AWBs.
16. Terra interpreta tarifários do zero.
17. Determina regra por documento.
18. Calculadora executa aritmética.
19. Persiste resultado individual.
20. Consolida fatura.
21. Calcula margem quando possível.
22. Salva interpretação.
23. Compara com históricos.
24. Cria alerta se incoerente.
25. Gera relatório JSON + HTML.
26. Operador visualiza.
27. Se necessário, operador reanalisa com Sol.
```

---

# 45. Reanálise com Sol

```text
Operador abre fatura/CT-e
        ↓
Reanalisar com Sol
        ↓
observação opcional
        ↓
novo audit_run
        ↓
originais + contexto + resultado anterior
        ↓
nova interpretação
        ↓
nova revisão
        ↓
comparação lado a lado
```

---

# 46. PDF

Ferramentas recomendadas:

```text
list_pdf_pages
extract_pdf_text
render_pdf_page
search_pdf_text
```

PDF textual pode usar extração e original.

PDF escaneado usa visão multimodal.

Evitar enviar conteúdo desnecessário.

---

# 47. Planilhas

Ferramentas:

```text
list_sheets
get_sheet_dimensions
read_range
search_cells
find_rows
get_cell
get_formula
```

Não assumir colunas fixas.

Guardar aba/range como evidência.

---

# 48. Evidências

PDF:

```json
{
  "file_id": "tar_001",
  "page": 4,
  "description": "Faixa de 501 a 1000 kg."
}
```

Excel:

```json
{
  "file_id": "tar_002",
  "sheet": "Regioes",
  "range": "A42:D42",
  "description": "Ipatinga classificada na Região 4."
}
```

Fatura:

```json
{
  "file_id": "inv_att_01",
  "page": 2,
  "description": "CT-e 82918 cobrado em R$ 1.892,34."
}
```

---

# 49. Tolerância financeira

Configuração:

```text
tolerância absoluta
tolerância percentual
```

Guardar valor bruto e arredondado.

---

# 50. Segurança

- segredos nunca hardcoded;
- nunca commitados;
- nunca enviados ao frontend;
- nunca logados;
- senha de usuário com Argon2id/bcrypt;
- validar MIME/extensão/tamanho;
- bloquear path traversal;
- salvar com nome interno;
- nunca executar arquivos enviados;
- redigir logs.

---

# 51. Backup

## Banco

Dump diário PostgreSQL.

## Arquivos

Backup de:

```text
data/tariffs
data/invoices
data/reports
```

## Retenção

Padrão 30 dias.

## Restore

Procedimento testado/documentado.

Google Drive não é dependência operacional.

---

# 52. Observabilidade

Logs estruturados:

```text
timestamp
level
service
job_id
email_id
invoice_id
audit_run_id
event
duration
```

Health check:

```text
/api/health
```

Testar:

- app;
- PostgreSQL;
- storage;
- IMAP;
- IA.

---

# 53. Worker

Modo contínuo:

```text
poll a cada N minutos
```

Modo único:

```bash
python -m app.worker.main --once
```

Também oferecer botão `Processar agora`.

---

# 54. Instalação Windows

`INSTALL.md`:

1. instalar Docker Desktop;
2. WSL2 se necessário;
3. copiar/clonar projeto;
4. `scripts/setup.ps1`;
5. informar IMAP/API;
6. gerar segredos internos;
7. executar:

```powershell
docker compose up -d --build
```

8. acessar `http://localhost:8000`;
9. criar primeiro admin.

---

# 55. Instalação Linux/VPS

1. Docker Engine;
2. Compose plugin;
3. copiar projeto;
4. `scripts/setup.sh`;
5. `.env`;
6. `docker compose up -d --build`;
7. firewall;
8. Caddy/Nginx opcional;
9. domínio/HTTPS opcional.

Sem alteração de código entre Windows e Linux.

---

# 56. Migração local -> servidor

1. parar containers;
2. dump PostgreSQL;
3. copiar `data/`;
4. copiar `.env` de forma segura;
5. restaurar banco;
6. iniciar Compose;
7. migrations;
8. smoke test.

---

# 57. Autenticação

Primeiro acesso cria admin.

Sessão via cookie HTTPOnly seguro ou JWT corretamente protegido.

---

# 58. Auditoria humana

Operador pode:

- marcar revisado;
- comentar;
- aceitar/rejeitar;
- editar;
- reanalisar;
- resolver pendência;
- resolver inconsistência.

Toda ação -> `audit_event`.

---

# 59. Erros

Estados claros:

```text
AI_ERROR
IMAP_ERROR
DOCUMENT_ERROR
STORAGE_ERROR
DATABASE_ERROR
PROCESSING_ERROR
```

Devem aparecer no frontend e permitir retry.

---

# 60. Idempotência e concorrência

Jobs devem ser idempotentes.

Não duplicar:

- mensagem;
- anexo;
- fatura.

Evitar processar mesma fatura simultaneamente usando lock transacional/advisory.

---

# 61. Exclusão

Tarifário usado em auditoria:

- pode ser desativado;
- exclusão física deve ser bloqueada ou explícita;
- preferir soft delete.

---

# 62. Testes obrigatórios

## Unitários

- fingerprint;
- Decimal;
- tolerância;
- cálculo;
- consolidação;
- storage;
- normalização;
- dedupe.

## Integração

- PostgreSQL;
- upload;
- IMAP mock;
- AIProvider mock;
- auditoria completa.

## Golden cases

```text
tests/golden_cases/
```

Cada caso:

```text
email.json
invoice.*
tariffs/*
expected.json
```

---

# 63. Critérios de aceite

O produto só é pronto quando:

1. recebe e-mail;
2. deduplica;
3. classifica;
4. move;
5. salva originais;
6. cria fatura;
7. lista tarifários;
8. IA seleciona;
9. Terra reinterpreta originais do zero;
10. identifica documentos;
11. calcula;
12. compara;
13. gera resultado individual;
14. consolida;
15. nunca chama pendência de correta;
16. persiste evidências;
17. salva interpretação;
18. reanalisa com Sol;
19. preserva histórico;
20. frontend exibe;
21. tarifários são gerenciáveis;
22. Docker Compose funciona;
23. Windows documentado;
24. Linux documentado.

---

# 64. Critérios financeiros

Para qualquer `INCORRECT`, responder:

```text
Qual documento está errado?
Quanto foi cobrado?
Quanto deveria ser?
Qual a diferença?
Qual regra foi aplicada?
Qual tarifário?
Onde está a evidência?
Quais entradas foram usadas?
Como chegou ao esperado?
```

Sem isso, resultado não é plenamente auditável.

---

# 65. Status

## E-mail

```text
NEW
CLASSIFIED
MOVED
PROCESSING
DONE
MANUAL_REVIEW
ERROR
```

## Fatura

```text
PROCESSING
CORRECT
INCORRECT
PENDING
MANUAL_REVIEW
NOT_AUDITABLE
ERROR
```

## Documento

```text
CORRECT
INCORRECT
PENDING_MISSING_INFO
PENDING_AMBIGUITY
PENDING_NO_TARIFF
MANUAL_REVIEW
ERROR
```

## Pendência

```text
OPEN
RESOLVED
DISMISSED
```

---

# 66. Política inicial de modelos

```text
Classificação:
GPT-5.6 Luna

Seleção de tarifário:
GPT-5.6 Terra

Auditoria:
GPT-5.6 Terra

Reanálise manual avançada:
GPT-5.6 Sol
```

**Não implementar fallback automático Terra -> Sol.**

A dificuldade só seria conhecida depois de interpretar parte relevante da fatura, o que poderia duplicar custo.

---

# 67. Troca de provider/modelo

Deve ser possível alterar:

```env
AI_AUDIT_PROVIDER=google
AI_AUDIT_MODEL=<modelo>
```

sem mudar domínio.

Entre modelos do mesmo provider, idealmente somente configuração.

Entre fornecedores, muda adapter, não o sistema inteiro.

---

# 68. Respostas estruturadas

Usar Pydantic/JSON Schema para:

- classificação;
- tarifário;
- interpretação;
- documento;
- componentes;
- resultado;
- pendências;
- evidências.

Texto livre somente para explicação.

---

# 69. Exemplo conceitual de auditoria

```json
{
  "invoice": {
    "number": "91872",
    "partner": "JPC Transportes",
    "status": "INCORRECT",
    "charged_total": "18492.71",
    "expected_total": "17981.20",
    "difference": "511.51"
  },
  "tariffs": [
    {
      "id": "tar_001",
      "filename": "JPC-2026.pdf"
    }
  ],
  "documents": [
    {
      "type": "CTE",
      "number": "82918",
      "status": "INCORRECT",
      "charged": "1892.34",
      "expected": "1550.36",
      "difference": "341.98",
      "interpretation": {},
      "evidence": [],
      "calculation_trace": []
    }
  ],
  "pending_items": [],
  "interpretation_warnings": []
}
```

---

# 70. O que NÃO fazer

- parser fixo por parceiro;
- layout hardcoded;
- assunto como regra de classificação;
- primeira interpretação do tarifário como verdade permanente;
- float para dinheiro;
- `eval` inseguro;
- apagar versões;
- segredos no Git;
- Terra -> Sol automático;
- enviar todos os tarifários completos sem seleção;
- inventar dados;
- marcar correta com pendência;
- guardar arquivos apenas dentro do container.

---

# 71. Performance e custo

Volume inicial:

```text
~100 faturas/mês
```

O principal custo variável é IA.

Reduzir custo por:

- Luna para e-mail;
- seleção antes de carregar tarifários;
- Terra padrão;
- Sol manual;
- ferramentas para trechos;
- evitar contexto irrelevante;
- caching técnico quando aplicável.

Nunca sacrificar auditabilidade para economizar tokens.

---

# 72. Comparação Terra vs Sol

Quando houver reanálise, mostrar lado a lado:

```text
Status
Valor esperado
Diferença
Região
Peso
Tarifários
Regras
Pendências
Interpretações divergentes
```

---

# 73. Reprocessamento após novo tarifário

Novo upload não deve disparar reprocessamento automático de todo histórico.

Permitir reanálise seletiva ou futura reanálise em lote.

---

# 74. Temporários

`data/temp` pode ser limpo.

Nunca limpar:

- originais;
- tarifários usados;
- relatórios;
- evidências persistidas.

---

# 75. Exportação

No mínimo:

- HTML;
- impressão;
- PDF se viável.

CSV/XLSX de listagens é desejável, não bloqueante.

---

# 76. Dashboard analítico futuro

Preparar dados para:

- divergência por parceiro;
- motivo;
- mês;
- valor recuperável;
- CT-es com erro;
- margem por parceiro;
- custo por IA;
- taxa de validação humana.

---

# 77. Qualidade do código

- tipagem;
- módulos pequenos;
- lint/format;
- testes;
- migrations;
- transações;
- UTC no banco;
- `America/Sao_Paulo` na apresentação;
- documentação de decisões.

---

# 78. CI

Desejável GitHub Actions:

- lint;
- testes;
- build Docker.

Sem segredos reais.

---

# 79. Documentação obrigatória

## README.md

Visão, arquitetura, comandos.

## INSTALL.md

Windows, Linux, configuração, backup, restore, troubleshooting.

## ARCHITECTURE.md

Providers, fluxo e decisões.

## SECURITY.md

Segredos, uploads, autenticação e produção.

---

# 80. Scripts

## `scripts/setup.ps1`

- validar Docker;
- criar `.env`;
- gerar segredos;
- criar diretórios;
- build;
- migrations;
- primeiro acesso.

## `scripts/setup.sh`

Mesmo objetivo no Linux.

---

# 81. Primeiro acesso

Criar admin e mostrar:

```text
IMAP: OK/ERRO
PostgreSQL: OK
Storage: OK
IA: OK/ERRO
Worker: OK
```

---

# 82. Teste IMAP

Botão/ação:

```text
Testar conexão IMAP
```

Verificar conexão, autenticação, INBOX e movimentação/criação de pasta.

---

# 83. Teste IA

Ação:

```text
Testar provider
```

Mostrar:

- provider;
- modelo;
- latência;
- status.

---

# 84. Modo de desenvolvimento/produção

Produção preferencial: Docker.

Permitir backend/frontend fora do Docker para desenvolvimento.

---

# 85. Ordem de construção

## Fase 1

Docker, PostgreSQL, FastAPI, migrations, frontend base, auth, storage.

## Fase 2

IMAP, fingerprint, dedupe, classificação, movimentação.

## Fase 3

Upload/catalogação/seleção de tarifários.

## Fase 4

Auditoria Terra, ferramentas, cálculo, CT-e/AWB, consolidação.

## Fase 5

Frontend operacional e relatórios.

## Fase 6

Reanálise Terra/Sol, versões, comparação.

## Fase 7

Custos, logs, backup, health.

---

# 86. Entrega esperada do agente de código

Não entregar só scaffold.

Obrigatório:

- código executável;
- Docker Compose;
- migrations;
- frontend;
- login;
- upload de tarifário;
- IMAP;
- OpenAIProvider funcional;
- classificação;
- seleção;
- auditoria;
- persistência;
- reanálise;
- relatório;
- testes críticos;
- documentação.

Não deixar `TODO` em fluxo fundamental.

---

# 87. Falhas parciais

Se algo não puder ser concluído:

1. manter interface correta;
2. implementar caminho principal;
3. registrar limitação;
4. nunca simular sucesso.

Exemplo:

```text
DOCUMENT_UNSUPPORTED
```

é melhor que auditoria inventada.

---

# 88. Critério de sucesso do produto

Um operador deve conseguir:

1. configurar IMAP/API;
2. subir tarifários;
3. deixar worker receber faturas;
4. abrir painel;
5. escolher fatura;
6. ver quais CT-es/AWBs estão certos/errados;
7. entender por quê;
8. conferir evidência;
9. ver cobrado/esperado/diferença;
10. ver margem quando disponível;
11. corrigir/adicionar nota;
12. reanalisar com Sol;
13. comparar versões;
14. manter histórico.

---

# 89. Regra de ouro

> **A aplicação não deve apenas dizer “a fatura está errada”. Deve demonstrar, documento por documento, por que está errada e quais dados e regras produziram a conclusão.**

---

# 90. Instrução final ao agente implementador

Implemente esta especificação como um produto real, priorizando confiabilidade, auditabilidade e facilidade de implantação.

Evite complexidade sem benefício para o volume atual, mas não sacrifique:

- idempotência;
- segurança;
- persistência;
- versionamento;
- rastreabilidade;
- providers;
- auditoria por documento;
- reanálise;
- integridade dos originais.

A configuração ideal do usuário final deve se resumir, tanto quanto possível, a:

```text
IMAP host
IMAP port
IMAP user/e-mail
IMAP password
AI API key
provider/model names
```

Segredos internos adicionais devem ser gerados automaticamente.

Implementação inicial de IA:

```text
Luna -> classificação
Terra -> seleção de tarifário
Terra -> auditoria principal
Sol -> reanálise avançada manual
```

Os nomes são configuração e devem poder mudar sem alteração do núcleo.

**Não reutilizar interpretação de tarifário como verdade entre faturas. Cada auditoria reinterpreta os arquivos originais selecionados.**

**Armazenar justificativa estruturada e auditável — fatos, evidências, regras, premissas, ambiguidades e cálculos — e não cadeia de pensamento privada.**

**Preservar integralmente todas as versões anteriores de auditoria e relatório.**

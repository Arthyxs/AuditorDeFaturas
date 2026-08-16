# InvoiceAuditor — Estado do Projeto

**Atualizado em:** 2026-08-15
**Especificação:** v3.0, fechada para implementação
**Fase atual:** planejamento aprovado / ambiente pronto
**Macroetapa atual:** B — Fundação executável, segura e persistente, ainda não iniciada
**Milestone atual:** nenhum em execução; M00 concluído e M01 aguarda autorização explícita

## Resumo executivo

O repositório contém somente governança, especificação, configuração de exemplo e documentos de planejamento. Não existe código de aplicação, migration, teste, Dockerfile ou Compose. A arquitetura geral, as quatro definições antes abertas e as ADRs atuais foram aprovadas em 2026-08-15.

Não foi encontrada contradição técnica que impeça o produto. O plano inclui macroetapas, auditoria manual convergente com o pipeline IMAP, golden cases estratificados e métricas formais de qualidade. M00 foi concluído; isso remove o bloqueio técnico, mas M01 continua não iniciado até autorização explícita do usuário.

## Milestones concluídos

- **M00 — Aprovação do plano e prontidão do ambiente:** concluído em 2026-08-15.

## Trabalho concluído nesta fase

- leitura integral de `AGENTS.md`;
- leitura integral das 2.562 linhas de `ESPECIFICACAO_COMPLETA_AUDITOR_FATURAS_V3.md`;
- leitura de `GIT_WORKFLOW.md`, `CODE_REVIEW.md`, `.env.example` e `.gitignore`;
- inventário do repositório;
- inspeção do ambiente Windows, Git, Docker/WSL e toolchains disponíveis;
- validação documental dos IDs `gpt-5.6-luna`, `gpt-5.6-terra` e `gpt-5.6-sol` na documentação oficial da OpenAI;
- aprovação das quatro definições de produto e das ADRs;
- criação de sete macroetapas sem remover M00–M26;
- inclusão do fluxo de auditoria manual pelo frontend/API sobre o mesmo pipeline do IMAP;
- definição de baseline com 16+ golden cases em quatro dificuldades;
- definição de document accuracy, false positive rate, false negative rate e pending rate, com falso negativo crítico;
- explicitação de que WSL2 é requisito apenas do ambiente Windows atual, não da arquitetura;
- validação de WSL2 padrão versão 2 com distribuição `docker-desktop`;
- validação de Docker Client/Engine 29.7.2, Docker Desktop 4.86.0 e Docker Compose 5.3.1;
- execução bem-sucedida de `hello-world` em container Linux `amd64`;
- configuração de `main` para rastrear `origin/main` e validação de `git push --dry-run origin main` com resultado `Everything up-to-date`.

## Trabalho não iniciado

- todos os milestones M01–M26;
- código backend/frontend;
- banco e migrations;
- testes e golden cases;
- integrações IMAP/OpenAI;
- documentação operacional final.

## Estado do repositório e Git

- branch atual: `main`;
- working tree antes da criação destes documentos: limpa;
- remoto: `origin` configurado para `https://github.com/Arthyxs/AuditorDeFaturas.git`;
- commit local e `origin/main` inspecionado: `5f018648f699399e52e3ca71302a737cb518d538`;
- divergência local/remoto observada: `0` à frente, `0` atrás;
- upstream local: `main` rastreia `origin/main`;
- alterações atuais esperadas: somente `IMPLEMENTATION_PLAN.md`, `PROJECT_STATUS.md` e `DECISIONS.md`.

## Estado do ambiente

### Disponível

- Windows reportado pelo PowerShell como Microsoft Windows 10.0.26200;
- PowerShell 7.6.4;
- Git 2.53.0.windows.3;
- Node.js 24.19.0 e npm 11.17.0 no sistema;
- ripgrep 15.2.0;
- runtime Python 3.12.13 fornecido pelo ambiente do Codex;
- runtime Node/pnpm também fornecido pelo ambiente do Codex.

### Ausente ou não operacional

- Python não está instalado globalmente no `PATH` do usuário, embora exista o runtime isolado do Codex;
- inventário detalhado de hardware/virtualização via CIM foi negado pelas permissões atuais.

### Runtime canônico validado

- WSL2: distribuição padrão `docker-desktop`, versão padrão 2;
- Docker Client/Engine: 29.7.2;
- Docker Desktop: 4.86.0, contexto `desktop-linux`, Engine Linux `amd64`;
- Docker Compose: 5.3.1;
- smoke externo: `docker run --rm hello-world` concluído com sucesso.

## Status de testes, build e Docker

- testes: não existem; não executados;
- lint/type checks: não configurados;
- migrations: não existem;
- Docker CLI/Engine/Compose: disponíveis e validados;
- Docker build do projeto: não existe para executar, pois M01/M02 ainda não começaram;
- Docker Compose do projeto: não existe para executar;
- serviços em execução: nenhum serviço do projeto existe.

## Bloqueios e riscos conhecidos

### Bloqueios atuais

Nenhum bloqueio técnico conhecido para iniciar M01. O único gate restante é autorização explícita do usuário.

### Dependências externas futuras

- credenciais IMAP serão necessárias para contract test real; testes fake/mock não comprovam a conta real;
- API key e acesso da conta aos modelos serão necessários para contract test real;
- documentos reais não devem entrar no Git; golden cases versionados usam amostras sintéticas/licenciadas, enquanto casos reais anonimizados ficam em área privada ignorada pelo Git.

### Decisões aprovadas, não bloqueios

1. `EMAIL_CLASSIFICATION_MIN_CONFIDENCE=0.80` inicial e configurável;
2. bootstrap do primeiro admin por token único gerado pelo setup;
3. correção humana como nova revisão imutável, sem mutar o run de IA;
4. reanálise parcial publicada como revisão completa com linhagem dos resultados não reanalisados;
5. auditoria manual `ADMIN`/`OPERATOR` convergindo para o mesmo pipeline do IMAP;
6. falso negativo como finding `CRITICAL` e bloqueio de release.

## Findings de code review

Nenhum finding aberto. Ainda não há código para revisar.

## Último commit estável

`5f018648f699399e52e3ca71302a737cb518d538` — `chore: bootstrap project governance and specification`

Este hash antecede os documentos de planejamento e será substituído pelo hash do commit de conclusão de M00 após o commit/push desta atualização.

## Próxima ação recomendada

Aguardar autorização explícita do usuário para iniciar M01. Não implementar código antes dessa autorização.

# DSM-G08-PI6-2026-1

Repositório do GRUPO 08 do Projeto Interdisciplinar do 6º semestre DSM 2026/1. Alunos: Guilherme Dilio, Sheila e Gabriel Araújo

# Maternar

Aplicativo móvel de acompanhamento pré-natal com classificação de perfil gestacional por Inteligência Artificial, desenvolvido com dados históricos do DATASUS.

> **Projeto Interdisciplinar — 6º semestre · Desenvolvimento de Software Multiplataforma**

---

## O Problema

Gestantes em situação de vulnerabilidade não recebem orientação preventiva adequada durante a gestação. A ausência de triagem personalizada e acessível amplia desigualdades em saúde materno-infantil.

## A Solução

O **Maternar** utiliza um modelo K-Means (K=3) treinado com **378.969 gestantes** (DATASUS 2014–2016) para classificar o perfil de cuidado de cada gestante e entregar orientações personalizadas em linguagem acolhedora — sem alarmismo, sem barreiras técnicas.

---

## Perfis Identificados pelo Modelo de IA

| Cluster | Nome Técnico          | Nome no App           | % da Base | Característica Principal          |
| ------- | --------------------- | --------------------- | --------- | --------------------------------- |
| C0      | Obesidade Gestacional | **Cuidado Integral**  | 27,3%     | IMC pré-gestacional ≥ 31          |
| C1      | Eutrofia / Baixo Peso | **Caminho Seguro**    | 71,2%     | Grupo majoritário do SUS          |
| C2      | Acesso Diferenciado   | **Atenção Redobrada** | 1,5%      | Município com alta infraestrutura |

**Métricas do modelo:** Silhouette = 0,2873 · Calinski-Harabász = 102.169 · ARI hold-out = 0,999

---

## Arquitetura do Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                     App Flutter (Maternar)                   │
│  Cadastro · Login · Dashboard · Diário · Conteúdo Educativo  │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTPS / REST
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   Backend NestJS (API)                        │
│  Autenticação JWT · Cadastro de gestantes · Perfil           │
│  Integração ViaCEP · Validação de DTOs                       │
└──────────┬──────────────────────────────────┬───────────────┘
           │ PostgreSQL (Prisma)              │ RabbitMQ
           ▼                                  ▼
┌──────────────────┐              ┌──────────────────────────┐
│   PostgreSQL 16  │              │   Worker Flask (IA)       │
│   Dados de       │              │   KMeans K=3 · PCA · Scaler│
│   gestantes e    │◄─────────────│   Classificação de perfil │
│   localizações   │              │   gestacional             │
└──────────────────┘              └──────────────────────────┘
```

---

## Repositórios e Componentes

### `/maternar-backend/` — API NestJS

Backend REST responsável por autenticação, cadastro e gestão de perfil.

➜ [README do Backend](maternar-backend/README.md) · [Documentação Técnica](Document/14-Arquitetura_Backend_NestJS.md)

**Stack:** NestJS 11 · Prisma 7 · PostgreSQL · TypeScript · JWT · bcrypt

### `/maternar-frontend/` — App Flutter

Aplicativo mobile com interface acolhedora para acompanhamento gestacional.

➜ [README do Frontend](maternar-frontend/README.md) · [Documentação Técnica](Document/15-Arquitetura_Frontend_Flutter.md)

**Stack:** Flutter 3.8+ · Dart 3.8+ · Material 3 · http · shared_preferences

### `/ApiDatasus/` — Pipeline de Dados e Serviço de IA

Pipeline KDD completo (download → pré-processamento → clustering → pós-processamento) e Worker Flask para inferência.

➜ [README do Pipeline](ApiDatasus/README.md)

**Stack:** Python 3.12 · scikit-learn · pandas · Flask · RabbitMQ · Docker

---

## Estrutura do Repositório

```
Maternar/
│
├── README.md                         # Este arquivo
├── docker-compose.yml                # Infraestrutura: PostgreSQL + RabbitMQ + Worker
│
├── maternar-backend/                 # API NestJS (Sprint 2+)
│   ├── src/                          # Código-fonte TypeScript
│   ├── prisma/                       # Schema e migrations
│   ├── test/                         # Testes unitários e E2E
│   ├── docs/                         # Documentação específica do backend
│   ├── docker-compose.yml            # PostgreSQL para desenvolvimento local
│   ├── .env.example                  # Template de variáveis de ambiente
│   └── README.md                     # Guia de instalação e uso
│
├── maternar-frontend/                # App Flutter (Sprint 2+)
│   ├── lib/                          # Código-fonte Dart
│   ├── assets/                       # Imagens do app
│   ├── test/                         # Testes de widget
│   ├── android/ ios/ web/            # Plataformas nativas
│   └── README.md                     # Guia de instalação e uso
│
├── ApiDatasus/                       # Pipeline de dados e IA
│   ├── flask_api/                    # Serviço Flask de inferência
│   ├── dados_datasus/                # Notebooks e dados brutos
│   ├── clustering_output/            # Artefatos do modelo final
│   ├── preprocess_output/            # Dados pré-processados
│   ├── pos_processamento_output/     # Validação estatística
│   ├── main.py                       # Download DATASUS
│   ├── preprocessing_maternar.py     # Feature engineering
│   ├── pos_processamento_k3.py       # Validação hold-out + bootstrap
│   └── README.md                     # Guia do pipeline
│
└── Document/                         # Documentação do projeto
    ├── 00-Apresentacao_Projeto.md
    ├── 01-Visao_do_Produto.md
    ├── 02-Especificacao_de_Requisitos.md
    ├── 03-Arquitetura_de_Dados_e_IA.md
    ├── 04-Guia_de_UX_e_Tom_de_Voz.md
    ├── 05-Dicionario_de_Dados_DATASUS.md
    ├── 06-Fluxo_e_Telas_da_Aplicacao.md
    ├── 07-Questionamento_ao_Stakeholder.md
    ├── 08-Especificacao_Tecnica_Backend.md
    ├── 09-Pipeline_de_Treinamento_e_Mineracao.md
    ├── 10-Entrega_Sprint_1.md
    ├── 11-Modelagem_de_Banco_de_Dados.md
    ├── 12-Documentacao_Datasets_DATASUS.md
    ├── 13-Especificacoes_de_Seguranca.md
    ├── 14-Arquitetura_Backend_NestJS.md
    ├── 15-Arquitetura_Frontend_Flutter.md
    ├── 16-Guia_de_Integração.md
    └── 17-Modelagem_de_Banco_de_DadosNOVO.md
```

---

## Início Rápido — Desenvolvimento

### Pré-requisitos

- Node.js 22+
- Flutter SDK 3.8+
- Docker e Docker Compose
- Python 3.12+ (apenas para re-treinar o modelo)

### 1. Backend

```bash
cd maternar-backend
cp .env.example .env         # Editar com credenciais reais
npm install
docker-compose up -d         # Sobe PostgreSQL
npx prisma migrate dev       # Aplica migrations
npx prisma generate          # Gera Prisma Client
npm run start:dev            # API em http://localhost:3000
```

### 2. Frontend

```bash
cd maternar-frontend
flutter pub get
flutter run -d emulator-5554 # Backend em 10.0.2.2:3000
```

### 3. Serviço de IA (Worker Flask)

> Os artefatos `.pkl` já estão versionados. Execute apenas se precisar re-treinar.

```bash
# Subir infraestrutura completa (Postgres + RabbitMQ + Worker)
docker compose up -d

# Verificar logs do worker
docker compose logs -f worker
```

Saída esperada do worker:

```
maternar_worker | Modelos carregados — Scaler(9 feat) → PCA(8 comp) → KMeans(K=3)
maternar_worker | Worker aguardando mensagens em 'maternar.classificar'...
```

---

## API de Inferência

### Via HTTP (desenvolvimento)

```bash
# Health check
curl http://localhost:5001/health

# Classificar perfil gestacional
curl -X POST http://localhost:5001/classificar \
  -H "Content-Type: application/json" \
  -d '{
    "nu_peso": 72.0,
    "nu_altura": 1.62,
    "nu_imc_pre_gestacional": 24.1,
    "raca_cor": 4,
    "escolaridade": 3,
    "cod_municipio": "350950"
  }'
```

**Resposta:**

```json
{
  "cluster_id": 1,
  "cluster_nome": "Eutrofia / Baixo Peso",
  "cluster_nome_app": "Caminho Seguro",
  "nivel_risco": "moderado",
  "recomendacoes": [
    { "categoria": "nutricao", "texto": "Monitorar ganho de peso" },
    {
      "categoria": "consultas",
      "texto": "Mínimo de 6 consultas pré-natais (SUS)"
    }
  ]
}
```

---

## Dados e Fontes

| Base   | Conteúdo                              | Linkage       |
| ------ | ------------------------------------- | ------------- |
| SISVAN | Peso, altura, IMC, raça, escolaridade | Individual    |
| SINAN  | Taxa de sífilis gestacional           | Município/ano |
| SIM    | Taxa de mortalidade materna           | Município/ano |
| SIA    | Cobertura de consultas pré-natal      | Município/ano |
| CNES   | Quantidade de hospitais               | Município/ano |

**Período:** 2014–2016 · **Municípios:** 2.573 · **Gestantes:** 378.969

---

## Documentação

| #   | Documento                                                                     | Descrição                                     |
| --- | ----------------------------------------------------------------------------- | --------------------------------------------- |
| 00  | [Apresentação do Projeto](Document/00-Apresentacao_Projeto.md)                | Visão geral com métricas do modelo            |
| 01  | [Visão do Produto](Document/01-Visao_do_Produto.md)                           | Problema, solução, KPIs                       |
| 02  | [Especificação de Requisitos](Document/02-Especificacao_de_Requisitos.md)     | Requisitos funcionais e não-funcionais        |
| 03  | [Arquitetura de Dados e IA](Document/03-Arquitetura_de_Dados_e_IA.md)         | Pipeline e clusters K=3                       |
| 04  | [Guia de UX e Tom de Voz](Document/04-Guia_de_UX_e_Tom_de_Voz.md)             | Design system e linguagem                     |
| 05  | [Dicionário de Dados DATASUS](Document/05-Dicionario_de_Dados_DATASUS.md)     | Variáveis e codificações                      |
| 06  | [Fluxo e Telas da Aplicação](Document/06-Fluxo_e_Telas_da_Aplicacao.md)       | Jornadas e wireframes                         |
| 07  | [Questionamento ao Stakeholder](Document/07-Questionamento_ao_Stakeholder.md) | Decisões de produto                           |
| 08  | [Especificação Técnica Backend](Document/08-Especificacao_Tecnica_Backend.md) | Flask + NestJS + RabbitMQ                     |
| 09  | [Pipeline de Treinamento](Document/09-Pipeline_de_Treinamento_e_Mineracao.md) | KDD completo com métricas                     |
| 10  | [Entrega Sprint 1](Document/10-Entrega_Sprint_1.md)                           | Resultados consolidados                       |
| 11  | [Modelagem de Banco de Dados](Document/11-Modelagem_de_Banco_de_Dados.md)     | Schemas PostgreSQL                            |
| 12  | [Documentação DATASUS](Document/12-Documentacao_Datasets_DATASUS.md)          | Datasets utilizados                           |
| 13  | [Especificações de Segurança](Document/13-Especificacoes_de_Seguranca.md)     | Vulnerabilidades, melhorias, LGPD             |
| 14  | [Arquitetura Backend NestJS](Document/14-Arquitetura_Backend_NestJS.md)       | Módulos, endpoints, fluxos                    |
| 15  | [Arquitetura Frontend Flutter](Document/15-Arquitetura_Frontend_Flutter.md)   | Telas, camadas, componentes                   |
| 16  | [Guia de Integração](Document/16-Guia_de_Integração.md)                       | Contratos de API: payloads, respostas, fluxos |
| 17  | [Modelagem de Banco de Dados](Document/17-Modelagem_de_Banco_de_DadosNOVO.md) | Schema Prisma, DDL, relacionamentos           |

---

## Estado Atual do Projeto

| Componente                        | Status      | Observações                                 |
| --------------------------------- | ----------- | ------------------------------------------- |
| Pipeline KDD (dados + modelo)     | ✅ Completo | 378.969 gestantes, K=3                      |
| Worker Flask (inferência)         | ✅ Completo | RabbitMQ + HTTP                             |
| Backend NestJS — Auth             | ✅ Completo | JWT, bcrypt, guards                         |
| Backend NestJS — Usuários         | ✅ Completo | Cadastro, perfil, ViaCEP                    |
| Frontend Flutter — Cadastro/Login | ✅ Completo | Fluxo completo integrado                    |
| Frontend Flutter — Dashboard      | ✅ Completo | Sincronizado com API                        |
| Frontend Flutter — Conteúdo       | ✅ Completo | Artigos, nutrição, semana                   |
| Backend NestJS — Classificação IA | ✅ Completo | POST /classification via RabbitMQ           |
| Backend NestJS — Gestações        | ✅ Completo | CRUD de ciclos gestacionais                 |
| Backend NestJS — Questionários    | ✅ Completo | Check-in com classificação IA em tempo real |
| Integração NestJS ↔ Worker IA     | ✅ Completo | RabbitMQ RPC com timeout de 10s             |
| Refresh Token                     | 🔄 Pendente | Ver doc de segurança                        |
| Compliance LGPD                   | 🔄 Pendente | Endpoints de direitos                       |

---

## Segurança

Este projeto lida com **dados de saúde sensíveis** (categoria especial LGPD, Art. 11). Vulnerabilidades identificadas, melhorias priorizadas e checklist de deploy estão documentados em:

➜ [Document/13-Especificacoes_de_Seguranca.md](Document/13-Especificacoes_de_Seguranca.md)

Antes de qualquer deploy em produção, revisar o checklist de segurança nesse documento.

---

## Equipe

| Nome                     | Papel                                |
| ------------------------ | ------------------------------------ |
| Gabriel Araujo de Pádua  | Backend · Pipeline de Dados · DevOps |
| Guilherme Dilio de Souza | Backend · Arquitetura                |
| Sheila Alves de Araujo   | Frontend · UX                        |

---

## Stack

![Flutter](https://img.shields.io/badge/Flutter-3.8-blue?logo=flutter)
![NestJS](https://img.shields.io/badge/NestJS-11-red?logo=nestjs)
![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.1-black?logo=flask)
![scikit-learn](https://img.shields.io/badge/scikit--learn-1.6-orange?logo=scikitlearn)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue?logo=postgresql)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-3.13-orange?logo=rabbitmq)
![Docker](https://img.shields.io/badge/Docker-Compose-blue?logo=docker)
![Prisma](https://img.shields.io/badge/Prisma-7-white?logo=prisma)

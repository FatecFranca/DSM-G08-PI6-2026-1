# 11 - Modelagem Detalhada de Banco de Dados: Maternar

> **Última atualização:** 2026-06-06
> **Status:** Esquema atualizado — migração para modelo de Timeline/Event Sourcing com respostas e dicas em JSON retornadas diretamente do Worker de IA.

---

## 1. Visão Geral do Modelo de Dados

O sistema mantém dois schemas no mesmo banco PostgreSQL `maternar`:

| Schema        | Responsável     | Propósito                                                            |
| ------------- | --------------- | -------------------------------------------------------------------- |
| `app`         | NestJS          | Dados de produção — usuárias, gestações e histórico de questionários |
| `ml_maternar` | Pipeline Python | Features municipais para inferência K-Means                          |
| `datasus`     | ETL offline     | Microdados históricos DATASUS — apenas para re-treinamento           |

### Diagrama Conceitual

```
users ──(1:N)──▶ gestacoes ──(1:N)──▶ questionario_respostas
                    │
                    └──(N:1)──▶ clusters ──(N:N via cluster_dicas)──▶ dicas
```

---

## 2. Tabelas do Schema `app` no prisma

---

### 2.1. Tabela `app.users` (Gestante)

Armazena perfil completo da gestante. Os campos de saúde presentes aqui são **estáticos ou de longa duração** (não mudam a cada consulta). Estes campos alimentam diretamente o payload enviado ao motor de IA.

| Coluna                    | Tipo         | Restrições                    | Obrigatório | Descrição                                                                                               |
| ------------------------- | ------------ | ----------------------------- | ----------- | ------------------------------------------------------------------------------------------------------- |
| `id`                      | UUID         | PK, DEFAULT gen_random_uuid() | Sim         | Identificador único                                                                                     |
| `name`                    | VARCHAR(150) | NOT NULL                      | Sim         | Nome completo                                                                                           |
| `email`                   | VARCHAR(254) | UNIQUE NOT NULL               | Sim         | E-mail de login                                                                                         |
| `password`                | VARCHAR(255) | NOT NULL                      | Sim         | Senha criptografada (bcrypt)                                                                            |
| `phone`                   | VARCHAR(20)  |                               | Não         | Contato para notificações push                                                                          |
| `birthDate`               | DATE         | NOT NULL                      | Sim         | Para cálculo de idade gestacional                                                                       |
| `raceColor`               | SMALLINT     | CHECK (1–5)                   | **Sim**     | Auto-declaração — **obrigatório para inferência IA**: 1=Branca, 2=Preta, 3=Amarela, 4=Parda, 5=Indígena |
| `height`                  | NUMERIC(4,2) | CHECK (1.00–2.50)             | Não         | Altura em metros — usada no cálculo de IMC                                                              |
| `preGestationalWeight`    | NUMERIC(5,2) | CHECK (30.0–250.0)            | Não         | Peso antes da gestação (kg) — usado para `nu_imc_pre_gestacional`                                       |
| `educationLevel`          | SMALLINT     | CHECK (1–5)                   | Sim         | Código ESCMAE: 1=Sem escolaridade ... 5=Superior                                                        |
| `previousPregnancies`     | SMALLINT     | CHECK >= 0                    | Não         | Número de gestações anteriores (histórico)                                                              |
| `hadPreviousComplication` | BOOLEAN      | DEFAULT FALSE                 | Não         | Histórico de complicação clínica grave anterior                                                         |
| `zipCode`                 | VARCHAR(9)   | NOT NULL                      | Sim         | CEP no formato `00000-000` — origem para lookup de município                                            |
| `createdAt`               | TIMESTAMPTZ  | DEFAULT now()                 | —           | Data de cadastro                                                                                        |
| `updatedAt`               | TIMESTAMPTZ  | DEFAULT now()                 | —           | Última modificação de perfil                                                                            |

**Notas de negócio:**

- `raca_cor` e `escolaridade` são solicitados no onboarding pois são **features obrigatórias do modelo K-Means**. Sem eles, a inferência usa valores padrão, reduzindo a precisão.
- `cod_municipio` é resolvido automaticamente a partir do CEP via API ViaCEP no momento do cadastro — o usuário não precisa informá-lo manualmente.
- `imc_pre_gestacional` é **calculado** pelo backend como `peso_pre_gestacional / altura²` antes de enviar ao Flask.

---

### 2.2. Tabela `app.user_locations` (Localização da Gestante)

Armazena os dados geográficos detalhados da usuária, separados da tabela principal de perfil.

| Coluna      | Tipo         | Restrições                    | Obrigatório | Descrição                                                                                |
| ----------- | ------------ | ----------------------------- | ----------- | ---------------------------------------------------------------------------------------- |
| `id`        | UUID         | PK, DEFAULT gen_random_uuid() | Sim         | Identificador único                                                                      |
| `userId`    | UUID         | FK → `app.users.id`, UNIQUE   | Sim         | Gestante proprietária da localização                                                     |
| `city`      | VARCHAR(150) | NOT NULL                      | Sim         | Nome da cidade                                                                           |
| `uf`        | VARCHAR(2)   | NOT NULL                      | Sim         | Unidade Federativa (Sigla do Estado)                                                     |
| `region`    | VARCHAR(50)  |                               | Não         | Região do país                                                                           |
| `ibgeCode`  | VARCHAR(7)   |                               | Não         | Código IBGE 7 dígitos — derivado do CEP no cadastro; usado nas features municipais da IA |
| `createdAt` | TIMESTAMPTZ  | DEFAULT now()                 | —           | Data de registro                                                                         |

---

### 2.3. Tabela `app.gestacoes`

Cada linha representa um ciclo gestacional. Uma usuária pode ter múltiplas gestações ao longo do tempo.

| Coluna               | Tipo        | Restrições                                                   | Descrição                                           |
| -------------------- | ----------- | ------------------------------------------------------------ | --------------------------------------------------- |
| `id`                 | UUID        | PK, DEFAULT gen_random_uuid()                                | Identificador único                                 |
| `userId`             | UUID        | FK → `app.users.id`, NOT NULL                                | Gestante proprietária                               |
| `dumStartDate`       | DATE        |                                                              | Data da Última Menstruação (para cálculo de IG)     |
| `estimatedDueDate`   | DATE        |                                                              | Calculada pelo sistema (DUM + 280 dias)             |
| `status`             | VARCHAR(20) | CHECK ('ativa','finalizada','interrompida'), DEFAULT 'ativa' | Estado da gestação                                  |
| `currentClusterId`   | SMALLINT    | CHECK (0–3)                                                  | Último cluster atribuído pela IA (Cache para o App) |
| `currentClusterName` | VARCHAR(60) |                                                              | Nome do cluster atual (Cache para o App)            |
| `currentRiskLevel`   | VARCHAR(20) |                                                              | Nível de risco atual (Cache para o App)             |
| `currentHexColor`    | VARCHAR(7)  |                                                              | Cor em hexadecimal atual (Cache para o App)         |
| `createdAt`          | TIMESTAMPTZ | DEFAULT now()                                                | Data de início do registro                          |
| `updatedAt`          | TIMESTAMPTZ | DEFAULT now()                                                | Última atualização (re-classificação)               |

---

### 2.4. Tabela `app.questionario_respostas`

Registra cada check-in periódico da gestante, servindo como uma **Timeline/Histórico**. O Worker (IA) agora é a fonte da verdade: ele retorna as dicas, cores e métricas completas, que são salvas nativamente como `JSON` no banco de dados.

| Coluna                | Tipo         | Restrições                        | Descrição                                            |
| --------------------- | ------------ | --------------------------------- | ---------------------------------------------------- |
| `id`                  | UUID         | PK, DEFAULT gen_random_uuid()     | Identificador único                                  |
| `pregnancyId`         | UUID         | FK → `app.gestacoes.id`, NOT NULL | Gestação relacionada                                 |
| `currentWeight`       | NUMERIC(5,2) | NOT NULL, CHECK (30.0–250.0)      | Peso no momento do check-in (kg) — feature `nu_peso` |
| `currentAppointments` | SMALLINT     | NOT NULL, CHECK >= 0              | Consultas pré-natal realizadas até agora             |
| `hadNewComplications` | BOOLEAN      | DEFAULT FALSE                     | Novo evento clínico desde o último check-in          |
| `antiHivFlag`         | SMALLINT     | DEFAULT 0, CHECK (0–1)            | 0=não testada / 1=testada — feature opcional da IA   |
| `clusterId`           | SMALLINT     | CHECK (0–2)                       | Cluster retornado pela IA nesta resposta             |
| `clusterName`         | VARCHAR(60)  |                                   | Nome do cluster retornado                            |
| `riskLevel`           | VARCHAR(20)  |                                   | Nível de risco retornado pela IA                     |
| `hexColor`            | VARCHAR(7)   |                                   | Cor associada à classificação do momento             |
| `calculatedImc`       | NUMERIC(5,2) |                                   | IMC calculado no momento da classificação            |
| `recommendations`     | JSONB        |                                   | Array de objetos JSON contendo as dicas e categorias |
| `metrics`             | JSONB        |                                   | Objeto JSON contendo ganho de peso, CNES, etc.       |
| `responseDate`        | TIMESTAMPTZ  | DEFAULT now()                     | Timestamp do check-in                                |

**Payload enviado ao Flask** (montado pelo NestJS em `questionnaire.service.ts`):

```json
{
  "nu_peso": "Number(dto.currentWeight)",
  "nu_altura": "Number(user.height) || 1.6",
  "nu_imc_pre_gestacional": "imcPreGestacional",
  "raca_cor": "user.raceColor",
  "escolaridade": "user.educationLevel",
  "cod_municipio": "user.location?.ibgeCode || '0000000'",
  "flag_anti_hiv": "dto.antiHivFlag || 0"
}
```

> **Nota:** `nu_altura` usa valor default `1.6` para evitar quebra quando o campo for `null`.

---

## 3. DDL de Criação (Schema `app`)

```sql
CREATE SCHEMA IF NOT EXISTS app;

-- 3.1 Users (Gestantes)
CREATE TABLE app.users (
    id                       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name                     VARCHAR(150) NOT NULL,
    email                    VARCHAR(254) UNIQUE NOT NULL,
    password                 VARCHAR(255) NOT NULL,
    phone                    VARCHAR(20),
    birth_date               DATE,
    race_color               SMALLINT     CHECK (race_color BETWEEN 1 AND 5),
    height                   NUMERIC(4,2) CHECK (height BETWEEN 1.00 AND 2.50),
    pre_gestational_weight   NUMERIC(5,2) CHECK (pre_gestational_weight BETWEEN 30 AND 250),
    education_level          SMALLINT     CHECK (education_level BETWEEN 1 AND 5),
    previous_pregnancies     SMALLINT     CHECK (previous_pregnancies >= 0),
    had_previous_complication BOOLEAN     DEFAULT FALSE,
    zip_code                 VARCHAR(9)   NOT NULL,
    ibge_code                VARCHAR(7)   NOT NULL,
    created_at               TIMESTAMPTZ  DEFAULT now(),
    updated_at               TIMESTAMPTZ  DEFAULT now()
);

-- 3.2 User Locations (Localização da Gestante)
CREATE TABLE app.user_locations (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID         NOT NULL UNIQUE REFERENCES app.users(id) ON DELETE CASCADE,
    city       VARCHAR(150) NOT NULL,
    uf         VARCHAR(2)   NOT NULL,
    region     VARCHAR(50),
    ibge_code  VARCHAR(7),
    created_at TIMESTAMPTZ  DEFAULT now()
);

-- 3.3 Pregnancies (Gestações)
CREATE TABLE app.pregnancies (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID        NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
    dum_start_date    DATE,
    estimated_due_date DATE,
    status            VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active','completed','interrupted')),
    cluster_id        SMALLINT    REFERENCES app.clusters(id),
    cluster_name      VARCHAR(60),
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now()
);

-- 3.4 Questionnaires (Questionário Respostas)
CREATE TABLE app.questionnaire_responses (
    id                    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    pregnancy_id          UUID         NOT NULL REFERENCES app.pregnancies(id) ON DELETE CASCADE,
    current_weight        NUMERIC(5,2) NOT NULL CHECK (current_weight BETWEEN 30 AND 250),
    current_appointments  SMALLINT     NOT NULL CHECK (current_appointments >= 0),
    had_new_complications BOOLEAN      DEFAULT FALSE,
    anti_hiv_flag         SMALLINT     DEFAULT 0 CHECK (anti_hiv_flag IN (0, 1)),
    cluster_id            SMALLINT     REFERENCES app.clusters(id),
    cluster_name          VARCHAR(60),
    calculated_imc        NUMERIC(5,2),
    response_date         TIMESTAMPTZ  DEFAULT now()
);
```

---

## 4. Relacionamentos e Cardinalidade

| Relacionamento                         | Tipo | Descrição                                             |
| -------------------------------------- | ---- | ----------------------------------------------------- |
| `users` → `gestacoes`                  | 1:N  | Uma gestante pode ter múltiplas gestações registradas |
| `gestacoes` → `questionario_respostas` | 1:N  | Cada gestação acumula check-ins periódicos            |

---

## 5. Lógica de Integração com a IA (Flask)

O NestJS **monta o payload completo** combinando dados estáticos do perfil do usuário com o check-in parcial atual antes de publicar na fila RabbitMQ para o worker em Python:

```
questionario_respostas.peso_atual        → nu_peso
user.height                              → nu_altura
user.preGestationalWeight / altura²      → nu_imc_pre_gestacional
user.raceColor                           → raca_cor
user.educationLevel                      → escolaridade
user.location?.ibgeCode                  → cod_municipio (lookup de features municipais)
questionario_respostas.flag_anti_hiv     → flag_anti_hiv
```

Após o retorno enriquecido do Flask, o NestJS aplica o conceito de _Event Sourcing_:

1. **Histórico (Timeline):** Persiste o resultado estruturado (`cluster_id`, `cluster_nome_app`, `cor_hex`, JSON de `recomendacoes` e JSON de `metricas`) diretamente na tabela `questionario_respostas`.
2. **Cache da Dashboard:** Atualiza a tabela `gestacoes` salvando os dados de status no modelo `current_*` (ex: `current_cluster_id`, `current_hex_color`).
3. O App Frontend consome a **Gestação** para exibir o status atual de forma veloz na tela inicial, e consome a listagem de **Questionários** para montar o feed/diário histórico com as dicas armazenadas em JSONB.

---

## 6. Schema `ml_maternar` — Features Municipais (Produção)

Consultado em tempo real pelo Flask durante a inferência para preencher features de município.

```sql
CREATE SCHEMA IF NOT EXISTS ml_maternar;

CREATE TABLE ml_maternar.municipio_features (
    cod_municipio          VARCHAR(7)   NOT NULL,
    ano                    SMALLINT     NOT NULL,
    log_taxa_sifilis_gest  NUMERIC(8,4) NOT NULL DEFAULT 0,
    cnes_hospitais         NUMERIC(6,2) NOT NULL DEFAULT 2,
    cobertura_prenatal_log NUMERIC(8,4) NOT NULL DEFAULT 0,
    tem_dado_sia           BOOLEAN      NOT NULL DEFAULT FALSE,
    PRIMARY KEY (cod_municipio, ano)
);
```

---

## 7. Schema `datasus` — Dados Históricos (ETL Offline)

Tabelas de staging populadas pelo pipeline Python. **Não acessadas em produção** pelo app — servem exclusivamente ao re-treinamento do modelo.

| Tabela                            | Fonte  | Conteúdo                               |
| --------------------------------- | ------ | -------------------------------------- |
| `datasus.sisvan_gestante`         | SISVAN | Medidas antropométricas por gestante   |
| `datasus.sinan_agravos_gestantes` | SINAN  | Notificações de sífilis e toxoplasmose |
| `datasus.sim_mortalidade_materna` | SIM    | Óbitos maternos (CID O00–O99)          |
| `datasus.sia_prenatal`            | SIA    | Procedimentos pré-natais por município |
| `datasus.cnes_estabelecimentos`   | CNES   | Estabelecimentos e leitos obstétricos  |

> **Separação por schema:** `app.*` = produção | `ml_maternar.*` = inferência | `datasus.*` = treinamento offline

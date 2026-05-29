# 11 - Modelagem Detalhada de Banco de Dados: Maternar

> **Última atualização:** 2026-05-28
> **Status:** Esquema revisado — usuária com campos de perfil completo para inferência de IA.

---

## 1. Visão Geral do Modelo de Dados

O sistema mantém dois schemas no mesmo banco PostgreSQL `maternar`:

| Schema | Responsável | Propósito |
|--------|------------|-----------|
| `app` | NestJS | Dados de produção — usuárias, gestações, classificações, dicas |
| `ml_maternar` | Pipeline Python | Features municipais para inferência K-Means |
| `datasus` | ETL offline | Microdados históricos DATASUS — apenas para re-treinamento |

### Diagrama Conceitual

```
admins (autenticação admin)

users ──(1:N)──▶ gestacoes ──(1:N)──▶ questionario_respostas
                    │
                    └──(N:1)──▶ clusters ──(N:N via cluster_dicas)──▶ dicas
```

---

## 2. Tabelas do Schema `app`

### 2.1. Tabela `app.admins`

Acesso administrativo ao painel de gestão. Separado de `users` por segurança — credenciais e permissões distintas.

| Coluna | Tipo | Restrições | Descrição |
|--------|------|-----------|-----------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Identificador único |
| `nome` | VARCHAR(150) | NOT NULL | Nome completo do administrador |
| `email` | VARCHAR(254) | UNIQUE NOT NULL | E-mail de login |
| `senha_hash` | VARCHAR(255) | NOT NULL | Senha criptografada (bcrypt) |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | Data de cadastro |
| `updated_at` | TIMESTAMPTZ | DEFAULT now() | Última modificação |

> Credenciais do admin são carregadas via variáveis de ambiente no `.env` — nunca hardcoded no código.

---

### 2.2. Tabela `app.users` (Gestante)

Armazena perfil completo da gestante. Os campos de saúde presentes aqui são **estáticos ou de longa duração** (não mudam a cada consulta). Estes campos alimentam diretamente o payload enviado ao motor de IA.

| Coluna | Tipo | Restrições | Obrigatório | Descrição |
|--------|------|-----------|------------|-----------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Sim | Identificador único |
| `nome` | VARCHAR(150) | NOT NULL | Sim | Nome completo |
| `email` | VARCHAR(254) | UNIQUE NOT NULL | Sim | E-mail de login |
| `senha_hash` | VARCHAR(255) | NOT NULL | Sim | Senha criptografada (bcrypt) |
| `telefone` | VARCHAR(20) | | Não | Contato para notificações push |
| `data_nascimento` | DATE | | Não | Para cálculo de idade gestacional |
| `raca_cor` | SMALLINT | CHECK (1–5) | **Sim** | Auto-declaração — **obrigatório para inferência IA**: 1=Branca, 2=Preta, 3=Amarela, 4=Parda, 5=Indígena |
| `altura` | NUMERIC(4,2) | CHECK (1.00–2.50) | Não | Altura em metros — usada no cálculo de IMC |
| `peso_pre_gestacional` | NUMERIC(5,2) | CHECK (30.0–250.0) | Não | Peso antes da gestação (kg) — usado para `nu_imc_pre_gestacional` |
| `escolaridade` | SMALLINT | CHECK (1–5) | Não | Código ESCMAE: 1=Sem escolaridade ... 5=Superior |
| `qtd_gestacoes_ant` | SMALLINT | CHECK >= 0 | Não | Número de gestações anteriores (histórico) |
| `teve_complicacao_previa` | BOOLEAN | DEFAULT FALSE | Não | Histórico de complicação clínica grave anterior |
| `cep` | VARCHAR(9) | NOT NULL | Sim | CEP no formato `00000-000` — origem para lookup de município |
| `cod_municipio` | VARCHAR(7) | NOT NULL | Sim | Código IBGE 7 dígitos — derivado do CEP no cadastro; usado nas features municipais da IA |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | — | Data de cadastro |
| `updated_at` | TIMESTAMPTZ | DEFAULT now() | — | Última modificação de perfil |

**Notas de negócio:**
- `raca_cor` e `escolaridade` são solicitados no onboarding pois são **features obrigatórias do modelo K-Means**. Sem eles, a inferência usa valores padrão, reduzindo a precisão.
- `cod_municipio` é resolvido automaticamente a partir do CEP via API ViaCEP no momento do cadastro — o usuário não precisa informá-lo manualmente.
- `imc_pre_gestacional` é **calculado** pelo backend como `peso_pre_gestacional / altura²` antes de enviar ao Flask.

---

### 2.3. Tabela `app.gestacoes`

Cada linha representa um ciclo gestacional. Uma usuária pode ter múltiplas gestações ao longo do tempo.

| Coluna | Tipo | Restrições | Descrição |
|--------|------|-----------|-----------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Identificador único |
| `user_id` | UUID | FK → `app.users.id`, NOT NULL | Gestante proprietária |
| `data_inicio_dum` | DATE | | Data da Última Menstruação (para cálculo de IG) |
| `data_prevista_parto` | DATE | | Calculada pelo sistema (DUM + 280 dias) |
| `status` | VARCHAR(20) | CHECK ('ativa','finalizada','interrompida'), DEFAULT 'ativa' | Estado da gestação |
| `cluster_id` | SMALLINT | FK → `app.clusters.id`, CHECK (0–2) | Último cluster atribuído pela IA |
| `cluster_nome` | VARCHAR(60) | | Nome do cluster (desnormalizado para queries rápidas) |
| `created_at` | TIMESTAMPTZ | DEFAULT now() | Data de início do registro |
| `updated_at` | TIMESTAMPTZ | DEFAULT now() | Última atualização (re-classificação) |

---

### 2.4. Tabela `app.questionario_respostas`

Registra cada check-in periódico da gestante. Dados **dinâmicos** que mudam a cada consulta. O NestJS monta o payload completo para o Flask combinando estes dados com o perfil estático de `users`.

| Coluna | Tipo | Restrições | Descrição |
|--------|------|-----------|-----------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Identificador único |
| `gestacao_id` | UUID | FK → `app.gestacoes.id`, NOT NULL | Gestação relacionada |
| `peso_atual` | NUMERIC(5,2) | NOT NULL, CHECK (30.0–250.0) | Peso no momento do check-in (kg) — feature `nu_peso` |
| `num_consultas_atual` | SMALLINT | NOT NULL, CHECK >= 0 | Consultas pré-natal realizadas até agora |
| `teve_novas_complicacoes` | BOOLEAN | DEFAULT FALSE | Novo evento clínico desde o último check-in |
| `flag_anti_hiv` | SMALLINT | DEFAULT 0, CHECK (0–1) | 0=não testada / 1=testada — feature opcional da IA |
| `cluster_id` | SMALLINT | CHECK (0–2) | Cluster retornado pela IA nesta resposta |
| `cluster_nome` | VARCHAR(60) | | Nome do cluster retornado |
| `imc_calculado` | NUMERIC(5,2) | | IMC calculado no momento da classificação |
| `data_resposta` | TIMESTAMPTZ | DEFAULT now() | Timestamp do check-in |

**Payload enviado ao Flask (montado pelo NestJS):**
```json
{
  "nu_peso":               "questionario_respostas.peso_atual",
  "nu_altura":             "users.altura",
  "nu_imc_pre_gestacional":"users.peso_pre_gestacional / users.altura²",
  "raca_cor":              "users.raca_cor",
  "escolaridade":          "users.escolaridade",
  "cod_municipio":         "users.cod_municipio",
  "flag_anti_hiv":         "questionario_respostas.flag_anti_hiv"
}
```

---

### 2.5. Tabela `app.clusters` (Perfis de Cuidado — Seed)

Tabela mestre com os 3 perfis K=3 e seus nomes acolhedores. Populada uma vez via seed — nunca alterada em runtime.

| Coluna | Tipo | Restrições | Descrição |
|--------|------|-----------|-----------|
| `id` | SMALLINT | PK, CHECK (0–2) | ID técnico do cluster |
| `nome_tecnico` | VARCHAR(60) | NOT NULL | Nome clínico (ex: 'Obesidade Gestacional') |
| `nome_acolhedor` | VARCHAR(60) | NOT NULL | Nome no app (ex: 'Cuidado Integral') |
| `nivel_risco` | VARCHAR(20) | CHECK ('alto','moderado','atencao') | Nível de atenção clínica |
| `descricao` | TEXT | | Definição do perfil para equipe de saúde |
| `cor_hex` | VARCHAR(7) | | Cor da UI (C0=#FFB347, C1=#A8D8EA, C2=#FFE08A) |
| `percentual_base` | NUMERIC(5,2) | | % do cluster no conjunto de treino |

**Seed de dados:**

| id | nome_tecnico | nome_acolhedor | nivel_risco | cor_hex | % base |
|----|-------------|---------------|------------|---------|--------|
| 0 | Obesidade Gestacional | Cuidado Integral | alto | #FFB347 | 27.3% |
| 1 | Eutrofia / Baixo Peso | Caminho Seguro | moderado | #A8D8EA | 71.2% |
| 2 | Acesso Diferenciado | Atenção Redobrada | atencao | #FFE08A | 1.5% |

---

### 2.6. Tabela `app.dicas`

Conteúdo educativo personalizado por perfil.

| Coluna | Tipo | Restrições | Descrição |
|--------|------|-----------|-----------|
| `id` | SERIAL | PK | Identificador da dica |
| `titulo` | VARCHAR(150) | NOT NULL | Título chamativo |
| `conteudo` | TEXT | NOT NULL | Texto completo da orientação |
| `categoria` | VARCHAR(20) | CHECK ('nutricao','consultas','exames','alertas') | Categoria da dica |

---

### 2.7. Tabela `app.cluster_dicas` (N:N)

Associa quais dicas aparecem para quais perfis.

| Coluna | Tipo | Restrições | Descrição |
|--------|------|-----------|-----------|
| `cluster_id` | SMALLINT | FK → `app.clusters.id`, NOT NULL | Perfil de cuidado |
| `dica_id` | INTEGER | FK → `app.dicas.id`, NOT NULL | Conteúdo associado |
| PRIMARY KEY | — | (cluster_id, dica_id) | Chave composta |

---

## 3. DDL de Criação (Schema `app`)

```sql
CREATE SCHEMA IF NOT EXISTS app;

-- 3.1 Admins
CREATE TABLE app.admins (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome        VARCHAR(150)  NOT NULL,
    email       VARCHAR(254)  UNIQUE NOT NULL,
    senha_hash  VARCHAR(255)  NOT NULL,
    created_at  TIMESTAMPTZ   DEFAULT now(),
    updated_at  TIMESTAMPTZ   DEFAULT now()
);

-- 3.2 Gestantes
CREATE TABLE app.users (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    nome                    VARCHAR(150) NOT NULL,
    email                   VARCHAR(254) UNIQUE NOT NULL,
    senha_hash              VARCHAR(255) NOT NULL,
    telefone                VARCHAR(20),
    data_nascimento         DATE,
    raca_cor                SMALLINT    CHECK (raca_cor BETWEEN 1 AND 5),
    altura                  NUMERIC(4,2) CHECK (altura BETWEEN 1.00 AND 2.50),
    peso_pre_gestacional    NUMERIC(5,2) CHECK (peso_pre_gestacional BETWEEN 30 AND 250),
    escolaridade            SMALLINT    CHECK (escolaridade BETWEEN 1 AND 5),
    qtd_gestacoes_ant       SMALLINT    CHECK (qtd_gestacoes_ant >= 0),
    teve_complicacao_previa BOOLEAN     DEFAULT FALSE,
    cep                     VARCHAR(9)  NOT NULL,
    cod_municipio           VARCHAR(7)  NOT NULL,
    created_at              TIMESTAMPTZ DEFAULT now(),
    updated_at              TIMESTAMPTZ DEFAULT now()
);

-- 3.3 Perfis de cuidado (seed)
CREATE TABLE app.clusters (
    id              SMALLINT    PRIMARY KEY CHECK (id IN (0, 1, 2)),
    nome_tecnico    VARCHAR(60) NOT NULL,
    nome_acolhedor  VARCHAR(60) NOT NULL,
    nivel_risco     VARCHAR(20) CHECK (nivel_risco IN ('alto','moderado','atencao')),
    descricao       TEXT,
    cor_hex         VARCHAR(7),
    percentual_base NUMERIC(5,2)
);

INSERT INTO app.clusters VALUES
    (0, 'Obesidade Gestacional', 'Cuidado Integral',   'alto',     'Gestante com IMC pré-gestacional elevado — risco de diabetes e hipertensão.', '#FFB347', 27.3),
    (1, 'Eutrofia / Baixo Peso', 'Caminho Seguro',     'moderado', 'Perfil majoritário do SUS — acompanhamento padrão com orientação básica.',    '#A8D8EA', 71.2),
    (2, 'Acesso Diferenciado',   'Atenção Redobrada',  'atencao',  'Município com alta infraestrutura hospitalar e taxa elevada de sífilis.',     '#FFE08A',  1.5);

-- 3.4 Gestações
CREATE TABLE app.gestacoes (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID        NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
    data_inicio_dum     DATE,
    data_prevista_parto DATE,
    status              VARCHAR(20) DEFAULT 'ativa' CHECK (status IN ('ativa','finalizada','interrompida')),
    cluster_id          SMALLINT    REFERENCES app.clusters(id),
    cluster_nome        VARCHAR(60),
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

-- 3.5 Check-ins periódicos
CREATE TABLE app.questionario_respostas (
    id                      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    gestacao_id             UUID         NOT NULL REFERENCES app.gestacoes(id) ON DELETE CASCADE,
    peso_atual              NUMERIC(5,2) NOT NULL CHECK (peso_atual BETWEEN 30 AND 250),
    num_consultas_atual     SMALLINT     NOT NULL CHECK (num_consultas_atual >= 0),
    teve_novas_complicacoes BOOLEAN      DEFAULT FALSE,
    flag_anti_hiv           SMALLINT     DEFAULT 0 CHECK (flag_anti_hiv IN (0, 1)),
    cluster_id              SMALLINT     REFERENCES app.clusters(id),
    cluster_nome            VARCHAR(60),
    imc_calculado           NUMERIC(5,2),
    data_resposta           TIMESTAMPTZ  DEFAULT now()
);

-- 3.6 Dicas
CREATE TABLE app.dicas (
    id        SERIAL      PRIMARY KEY,
    titulo    VARCHAR(150) NOT NULL,
    conteudo  TEXT        NOT NULL,
    categoria VARCHAR(20) CHECK (categoria IN ('nutricao','consultas','exames','alertas'))
);

-- 3.7 Dicas por cluster (N:N)
CREATE TABLE app.cluster_dicas (
    cluster_id SMALLINT NOT NULL REFERENCES app.clusters(id),
    dica_id    INTEGER  NOT NULL REFERENCES app.dicas(id),
    PRIMARY KEY (cluster_id, dica_id)
);
```

---

## 4. Relacionamentos e Cardinalidade

| Relacionamento | Tipo | Descrição |
|---------------|------|-----------|
| `users` → `gestacoes` | 1:N | Uma gestante pode ter múltiplas gestações registradas |
| `gestacoes` → `questionario_respostas` | 1:N | Cada gestação acumula check-ins periódicos |
| `gestacoes` → `clusters` | N:1 | Muitas gestações podem ser classificadas no mesmo perfil |
| `clusters` → `dicas` | N:N via `cluster_dicas` | Um cluster exibe várias dicas; uma dica pode aparecer em vários clusters |
| `admins` | — | Tabela independente — sem FK com `users` |

---

## 5. Lógica de Integração com a IA (Flask)

O NestJS **monta o payload completo** combinando dados estáticos do perfil com o check-in atual antes de publicar na fila RabbitMQ:

```
questionario_respostas.peso_atual       → nu_peso
users.altura                            → nu_altura
users.peso_pre_gestacional / altura²    → nu_imc_pre_gestacional
users.raca_cor                          → raca_cor
users.escolaridade                      → escolaridade
users.cod_municipio                     → cod_municipio  (lookup de features municipais)
questionario_respostas.flag_anti_hiv    → flag_anti_hiv
```

Após retorno do Flask, o NestJS:
1. Atualiza `gestacoes.cluster_id` e `gestacoes.cluster_nome`
2. Persiste resultado em `questionario_respostas.cluster_id` (histórico)
3. Retorna ao app as dicas filtradas via JOIN `cluster_dicas → dicas`

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

| Tabela | Fonte | Conteúdo |
|--------|-------|---------|
| `datasus.sisvan_gestante` | SISVAN | Medidas antropométricas por gestante |
| `datasus.sinan_agravos_gestantes` | SINAN | Notificações de sífilis e toxoplasmose |
| `datasus.sim_mortalidade_materna` | SIM | Óbitos maternos (CID O00–O99) |
| `datasus.sia_prenatal` | SIA | Procedimentos pré-natais por município |
| `datasus.cnes_estabelecimentos` | CNES | Estabelecimentos e leitos obstétricos |

> **Separação por schema:** `app.*` = produção | `ml_maternar.*` = inferência | `datasus.*` = treinamento offline

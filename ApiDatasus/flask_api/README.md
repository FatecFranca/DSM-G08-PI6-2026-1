# Maternar — Flask IA Service

Serviço de inferência do modelo K-Means K=3 para classificação de perfis gestacionais.

---

## Estrutura de Arquivos

```
flask_api/
  app.py          — API HTTP Flask (health-check, endpoints de desenvolvimento)
  worker.py       — Consumidor RabbitMQ (produção)
  classifier.py   — Motor de inferência (carrega .pkl e executa predict)
  db.py           — Conexão PostgreSQL para busca de features municipais
  config.py       — Configurações lidas de variáveis de ambiente
  requirements.txt
  Dockerfile
  .env.example    — Template de credenciais
  models/         — Diretório para os artefatos .pkl (ver seção Modelos)
```

---

## Modelos Necessários

Copie os artefatos gerados pelo pipeline para `flask_api/models/`:

| Arquivo destino | Arquivo fonte (no repo) | Descrição |
|-----------------|------------------------|-----------|
| `models/kmeans_k3.pkl` | `clustering_research_output/modelos/kmeans_k3.pkl` | Modelo K-Means treinado (K=3) |
| `models/scaler_maternar.pkl` | `preprocess_output/scaler_maternar.pkl` | RobustScaler (9 features contínuas) |
| `models/pca_maternar.pkl` | `clustering_output/pca_maternar.pkl` | PCA (20 features → 8 componentes) |

```bash
# Comando de cópia (execute a partir de ApiDatasus/)
cp clustering_research_output/modelos/kmeans_k3.pkl   flask_api/models/
cp preprocess_output/scaler_maternar.pkl              flask_api/models/
cp clustering_output/pca_maternar.pkl                 flask_api/models/
```

---

## Instalação e Execução

```bash
# 1. Criar e ativar virtualenv
python3.12 -m venv .venv
source .venv/bin/activate

# 2. Instalar dependências
pip install -r flask_api/requirements.txt

# 3. Configurar credenciais
cp flask_api/.env.example flask_api/.env
# Editar flask_api/.env com as credenciais reais

# 4a. Iniciar API HTTP (desenvolvimento)
cd flask_api
python app.py

# 4b. Iniciar worker de mensageria (produção)
cd flask_api
python worker.py
```

---

## Dependência de Banco de Dados

O serviço busca features municipais no PostgreSQL antes de cada inferência.
**A tabela deve existir antes de iniciar o serviço.**

### Tabela requerida: `ml_maternar.municipio_features`

```sql
CREATE SCHEMA IF NOT EXISTS ml_maternar;

CREATE TABLE ml_maternar.municipio_features (
    cod_municipio          VARCHAR(7)     NOT NULL,
    ano                    SMALLINT       NOT NULL,
    log_taxa_sifilis_gest  NUMERIC(8, 4)  NOT NULL DEFAULT 0,
    cnes_hospitais         NUMERIC(6, 2)  NOT NULL DEFAULT 2,
    cobertura_prenatal_log NUMERIC(8, 4)  NOT NULL DEFAULT 0,
    tem_dado_sia           BOOLEAN        NOT NULL DEFAULT FALSE,
    PRIMARY KEY (cod_municipio, ano)
);

CREATE INDEX ON ml_maternar.municipio_features (cod_municipio);
```

> **Nota:** Esta tabela é populada pelo script `preprocessing_maternar.py`
> (pipeline de treinamento). Se o banco estiver vazio, o serviço usa valores
> default por município e ainda classifica — apenas com menor precisão geográfica.

---

## Integração via Mensageria (RabbitMQ) — Produção

### Padrão: RPC Assíncrono com `correlation_id`

```
Backend (Next.js)                         Worker (Python)
─────────────────                         ───────────────
1. Gera correlation_id (UUID)
2. Cria fila temporária exclusiva
   reply_to = "amq.rabbitmq.reply-to"
   (ou fila UUID efêmera)
3. Publica em "maternar.classificar"      4. Consome a mensagem
   com headers:                           5. Executa classifier.classify()
     correlation_id                       6. Publica em reply_to
     reply_to                                com mesmo correlation_id
7. Consome da reply_to
8. Verifica correlation_id
9. Retorna resultado ao App
```

### Mensagem publicada pelo Backend (payload JSON)

```json
{
  "nu_peso":                72.0,
  "nu_altura":              1.62,
  "nu_imc_pre_gestacional": 24.1,
  "raca_cor":               4,
  "escolaridade":           3,
  "cod_municipio":          "350950",
  "flag_anti_hiv":          0
}
```

### Propriedades AMQP obrigatórias

| Propriedade | Tipo | Descrição |
|-------------|------|-----------|
| `correlation_id` | string (UUID) | Identificador único da requisição |
| `reply_to` | string | Nome da fila para receber a resposta |
| `content_type` | string | Deve ser `"application/json"` |

### Mensagem de resposta do Worker

```json
{
  "correlation_id":   "a1b2c3d4-...",
  "cluster_id":       1,
  "cluster_nome":     "Eutrofia / Baixo Peso",
  "cluster_nome_app": "Caminho Seguro",
  "nivel_risco":      "moderado",
  "cor_hex":          "#A8D8EA",
  "recomendacoes": [
    {"categoria": "nutricao",  "texto": "Orientação nutricional básica; monitorar ganho de peso"},
    {"categoria": "consultas", "texto": "Garantir mínimo de 6 consultas de pré-natal (padrão SUS)"},
    {"categoria": "exames",    "texto": "Hemograma, glicemia, VDRL e anti-HIV (rotina)"},
    {"categoria": "alertas",   "texto": "Verificar se peso pré-gestacional está na faixa adequada"}
  ],
  "metricas": {
    "nu_imc_calculado":            27.43,
    "ganho_imc":                   3.33,
    "estado_nutricional":          "sobrepeso",
    "cnes_hospitais_municipio":    2.0
  }
}
```

### Resposta de erro

```json
{
  "erro":           "Payload inválido: 'nu_peso'",
  "correlation_id": "a1b2c3d4-..."
}
```

---

## Integração via HTTP — Desenvolvimento

### `POST /classificar`

```bash
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

### `GET /health`

```json
{
  "status": "ok",
  "modelo": "kmeans_k3",
  "K": 3,
  "silhouette": 0.2873,
  "uptime_s": 42.1
}
```

### `GET /clusters`

Retorna a definição completa dos 3 clusters — útil para popular a tabela
`clusters` do banco da aplicação no primeiro deploy.

---

## Schema Completo do Payload

### Campos do payload de entrada

| Campo | Tipo | Obrigatório | Intervalo | Descrição |
|-------|------|-------------|-----------|-----------|
| `nu_peso` | float | Sim | 30–250 | Peso atual em kg |
| `nu_altura` | float | Sim | 1.30–2.15 | Altura em metros |
| `nu_imc_pre_gestacional` | float | Sim | 10–80 | IMC antes da gestação |
| `raca_cor` | int | Sim | 1–5 | 1=Branca 2=Preta 3=Amarela 4=Parda 5=Indígena |
| `escolaridade` | int | Sim | 1–5 | 1=Sem escolaridade … 5=Superior completo |
| `cod_municipio` | string | Sim | — | Código IBGE 6 ou 7 dígitos |
| `flag_anti_hiv` | int | Não | 0–1 | 0=Não testada (default) / 1=Testada |

> `nu_imc`, `ganho_imc` e todas as features municipais são calculadas
> internamente — o backend **não precisa calculá-las**.

### Campos calculados internamente (não enviar)

| Campo | Como é calculado |
|-------|-----------------|
| `nu_imc` | `nu_peso / nu_altura²` |
| `ganho_imc` | `nu_imc - nu_imc_pre_gestacional` |
| `estado_nutricional` | Derivado do `nu_imc` (OMS) |
| `log_taxa_sifilis_gest` | Buscado do PostgreSQL via `cod_municipio` |
| `cnes_hospitais` | Buscado do PostgreSQL via `cod_municipio` |
| `cobertura_prenatal_log` | Buscado do PostgreSQL via `cod_municipio` |

---

## Clusters de Saída — Referência Completa

| cluster_id | cluster_nome | cluster_nome_app | nivel_risco | cor_hex | % base (n=378.969) |
|------------|-------------|-----------------|------------|---------|---------------------|
| 0 | Obesidade Gestacional | Cuidado Integral | alto | #FFB347 | 27.3% (103.418 gest.) |
| 1 | Eutrofia / Baixo Peso | Caminho Seguro | moderado | #A8D8EA | 71.2% (269.787 gest.) |
| 2 | Acesso Diferenciado | Atenção Redobrada | atencao | #FFE08A | 1.5% (5.764 gest.) |

---

## Fluxo de Dados Completo (Backend → IA → Backend)

```
App Flutter
  │ POST /api/quiz/submit
  ▼
Next.js
  │ 1. Autentica JWT
  │ 2. Valida campos obrigatórios (nu_peso, nu_altura, etc.)
  │ 3. Gera correlation_id = uuidv4()
  │ 4. Cria fila temporária reply_to
  │ 5. Publica payload em "maternar.classificar"
  │ 6. Aguarda resposta na reply_to (timeout 10 s)
  ▼
Worker Python (Flask IA)
  │ 1. Consome da fila "maternar.classificar"
  │ 2. Busca features do município no PostgreSQL
  │ 3. Monta vetor de 20 features
  │ 4. Aplica RobustScaler → PCA (8 comp.) → KMeans.predict()
  │ 5. Publica resultado em reply_to com correlation_id
  ▼
Next.js
  │ 1. Recebe e valida correlation_id
  │ 2. Salva {user_id, cluster_id, imc, municipio, timestamp} no PostgreSQL
  │ 3. Retorna resposta completa ao App
  ▼
App Flutter
  Exibe: nome acolhedor + cor + recomendações
```

---

## Configuração do RabbitMQ

```bash
# Criar usuário e vhost (executar uma vez)
rabbitmqctl add_user maternar SENHA_AQUI
rabbitmqctl add_vhost /
rabbitmqctl set_permissions -p / maternar ".*" ".*" ".*"

# Verificar filas (após o worker iniciar)
rabbitmq-diagnostics list_queues
```

---

## Variáveis de Ambiente — Referência

| Variável | Default | Descrição |
|----------|---------|-----------|
| `PGHOST` | 127.0.0.1 | Host PostgreSQL |
| `PGPORT` | 5435 | Porta PostgreSQL |
| `PGDATABASE` | maternar | Banco de dados |
| `PGUSER` | postgres | Usuário PostgreSQL |
| `PGPASSWORD` | — | Senha PostgreSQL |
| `RABBITMQ_HOST` | localhost | Host RabbitMQ |
| `RABBITMQ_PORT` | 5672 | Porta RabbitMQ |
| `RABBITMQ_USER` | maternar | Usuário RabbitMQ |
| `RABBITMQ_PASSWORD` | — | Senha RabbitMQ |
| `RABBITMQ_VHOST` | / | Virtual host |
| `QUEUE_CLASSIFY` | maternar.classificar | Fila de entrada |
| `QUEUE_DLX` | maternar.classificar.dlq | Dead-letter queue |
| `FLASK_PORT` | 5001 | Porta HTTP |
| `FLASK_DEBUG` | false | Modo debug |
| `MODEL_DIR` | /app/models | Diretório dos .pkl |
| `KMEANS_FILENAME` | kmeans_k3.pkl | Nome do arquivo KMeans |
| `SCALER_FILENAME` | scaler_maternar.pkl | Nome do arquivo Scaler |
| `PCA_FILENAME` | pca_maternar.pkl | Nome do arquivo PCA |

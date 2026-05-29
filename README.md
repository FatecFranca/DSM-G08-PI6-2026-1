# Maternar

Aplicativo móvel de acompanhamento pré-natal com classificação de perfil gestacional por Inteligência Artificial, desenvolvido com dados históricos do DATASUS.

## Sobre o Projeto

O **Maternar** utiliza um modelo K-Means (K=3) treinado com **378.969 gestantes** (DATASUS 2014–2016) para classificar o perfil de cuidado de cada gestante e fornecer orientações personalizadas em linguagem acolhedora — sem alarmismo.

**Problema:** Gestantes em situação de vulnerabilidade não recebem orientação preventiva adequada durante a gestação.

**Solução:** App Flutter que, a partir de dados simples (peso, altura, município), classifica o perfil e entrega dicas personalizadas de nutrição, consultas e exames.

---

## Perfis Identificados pelo Modelo

| Cluster | Nome Técnico | Nome no App | % da Base | Característica |
|---------|-------------|-------------|-----------|----------------|
| C0 | Obesidade Gestacional | **Cuidado Integral** | 27,3% | IMC pré-gestacional ≥ 31 |
| C1 | Eutrofia / Baixo Peso | **Caminho Seguro** | 71,2% | Grupo majoritário do SUS |
| C2 | Acesso Diferenciado | **Atenção Redobrada** | 1,5% | Município com alta infraestrutura hospitalar |

**Métricas do modelo:** Silhouette=0,2873 · Calinski-Harabász=102.169 · ARI hold-out=0,999

---

## Arquitetura

```
App Flutter
    │
    │ HTTPS
    ▼
Backend NestJS          ←──── PostgreSQL (porta 5435)
    │
    │ RabbitMQ — fila: maternar.classificar
    ▼
Worker Flask (IA)
    ├── RobustScaler → PCA (8 comp.) → KMeans K=3
    └── PostgreSQL — features municipais (ml_maternar.municipio_features)
```

Toda a infraestrutura (PostgreSQL + RabbitMQ + Worker) sobe via **Docker Compose** incluído na raiz do projeto.

---

## Estrutura do Repositório

```
├── docker-compose.yml            # Infraestrutura completa (postgres + rabbitmq + worker)
├── ApiDatasus/                   # Pipeline de dados e serviço de IA
│   ├── .env.example              # Template de variáveis de ambiente
│   ├── flask_api/                # Serviço Flask — inferência + worker RabbitMQ
│   │   ├── app.py                # HTTP endpoints (dev / health-check)
│   │   ├── worker.py             # Consumidor RabbitMQ (produção)
│   │   ├── classifier.py         # Motor de inferência K-Means
│   │   ├── db.py                 # Consulta de features municipais (PostgreSQL)
│   │   ├── config.py             # Configurações via variáveis de ambiente
│   │   ├── models/               # Artefatos ML de produção (.pkl)
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── .env.example          # Template de credenciais do serviço Flask
│   ├── main.py                   # Download de dados DATASUS
│   ├── db_loader.py              # Carga no PostgreSQL
│   ├── preprocessing_maternar.py # Feature engineering (20 features)
│   ├── gerar_notebook_research.py# Pesquisa KDD — 4 algoritmos × K=3 e K=4
│   ├── pos_processamento_k3.py   # Validação hold-out + bootstrap + gráficos
│   ├── KDD_Maternar.ipynb        # Notebook de clustering inicial
│   ├── KDD_Maternar_Research.ipynb # Notebook de pesquisa comparativa
│   ├── clustering_research_output/
│   │   ├── graficos/             # 16 gráficos comparativos (4 modelos × K=3 e K=4)
│   │   └── tabelas/              # CSVs de centroides e métricas
│   └── pos_processamento_output/
│       ├── relatorio_tecnico_k3.md
│       ├── graficos/             # 15 gráficos de validação do modelo final
│       └── *.csv                 # ANOVA, Qui-Quadrado, centroides, hold-out
│
├── Document/                     # Documentação do projeto
│   ├── 00-Apresentacao_Projeto.md
│   ├── 01-Visao_do_Produto.md
│   ├── 02-Especificacao_de_Requisitos.md
│   ├── 03-Arquitetura_de_Dados_e_IA.md
│   ├── 04-Guia_de_UX_e_Tom_de_Voz.md
│   ├── 05-Dicionario_de_Dados_DATASUS.md
│   ├── 06-Fluxo_e_Telas_da_Aplicacao.md
│   ├── 07-Questionamento_ao_Stakeholder.md
│   ├── 08-Especificacao_Tecnica_Backend.md
│   ├── 09-Pipeline_de_Treinamento_e_Mineracao.md
│   ├── 10-Entrega_Sprint_1.md
│   ├── 11-Modelagem_de_Banco_de_Dados.md
│   └── 12-Documentacao_Datasets_DATASUS.md
│
└── src/                          # Backend NestJS (Sprint 2)
```

---

## Configuração do Ambiente

### Pré-requisitos

- Python 3.12+
- Docker e Docker Compose

### 1. Variáveis de Ambiente

Crie o arquivo `.env` na raiz do projeto a partir do template:

```bash
cp ApiDatasus/.env.example .env
# Edite .env com suas senhas antes de continuar
```

O arquivo `.env` é lido pelo `docker-compose.yml` e pelos scripts Python do pipeline.

### 2. Subir a Infraestrutura

```bash
# PostgreSQL + RabbitMQ
docker compose up -d postgres rabbitmq

# Aguardar os health-checks passarem (~15 s) e verificar
docker compose ps
```

### 3. Pipeline de Dados (primeira execução)

> Execute apenas se precisar re-treinar o modelo. Os artefatos `.pkl` já estão versionados em `ApiDatasus/flask_api/models/`.

```bash
cd ApiDatasus
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r flask_api/requirements.txt

# 1. Download dos dados DATASUS (~60 GB — pode demorar horas)
python main.py

# 2. Carga no PostgreSQL
python db_loader.py

# 3. Feature engineering (gera gestante_para_cluster.parquet)
python preprocessing_maternar.py

# 4. Pesquisa KDD — compara 4 algoritmos (gera kmeans_k3.pkl)
python gerar_notebook_research.py  # ou execute KDD_Maternar_Research.ipynb

# 5. Pós-processamento — hold-out, bootstrap, gráficos
python pos_processamento_k3.py

# 6. Copiar modelos atualizados para o serviço Flask
cp clustering_research_output/modelos/kmeans_k3.pkl flask_api/models/
cp preprocess_output/scaler_maternar.pkl            flask_api/models/
cp clustering_output/pca_maternar.pkl               flask_api/models/
```

### 4. Subir o Worker de IA

```bash
# A partir da raiz do projeto
docker compose up -d worker

# Acompanhar os logs de inicialização
docker compose logs -f worker
```

Saída esperada:
```
maternar_worker | Modelos carregados — Scaler(9 feat) → PCA(8 comp) → KMeans(K=3)
maternar_worker | Pool PostgreSQL iniciado
maternar_worker | Conectado ao RabbitMQ (rabbitmq:5672)
maternar_worker | Worker aguardando mensagens em 'maternar.classificar'...
```

### 5. Criar Tabela de Features Municipais

Execute uma vez após o pipeline de dados:

```bash
docker compose exec postgres psql -U postgres -d maternar -c "
CREATE SCHEMA IF NOT EXISTS ml_maternar;
CREATE TABLE IF NOT EXISTS ml_maternar.municipio_features (
    cod_municipio          VARCHAR(7)   NOT NULL,
    ano                    SMALLINT     NOT NULL,
    log_taxa_sifilis_gest  NUMERIC(8,4) NOT NULL DEFAULT 0,
    cnes_hospitais         NUMERIC(6,2) NOT NULL DEFAULT 2,
    cobertura_prenatal_log NUMERIC(8,4) NOT NULL DEFAULT 0,
    tem_dado_sia           BOOLEAN      NOT NULL DEFAULT FALSE,
    PRIMARY KEY (cod_municipio, ano)
);"
```

---

## API de Inferência

### Via RabbitMQ (produção)

Publique na fila `maternar.classificar` com `correlation_id` e `reply_to`:

```json
{
  "nu_peso": 72.0,
  "nu_altura": 1.62,
  "nu_imc_pre_gestacional": 24.1,
  "raca_cor": 4,
  "escolaridade": 3,
  "cod_municipio": "350950"
}
```

| Campo | Tipo | Obrigatório | Valores |
|-------|------|-------------|---------|
| `nu_peso` | float | Sim | 30–250 kg |
| `nu_altura` | float | Sim | 1.30–2.15 m |
| `nu_imc_pre_gestacional` | float | Sim | 10–80 |
| `raca_cor` | int | Sim | 1=Branca 2=Preta 3=Amarela 4=Parda 5=Indígena |
| `escolaridade` | int | Sim | 1–5 |
| `cod_municipio` | string | Sim | IBGE 6 ou 7 dígitos |
| `flag_anti_hiv` | int | Não | 0=não testada (default) / 1=testada |

Resposta na fila `reply_to`:

```json
{
  "cluster_id": 1,
  "cluster_nome": "Eutrofia / Baixo Peso",
  "cluster_nome_app": "Caminho Seguro",
  "nivel_risco": "moderado",
  "cor_hex": "#A8D8EA",
  "recomendacoes": [
    {"categoria": "nutricao",  "texto": "Orientação nutricional básica; monitorar ganho de peso"},
    {"categoria": "consultas", "texto": "Garantir mínimo de 6 consultas de pré-natal (padrão SUS)"}
  ],
  "metricas": {
    "nu_imc_calculado": 27.43,
    "ganho_imc": 3.33,
    "estado_nutricional": "sobrepeso",
    "cnes_hospitais_municipio": 2.0
  }
}
```

### Via HTTP (desenvolvimento)

```bash
# Health check
curl http://localhost:5001/health

# Classificar
curl -X POST http://localhost:5001/classificar \
  -H "Content-Type: application/json" \
  -d '{"nu_peso":72,"nu_altura":1.62,"nu_imc_pre_gestacional":24.1,"raca_cor":4,"escolaridade":3,"cod_municipio":"350950"}'

# Listar definição dos 3 clusters
curl http://localhost:5001/clusters
```

> Para subir apenas o endpoint HTTP (sem worker): `docker compose run --rm -p 5001:5001 worker python app.py`

Documentação completa da API: [`ApiDatasus/flask_api/README.md`](ApiDatasus/flask_api/README.md)

---

## Dados e Fontes

| Base | Conteúdo | Linkage |
|------|----------|---------|
| SISVAN | Peso, altura, IMC, raça, escolaridade por gestante | Individual |
| SINAN | Taxa de sífilis gestacional e toxoplasmose | Município/ano |
| SIM | Taxa de mortalidade materna | Município/ano |
| SIA | Cobertura de consultas pré-natal | Município/ano |
| CNES | Quantidade de hospitais | Município/ano |

Período: 2014–2016 · Municípios: 2.573 · Gestantes: 378.969

---

## Documentação

| Documento | Descrição |
|-----------|-----------|
| [Apresentação do Projeto](Document/00-Apresentacao_Projeto.md) | Visão geral com gráficos do modelo |
| [Visão do Produto](Document/01-Visao_do_Produto.md) | Problema, solução e KPIs |
| [Arquitetura de Dados e IA](Document/03-Arquitetura_de_Dados_e_IA.md) | Pipeline e clusters K=3 |
| [Especificação Técnica Backend](Document/08-Especificacao_Tecnica_Backend.md) | Flask + NestJS + RabbitMQ |
| [Pipeline de Treinamento](Document/09-Pipeline_de_Treinamento_e_Mineracao.md) | KDD completo com métricas |
| [Modelagem de Banco de Dados](Document/11-Modelagem_de_Banco_de_Dados.md) | Schemas PostgreSQL |
| [Entrega Sprint 1](Document/10-Entrega_Sprint_1.md) | Resultados consolidados |

---

## Equipe

- Gabriel Araujo de Pádua
- Guilherme Dilio de Souza
- Sheila Alves de Araujo

---

## Stack

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.1-black?logo=flask)
![scikit-learn](https://img.shields.io/badge/scikit--learn-1.6-orange?logo=scikitlearn)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue?logo=postgresql)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-3.13-orange?logo=rabbitmq)
![Docker](https://img.shields.io/badge/Docker-Compose-blue?logo=docker)
![Flutter](https://img.shields.io/badge/Flutter-mobile-blue?logo=flutter)

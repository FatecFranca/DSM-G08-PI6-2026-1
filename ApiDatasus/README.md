# ApiDatasus — Pipeline de Dados Gestacionais (Maternar)

Pipeline de extração, processamento e carga dos dados do DATASUS para o projeto **Maternar** — app de acompanhamento de gestantes e bebês no pré-natal.

## Arquitetura

```
ApiDatasus/
├── main.py               # 1. Download dos dados do DATASUS (via pysus)
├── converter_parquet.py  # 2. Utilitário: estatísticas, consolidação, CSV
├── db_loader.py          # 3. Carga dos parquets no PostgreSQL local
├── .env.example          # Variáveis de ambiente para o banco
└── dados_gestacao_datasus/
    ├── SINASC/           # Nascidos Vivos (base principal do modelo K-Means)
    ├── SINAN/            # Agravos em Gestantes (sífilis, toxo, dengue, zika...)
    ├── SIM/              # Mortalidade Materna (CID O00-O99)
    ├── CNES/             # Estabelecimentos de Saúde (cobertura pré-natal)
    ├── SIA_PRENATAL/     # Produção Pré-Natal (proxy SISPreNatal via SIA)
    └── SISVAN/           # Estado Nutricional de Gestantes
```

## Pré-requisitos

```bash
pip install pysus pandas pyarrow psycopg2-binary numpy tqdm requests
```

| Pacote | Versão mínima |
|--------|---------------|
| Python | 3.10+ |
| pandas | 2.0+ |
| pyarrow | 10.0+ |
| pysus | 0.11+ |
| psycopg2-binary | 2.9+ |

**Recursos de sistema:**
- RAM: 8 GB recomendado (4 GB mínimo)
- Disco: 10–50 GB dependendo dos estados/anos selecionados

---

## Fluxo de Trabalho

### Passo 1 — Download dos dados

Edite as variáveis no topo de `main.py` conforme necessidade:

```python
ESTADOS = ["SP", "RJ", "MG"]   # reduzir para testes locais
ANOS    = [2021, 2022, 2023]
```

Execute:

```bash
python main.py
```

Os dados são salvos em `dados_gestacao_datasus/` como arquivos `.parquet`.

---

### Passo 2 — Verificar estatísticas (opcional)

```bash
python converter_parquet.py estatisticas
```

Saída exemplo:
```
Sistema: SINASC  (27 arquivos)
Arquivo                            Registros   Tamanho MB
SINASC_SP_2023.parquet             1.234.567        45.23
...
TOTAL                             12.500.000       312.48
```

Para consolidar arquivos mensais de CNES e SIA_PRENATAL em anuais:

```bash
python converter_parquet.py consolidar
```

---

### Passo 3 — Carga no PostgreSQL

**Configurar banco:**

```bash
cp .env.example .env
# Edite .env com suas credenciais PostgreSQL
createdb maternar
```

**Carregar todos os sistemas:**

```bash
PGPASSWORD=senha python db_loader.py
```

**Carregar sistemas específicos:**

```bash
python db_loader.py sinasc sinan          # apenas SINASC e SINAN
python db_loader.py --reset sinasc        # trunca antes de recarregar
```

**Sistemas disponíveis:** `sinasc`, `sinan`, `sim`, `cnes`, `sia`, `sisvan`

---

## Schema PostgreSQL

Todos os dados de staging ficam no schema `datasus`:

| Tabela | Sistema | Descrição |
|--------|---------|-----------|
| `datasus.sinasc_nascidos_vivos` | SINASC | Base principal: nascidos vivos, dados da gestante e parto |
| `datasus.sinan_agravos_gestantes` | SINAN | Notificações de doenças em gestantes |
| `datasus.sim_mortalidade_materna` | SIM | Óbitos maternos filtrados por CID |
| `datasus.cnes_estabelecimentos` | CNES | Hospitais e UBS com geolocalização |
| `datasus.sia_prenatal` | SIA | Procedimentos pré-natais realizados |
| `datasus.sisvan_gestante` | SISVAN | Peso, altura, IMC por semana gestacional |

Cada tabela possui:
- **Colunas tipadas** para as variáveis de maior uso no modelo ML
- **`dado_raw JSONB`** com o registro completo para consultas ad hoc
- **Índices** nas colunas de filtragem mais comuns (estado/ano, município)

Consulta exemplo:
```sql
-- Perfil das gestantes de SP com 7+ consultas de pré-natal em 2023
SELECT idademae, escmae2010, gestacao, semagestac, peso
FROM datasus.sinasc_nascidos_vivos
WHERE estado = 'SP'
  AND ano = 2023
  AND consultas = 4;  -- 4 = 7 ou mais consultas (código SINASC)
```

---

## Sistemas de Dados

### SINASC — Nascidos Vivos
Base de desfecho do modelo. Contém dados da mãe (idade, escolaridade, raça/cor, histórico gestacional) e do recém-nascido (peso, Apgar, semanas de gestação). Chave primária de linkage entre sistemas: `NUMERODO` / `CODMUNRES` + ano.

### SINAN — Agravos Notificáveis em Gestantes
Agravos baixados: Sífilis Gestante (SIFG), Sífilis Congênita (SIFC), Toxoplasmose Gestacional (TOXG), Toxoplasmose Congênita (TOXC), Dengue (DENG), Zika (ZIKA), Hepatites (HEPA), Chikungunya (CHIK). Filtro `CS_GESTANT` aplicado para agravos não exclusivos de gestantes.

### SIM — Mortalidade Materna
Óbitos filtrados por `CAUSABAS` iniciando em O00–O99 (CID-10 mortalidade materna direta e indireta). Usado para correlacionar clusters de risco com desfechos de óbito.

### CNES — Estabelecimentos de Saúde
Snapshots semestrais (janeiro e julho). Permite calcular a distância da gestante à maternidade/UBS mais próxima com leitos obstétricos (`QT_LEITO_OBS`) — feature `DISTANCIA_UTI` do modelo.

### SIA — Proxy SISPreNatal
Procedimentos pré-natais da SIGTAP filtrados por código (consulta, ultrassom, VDRL, anti-HIV, etc.). Indicador de cobertura e adesão ao pré-natal por município e faixa etária.

### SISVAN — Estado Nutricional
Dados de peso, altura e IMC por semana gestacional, disponíveis via basedosdados.org. Permite aplicar a Curva de Atalah para classificação nutricional (`ds_st_nutricional`).

---

## Dicionário Rápido de Variáveis Críticas (SINASC)

| Variável | Descrição | Uso no Modelo |
|----------|-----------|---------------|
| `IDADEMAE` | Idade da mãe (anos) | Feature normalizada |
| `ESCMAE2010` | Escolaridade (1–5) | Feature categórica |
| `QTDGESTANT` | Gestações anteriores | Feature numérica |
| `CONSULTAS` | Consultas pré-natal (faixas) | Feature categórica |
| `GESTACAO` | Semanas no parto (faixas) | Target proxy (prematuridade) |
| `SEMAGESTAC` | Semanas exatas no parto | Target proxy detalhado |
| `PESO` | Peso ao nascer (g) | Target proxy (baixo peso) |
| `RACACORMAE` | Raça/cor da mãe | Feature de disparidade |
| `CODMUNRES` | Código IBGE do município | Linkage com CNES/SNIS |
| `PARTO` | Tipo de parto (1=vaginal, 2=cesáreo) | Informação descritiva |

---

## Solução de Problemas

| Erro | Causa | Solução |
|------|-------|---------|
| `OperationalError: could not connect` | PostgreSQL não acessível | Confirmar serviço ativo e credenciais em `.env` |
| `ModuleNotFoundError: pysus` | pysus não instalado | `pip install pysus` |
| `MemoryError` durante download | Arquivo muito grande | Reduzir `ESTADOS` ou processar um estado por vez |
| Arquivo parquet vazio | Dado indisponível no DATASUS | Normal — o log registra como aviso |
| SISVAN sem arquivo | Download manual necessário | Ver instruções no `main.py` (função `instrucoes_sisvan`) |

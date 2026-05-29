"""
================================================================================
  MATERNAR — Pipeline de Pré-Processamento para K-Means Gestacional
================================================================================
  Papel:  Engenheiro de ML / Cientista de Dados
  Foco:   Mulheres grávidas e todos os fatores de risco associados à gestação.

  Estratégia:
    • Espinha individual:  SISVAN (atendimentos nutricionais de gestantes)
    • Contexto municipal:  SINAN, SIM, SIA, CNES agregados por município/ano
    • Join por (municipio_ibge 6 dígitos, ano)

  Saídas:
    PostgreSQL schema ml_maternar:
      - gestante_features     → dados limpos + features contextuais (escala real)
      - gestante_para_cluster → idem, codificado + normalizado (RobustScaler)
      - municipio_risco       → indicadores de risco por município/ano

    Arquivos:
      preprocess_output/gestante_features.parquet
      preprocess_output/gestante_para_cluster.parquet
      preprocess_output/scaler_maternar.pkl
      preprocess_output/graficos/*.png
      preprocess_output/relatorio_preprocessamento.md

  Execução:
    cd ApiDatasus
    .venv/bin/python preprocessing_maternar.py
================================================================================
"""

import os
import sys
import warnings
import datetime
import textwrap
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import psycopg2
import matplotlib
matplotlib.use("Agg")                  # sem display (servidor/headless)
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
from psycopg2.extras import execute_values
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import RobustScaler

warnings.filterwarnings("ignore")
pd.set_option("display.float_format", "{:.3f}".format)
pd.set_option("display.max_columns", 40)
sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams.update({"figure.dpi": 120, "figure.figsize": (12, 5)})

# ── Configuração ────────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     os.getenv("PGHOST",     "127.0.0.1"),
    "port":     int(os.getenv("PGPORT", "5435")),
    "database": os.getenv("PGDATABASE", "maternar"),
    "user":     os.getenv("PGUSER",     "postgres"),
    "password": os.getenv("PGPASSWORD", ""),
}

OUTPUT_DIR  = Path(__file__).parent / "preprocess_output"
GRAFICOS    = OUTPUT_DIR / "graficos"
OUTPUT_DIR.mkdir(exist_ok=True)
GRAFICOS.mkdir(exist_ok=True)

TIMESTAMP = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
BATCH_SIZE = 5_000

# ── Janela temporal com cobertura SIA consistente ────────────────────────────────
ANO_INICIO = 2014   # SIA só tem dados a partir de 2014
ANO_FIM    = 2016   # 2017 incompleto no CSV SISVAN

# ── Logging simples ─────────────────────────────────────────────────────────────

_log_lines: list[str] = []

def log(msg: str = "", level: str = "INFO") -> None:
    ts  = datetime.datetime.now().strftime("%H:%M:%S")
    out = f"[{ts}] {msg}"
    print(out)
    _log_lines.append(f"[{ts}] [{level}] {msg}")

def secao(titulo: str) -> None:
    sep = "=" * 60
    log("")
    log(sep)
    log(f"  {titulo}")
    log(sep)

# ── Banco de Dados ───────────────────────────────────────────────────────────────

def conectar() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(**DB_CONFIG)
    log(f"Conectado: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    return conn

def query_df(conn, sql: str, params=None) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)

def criar_schema_ml(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS ml_maternar;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ml_maternar.municipio_risco (
                municipio       VARCHAR(6)  NOT NULL,
                ano             SMALLINT    NOT NULL,
                -- SINAN: agravos em gestantes
                sinan_sifilis_gest    INTEGER DEFAULT 0,
                sinan_sifilis_cong    INTEGER DEFAULT 0,
                sinan_toxo_gest       INTEGER DEFAULT 0,
                sinan_dengue          INTEGER DEFAULT 0,
                sinan_zika            INTEGER DEFAULT 0,
                sinan_hepatite        INTEGER DEFAULT 0,
                sinan_chik            INTEGER DEFAULT 0,
                -- SIM: mortalidade materna
                sim_obitos_maternos   INTEGER DEFAULT 0,
                sim_hipertensivos     INTEGER DEFAULT 0,
                sim_hemorragicos      INTEGER DEFAULT 0,
                -- SIA: cobertura pré-natal
                sia_consultas_prenatal  BIGINT  DEFAULT 0,
                sia_vdrl                BIGINT  DEFAULT 0,
                sia_anti_hiv            BIGINT  DEFAULT 0,
                sia_ultrassom           BIGINT  DEFAULT 0,
                sia_glicemia            BIGINT  DEFAULT 0,
                sia_toxo_exame          BIGINT  DEFAULT 0,
                -- CNES: infraestrutura
                cnes_hospitais          INTEGER DEFAULT 0,
                cnes_leitos_obs         INTEGER DEFAULT 0,
                -- Taxas derivadas (por 1000 consultas pré-natais)
                taxa_sifilis_gest       DECIMAL(18,4),
                taxa_sifilis_cong       DECIMAL(18,4),
                taxa_toxo_gest          DECIMAL(18,4),
                taxa_mortalidade_materna DECIMAL(18,4),
                -- Taxas em escala log1p (prontas para normalização)
                log_taxa_sifilis_gest   FLOAT8,
                -- Flags de cobertura (1=disponível no município naquele ano)
                flag_vdrl               SMALLINT DEFAULT 0,
                flag_anti_hiv           SMALLINT DEFAULT 0,
                flag_ultrassom          SMALLINT DEFAULT 0,
                tem_dado_sia            SMALLINT DEFAULT 0,
                inserted_at             TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (municipio, ano)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ml_maternar.gestante_features (
                id                          BIGSERIAL PRIMARY KEY,
                sisvan_id                   BIGINT,
                ano                         SMALLINT,
                municipio                   VARCHAR(6),
                -- Individuais SISVAN
                nu_peso                     DECIMAL(6,2),
                nu_altura                   DECIMAL(5,2),
                nu_imc                      DECIMAL(6,2),
                nu_imc_pre_gestacional      DECIMAL(6,2),
                ganho_imc                   DECIMAL(6,2),
                estado_nutricional_cod      SMALLINT,
                raca_cor                    SMALLINT,
                escolaridade                SMALLINT,
                -- Contextuais municipais (de municipio_risco)
                sinan_sifilis_gest          INTEGER,
                sinan_toxo_gest             INTEGER,
                sinan_dengue                INTEGER,
                sinan_zika                  INTEGER,
                sim_obitos_maternos         INTEGER,
                sia_consultas_prenatal      BIGINT,
                taxa_sifilis_gest           DECIMAL(18,4),
                taxa_toxo_gest              DECIMAL(18,4),
                taxa_mortalidade_materna    DECIMAL(18,4),
                log_taxa_sifilis_gest       FLOAT8,
                flag_vdrl                   SMALLINT,
                flag_anti_hiv               SMALLINT,
                flag_ultrassom              SMALLINT,
                tem_dado_sia                SMALLINT DEFAULT 0,
                cnes_hospitais              INTEGER,
                cnes_leitos_obs             INTEGER,
                inserted_at                 TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ml_maternar.gestante_para_cluster (
                id                          BIGSERIAL PRIMARY KEY,
                gestante_feature_id         BIGINT,
                -- Todas as features numéricas normalizadas (RobustScaler)
                -- Ordinais
                nu_imc                      FLOAT8,
                nu_imc_pre_gestacional      FLOAT8,
                ganho_imc                   FLOAT8,
                nu_peso                     FLOAT8,
                nu_altura                   FLOAT8,
                escolaridade                FLOAT8,
                log_taxa_sifilis_gest       FLOAT8,
                cobertura_prenatal_log      FLOAT8,
                cnes_hospitais              FLOAT8,
                -- Nominais OHE: estado nutricional
                est_nut_baixo_peso          SMALLINT,
                est_nut_adequado            SMALLINT,
                est_nut_sobrepeso           SMALLINT,
                est_nut_obesidade           SMALLINT,
                -- Nominais OHE: raça/cor
                raca_branca                 SMALLINT,
                raca_preta                  SMALLINT,
                raca_parda                  SMALLINT,
                raca_amarela                SMALLINT,
                raca_indigena               SMALLINT,
                -- Flags binárias
                flag_anti_hiv               SMALLINT,
                tem_dado_sia                SMALLINT,
                inserted_at                 TIMESTAMPTZ DEFAULT NOW()
            );
        """)
    conn.commit()
    log("Schema ml_maternar e tabelas criadas/verificadas.")

def salvar_df_pg(conn, df: pd.DataFrame, tabela: str, colunas: list[str]) -> int:
    """Insere DataFrame no PostgreSQL em batches."""
    linhas = [tuple(row) for row in df[colunas].itertuples(index=False, name=None)]
    if not linhas:
        return 0
    sql = f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES %s"
    with conn.cursor() as cur:
        execute_values(cur, sql, linhas, page_size=BATCH_SIZE)
    conn.commit()
    return len(linhas)

# ── Utilitários ──────────────────────────────────────────────────────────────────

def salvar_fig(nome: str, fig=None) -> None:
    path = GRAFICOS / nome
    (fig or plt).savefig(path, bbox_inches="tight")
    if fig:
        plt.close(fig)
    else:
        plt.close()
    log(f"  Gráfico salvo: {path.name}")

def norm_mun(s: pd.Series) -> pd.Series:
    """Normaliza código de município para 6 dígitos (remove prefixos de 7 dígitos)."""
    return s.astype(str).str.strip().str.lstrip("0").str[-6:].str.zfill(6)

def aplicar_iqr_capping(df: pd.DataFrame, colunas: list[str], fator: float = 1.5):
    df_out = df.copy()
    relatorio = []
    for col in colunas:
        if col not in df_out.columns or df_out[col].isna().all():
            continue
        Q1, Q3 = df_out[col].quantile([0.25, 0.75])
        IQR = Q3 - Q1
        if IQR == 0:
            # Fallback: usar percentil 99 como teto (comum em taxas epidemiológicas esparsas)
            lim_inf = df_out[col].quantile(0.01)
            lim_sup = df_out[col].quantile(0.99)
            if lim_sup == lim_inf:
                continue
        else:
            lim_inf = Q1 - fator * IQR
            lim_sup = Q3 + fator * IQR
        n_out = int(((df_out[col] < lim_inf) | (df_out[col] > lim_sup)).sum())
        df_out[col] = df_out[col].clip(lower=lim_inf, upper=lim_sup)
        relatorio.append({
            "variavel": col, "lim_inf": round(lim_inf, 2),
            "lim_sup": round(lim_sup, 2), "outliers_tratados": n_out,
        })
    return df_out, pd.DataFrame(relatorio)

# ── PASSO 1 — Extração e Limpeza SISVAN ─────────────────────────────────────────

ESTADO_NUTRICIONAL_MAP = {
    # CSV format (ds_st_nutricional field — texto)
    "baixo peso":                     0,
    "magreza":                        0,
    "magreza grave":                  0,
    "adequado ou eutrófico":          1,
    "eutrofico":                      1,
    "eutrófico":                      1,
    "adequado":                       1,
    "sobrepeso":                      2,
    "obesidade":                      3,
    "obesidade grau i":               3,
    "obesidade grau ii":              4,
    "obesidade grau iii":             5,
    "obeso":                          3,
    # Numeric codes (CO_ESTADO_NUTRI_IMC_SEMGEST)
    "1":                              0,
    "2":                              1,
    "3":                              2,
    "4":                              3,
}

def codificar_estado_nutricional(serie: pd.Series) -> pd.Series:
    return (
        serie.astype(str)
             .str.lower()
             .str.strip()
             .map(ESTADO_NUTRICIONAL_MAP)
    )

def extrair_sisvan(conn) -> pd.DataFrame:
    secao("PASSO 1 — Extração SISVAN (individual)")
    sql = f"""
        SELECT
            id                              AS sisvan_id,
            ano,
            LPAD(SUBSTRING(co_municipio_ibge, 1, 6), 6, '0') AS municipio,
            nu_peso,
            nu_altura,
            nu_imc,
            nu_imc_pre_gestacional,
            ds_st_nutricional               AS estado_nutricional_raw,
            co_raca_cor,
            nu_escolaridade
        FROM datasus.sisvan_gestante
        WHERE nu_peso IS NOT NULL
          AND nu_altura IS NOT NULL
          AND nu_imc   IS NOT NULL
          AND ano BETWEEN {ANO_INICIO} AND {ANO_FIM}
    """
    log("Carregando SISVAN do banco...")
    df = query_df(conn, sql)
    log(f"  Registros brutos: {len(df):,}")

    # ── Normalizar município
    df["municipio"] = norm_mun(df["municipio"])

    # ── Converter tipos
    for col in ["nu_peso", "nu_altura", "nu_imc", "nu_imc_pre_gestacional"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["co_raca_cor"] = pd.to_numeric(df["co_raca_cor"], errors="coerce")
    df["co_raca_cor"] = df["co_raca_cor"].replace({99: np.nan, 0: np.nan})

    # nu_escolaridade = anos de estudo (1–15); 99/0 = ignorado
    esc_raw = pd.to_numeric(df["nu_escolaridade"], errors="coerce")
    esc_raw = esc_raw.replace({99: np.nan, 0: np.nan})
    # Binar anos de estudo em 5 níveis ordinais
    # 1-3 = Fundamental I incompleto | 4-7 = Fundamental | 8-10 = Médio | 11-14 = Superior | 15+ = Pós
    df["nu_escolaridade"] = pd.cut(
        esc_raw,
        bins=[0, 3, 7, 10, 14, 100],
        labels=[1, 2, 3, 4, 5],
        include_lowest=True,
    ).astype(float)

    # ── Codificar estado nutricional
    df["estado_nutricional_cod"] = codificar_estado_nutricional(df["estado_nutricional_raw"])

    # ── Feature: ganho de IMC (proxy peso ganho)
    df["ganho_imc"] = df["nu_imc"] - df["nu_imc_pre_gestacional"]

    # ── Filtros de consistência biológica
    antes = len(df)
    df = df[
        df["nu_peso"].between(30, 200) &
        df["nu_altura"].between(1.3, 2.2) &
        df["nu_imc"].between(10, 80) &
        df["nu_imc_pre_gestacional"].between(10, 80)
    ].copy()
    log(f"  Inconsistências biológicas removidas: {antes - len(df):,}")

    # ── Remover registros com >50% de campos nulos
    cols_analise = ["nu_peso", "nu_altura", "nu_imc", "nu_imc_pre_gestacional",
                    "estado_nutricional_cod", "co_raca_cor", "nu_escolaridade"]
    mask = df[cols_analise].isnull().mean(axis=1) < 0.6
    antes = len(df)
    df = df[mask].reset_index(drop=True)
    log(f"  Removidos por excesso de nulos (>60%): {antes - len(df):,}")
    log(f"  SISVAN após limpeza: {len(df):,} registros")

    return df

# ── PASSO 2 — Agregação Municipal (toda via SQL para economizar RAM) ─────────────

def agregar_sinan(conn) -> pd.DataFrame:
    secao("PASSO 2a — Agregação SINAN por município/ano")
    sql = """
        SELECT
            LPAD(id_municip, 6, '0')                              AS municipio,
            ano,
            COUNT(*) FILTER (WHERE agravo = 'SIFG')              AS sinan_sifilis_gest,
            COUNT(*) FILTER (WHERE agravo = 'SIFC')              AS sinan_sifilis_cong,
            COUNT(*) FILTER (WHERE agravo = 'TOXG')              AS sinan_toxo_gest,
            COUNT(*) FILTER (WHERE agravo = 'DENG')              AS sinan_dengue,
            COUNT(*) FILTER (WHERE agravo = 'ZIKA')              AS sinan_zika,
            COUNT(*) FILTER (WHERE agravo = 'HEPA')              AS sinan_hepatite,
            COUNT(*) FILTER (WHERE agravo = 'CHIK')              AS sinan_chik
        FROM datasus.sinan_agravos_gestantes
        WHERE id_municip IS NOT NULL AND id_municip != ''
        GROUP BY id_municip, ano
    """
    df = query_df(conn, sql)
    df["municipio"] = norm_mun(df["municipio"])
    for c in df.columns[2:]:
        df[c] = df[c].fillna(0).astype(int)
    log(f"  SINAN: {len(df):,} combinações município/ano")
    return df

def agregar_sim(conn) -> pd.DataFrame:
    secao("PASSO 2b — Agregação SIM por município/ano")
    sql = """
        SELECT
            LPAD(codmunres, 6, '0')                              AS municipio,
            ano,
            COUNT(*)                                             AS sim_obitos_maternos,
            COUNT(*) FILTER (WHERE causabas LIKE 'O1%')          AS sim_hipertensivos,
            COUNT(*) FILTER (WHERE causabas LIKE 'O7%'
                               OR  causabas LIKE 'O44%'
                               OR  causabas LIKE 'O45%'
                               OR  causabas LIKE 'O46%')         AS sim_hemorragicos
        FROM datasus.sim_mortalidade_materna
        WHERE causabas LIKE 'O%'
          AND codmunres IS NOT NULL
        GROUP BY codmunres, ano
    """
    df = query_df(conn, sql)
    df["municipio"] = norm_mun(df["municipio"])
    for c in df.columns[2:]:
        df[c] = df[c].fillna(0).astype(int)
    log(f"  SIM: {len(df):,} combinações município/ano (apenas óbitos CID O%)")
    return df

def agregar_sia(conn) -> pd.DataFrame:
    secao("PASSO 2c — Agregação SIA por município/ano")
    sql = """
        SELECT
            LPAD(pa_munpcn, 6, '0')                              AS municipio,
            ano,
            COALESCE(SUM(pa_qtdapr) FILTER (
                WHERE pa_proc_id = '0301010072'), 0)             AS sia_consultas_prenatal,
            COALESCE(SUM(pa_qtdapr) FILTER (
                WHERE pa_proc_id = '0202050025'), 0)             AS sia_vdrl,
            COALESCE(SUM(pa_qtdapr) FILTER (
                WHERE pa_proc_id = '0214010015'), 0)             AS sia_anti_hiv,
            COALESCE(SUM(pa_qtdapr) FILTER (
                WHERE pa_proc_id IN ('0209010061','0209010070')), 0) AS sia_ultrassom,
            COALESCE(SUM(pa_qtdapr) FILTER (
                WHERE pa_proc_id = '0202010597'), 0)             AS sia_glicemia,
            COALESCE(SUM(pa_qtdapr) FILTER (
                WHERE pa_proc_id = '0202010201'), 0)             AS sia_toxo_exame
        FROM datasus.sia_prenatal
        WHERE pa_munpcn IS NOT NULL
          AND pa_proc_id IN (
              '0301010072','0202050025','0214010015',
              '0209010061','0209010070','0202010597','0202010201'
          )
        GROUP BY pa_munpcn, ano
    """
    log("  Agregando SIA (32 GB) — pode demorar 2–4 minutos...")
    df = query_df(conn, sql)
    df["municipio"] = norm_mun(df["municipio"])
    for c in df.columns[2:]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype("int64")
    log(f"  SIA: {len(df):,} combinações município/ano")
    return df

def agregar_cnes(conn) -> pd.DataFrame:
    secao("PASSO 2d — Agregação CNES por município/ano")
    # codmunicipio e tp_unidade ficaram NULL no carregamento;
    # os valores reais estão em dado_raw->>'CODUFMUN' e dado_raw->>'TP_UNID'
    # Tipos relevantes: 05=Hospital Geral, 07=Hospital Especializado,
    #                   15=Maternidade, 61=Centro de Parto Normal
    sql = f"""
        SELECT
            LPAD(dado_raw->>'CODUFMUN', 6, '0')                  AS municipio,
            ano,
            COUNT(DISTINCT cnes)                                 AS cnes_hospitais
        FROM datasus.cnes_estabelecimentos
        WHERE dado_raw->>'CODUFMUN' IS NOT NULL
          AND dado_raw->>'TP_UNID' IN ('05','07','15','61')
          AND ano BETWEEN {ANO_INICIO} AND {ANO_FIM}
        GROUP BY dado_raw->>'CODUFMUN', ano
    """
    df = query_df(conn, sql)
    df["municipio"] = norm_mun(df["municipio"])
    df["cnes_hospitais"] = pd.to_numeric(df["cnes_hospitais"], errors="coerce").fillna(0).astype(int)
    log(f"  CNES: {len(df):,} combinações município/ano")
    return df

# ── PASSO 3 — Construção da Tabela Municipal de Risco ───────────────────────────

def construir_municipio_risco(
    df_sinan: pd.DataFrame,
    df_sim:   pd.DataFrame,
    df_sia:   pd.DataFrame,
    df_cnes:  pd.DataFrame,
) -> pd.DataFrame:
    secao("PASSO 3 — Construção municipio_risco")

    # Base: todos municípios/anos do SIA (maior cobertura)
    base = df_sia[["municipio", "ano"]].drop_duplicates()

    df = base.merge(df_sinan, on=["municipio", "ano"], how="left")
    df = df.merge(df_sim,   on=["municipio", "ano"], how="left")
    df = df.merge(df_sia,   on=["municipio", "ano"], how="left")
    df = df.merge(df_cnes,  on=["municipio", "ano"], how="left")

    # Preencher zeros onde não houve notificação/óbito
    cols_fill_zero = [
        "sinan_sifilis_gest", "sinan_sifilis_cong", "sinan_toxo_gest",
        "sinan_dengue", "sinan_zika", "sinan_hepatite", "sinan_chik",
        "sim_obitos_maternos", "sim_hipertensivos", "sim_hemorragicos",
        "sia_consultas_prenatal", "sia_vdrl", "sia_anti_hiv", "sia_ultrassom",
        "sia_glicemia", "sia_toxo_exame", "cnes_hospitais",
    ]
    for c in cols_fill_zero:
        if c in df.columns:
            df[c] = df[c].fillna(0)

    # ── Calcular taxas (por 1.000 consultas pré-natais — usa SIA como denominador)
    denom = df["sia_consultas_prenatal"].replace(0, np.nan)

    df["taxa_sifilis_gest"]        = (df["sinan_sifilis_gest"]   / denom * 1000).round(4)
    df["taxa_sifilis_cong"]        = (df["sinan_sifilis_cong"]   / denom * 1000).round(4)
    df["taxa_toxo_gest"]           = (df["sinan_toxo_gest"]      / denom * 1000).round(4)
    df["taxa_mortalidade_materna"] = (df["sim_obitos_maternos"]  / denom * 1000).round(4)

    # CORREÇÃO 1 — log1p nas taxas para normalização robusta do K-Means
    # Resolve: RobustScaler falha quando mediana=0 e IQR≈0 (taxas esparsas)
    df["log_taxa_sifilis_gest"] = np.log1p(df["taxa_sifilis_gest"].fillna(0))

    # ── Flags de cobertura
    df["flag_vdrl"]      = (df["sia_vdrl"]      > 0).astype(int)
    df["flag_anti_hiv"]  = (df["sia_anti_hiv"]  > 0).astype(int)
    df["flag_ultrassom"] = (df["sia_ultrassom"]  > 0).astype(int)

    # CORREÇÃO 3 — flag explícito: 1 = município/ano com dado SIA real, 0 = imputado
    df["tem_dado_sia"] = 1  # todos os registros da base vêm do SIA (base do merge)

    log(f"  municipio_risco: {len(df):,} combinações município/ano")
    return df

# ── PASSO 4 — Join Individual × Municipal ───────────────────────────────────────

def construir_gestante_features(
    df_sisvan: pd.DataFrame,
    df_mun:    pd.DataFrame,
) -> pd.DataFrame:
    secao("PASSO 4 — Join SISVAN × municipio_risco")

    # Colunas contextuais a trazer
    cols_mun = [
        "municipio", "ano",
        "sinan_sifilis_gest", "sinan_toxo_gest", "sinan_dengue", "sinan_zika",
        "sim_obitos_maternos",
        "sia_consultas_prenatal",
        "taxa_sifilis_gest", "taxa_sifilis_cong", "taxa_toxo_gest",
        "taxa_mortalidade_materna",
        "log_taxa_sifilis_gest",
        "flag_vdrl", "flag_anti_hiv", "flag_ultrassom",
        "tem_dado_sia",
        "cnes_hospitais",
    ]
    df_mun_slim = df_mun[[c for c in cols_mun if c in df_mun.columns]].copy()

    df = df_sisvan.merge(df_mun_slim, on=["municipio", "ano"], how="left")
    log(f"  gestante_features: {len(df):,} registros")

    # ── Renomear para clareza
    df.rename(columns={
        "co_raca_cor":    "raca_cor",
        "nu_escolaridade": "escolaridade",
    }, inplace=True)

    return df

# ── PASSO 5 — Análise Exploratória e Validação ──────────────────────────────────

RACA_MAP = {1: "Branca", 2: "Preta", 3: "Amarela", 4: "Parda", 5: "Indígena"}
ESC_MAP  = {1: "Fund.I Incomp.\n(1-3 anos)", 2: "Fundamental\n(4-7 anos)",
            3: "Médio\n(8-10 anos)", 4: "Superior\n(11-14 anos)", 5: "Pós-Grad\n(15+ anos)"}
EST_NUT_MAP = {0: "Baixo Peso", 1: "Adequado", 2: "Sobrepeso", 3: "Obesidade I",
               4: "Obesidade II", 5: "Obesidade III"}

_relatorio_linhas: list[str] = []

def rel(s: str = "") -> None:
    _relatorio_linhas.append(s)

def analise_exploratoria(df: pd.DataFrame) -> dict:
    secao("PASSO 5 — Análise Exploratória e Validação")
    stats: dict = {}

    # ── 5.1 Nulos por variável
    log("  5.1 Valores ausentes por variável")
    nulos = (df.isnull().sum() / len(df) * 100).sort_values(ascending=False)
    nulos_plot = nulos[nulos > 0]

    fig, ax = plt.subplots(figsize=(10, max(4, len(nulos_plot) * 0.4)))
    if len(nulos_plot) > 0:
        nulos_plot.plot(kind="barh", ax=ax, color="steelblue", edgecolor="white")
        ax.set_title("Percentual de Valores Ausentes por Variável")
        ax.set_xlabel("% ausente")
        ax.xaxis.set_major_formatter(mticker.PercentFormatter())
    else:
        ax.text(0.5, 0.5, "Sem valores ausentes", ha="center", va="center", fontsize=14)
    plt.tight_layout()
    salvar_fig("01_valores_ausentes.png", fig)
    stats["nulos"] = nulos_plot.to_dict()

    # ── 5.2 Distribuição IMC individual
    log("  5.2 Distribuições IMC")
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for ax, col, titulo in zip(
        axes,
        ["nu_imc", "nu_imc_pre_gestacional", "ganho_imc"],
        ["IMC Atual", "IMC Pré-Gestacional", "Ganho de IMC"],
    ):
        data = df[col].dropna()
        ax.hist(data, bins=50, color="steelblue", edgecolor="white", alpha=0.8)
        ax.axvline(data.median(), color="red", linestyle="--", label=f"Mediana: {data.median():.1f}")
        ax.set_title(titulo)
        ax.legend(fontsize=8)
    plt.suptitle("Distribuição de IMC das Gestantes", fontsize=13, y=1.02)
    plt.tight_layout()
    salvar_fig("02_distribuicao_imc.png", fig)

    # ── 5.3 Estado nutricional
    log("  5.3 Estado nutricional")
    nut_counts = df["estado_nutricional_cod"].value_counts().sort_index()
    nut_labels = [EST_NUT_MAP.get(k, str(k)) for k in nut_counts.index]
    fig, ax = plt.subplots(figsize=(9, 4))
    bars = ax.bar(nut_labels, nut_counts.values, color=sns.color_palette("RdYlGn_r", len(nut_counts)))
    for bar, val in zip(bars, nut_counts.values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 200,
                f"{val:,}", ha="center", va="bottom", fontsize=9)
    ax.set_title("Estado Nutricional das Gestantes (SISVAN)")
    ax.set_ylabel("Quantidade")
    plt.tight_layout()
    salvar_fig("03_estado_nutricional.png", fig)
    stats["estado_nutricional"] = dict(zip(nut_labels, nut_counts.values.tolist()))

    # ── 5.4 Raça/cor
    log("  5.4 Raça/cor")
    raca_counts = df["raca_cor"].value_counts().sort_index()
    raca_labels = [RACA_MAP.get(int(k), str(k)) for k in raca_counts.index]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(raca_labels, raca_counts.values, color=sns.color_palette("pastel", len(raca_counts)))
    ax.set_title("Distribuição Raça/Cor — Gestantes")
    ax.set_ylabel("Quantidade")
    plt.tight_layout()
    salvar_fig("04_raca_cor.png", fig)

    # ── 5.5 Escolaridade
    log("  5.5 Escolaridade")
    esc_counts = df["escolaridade"].value_counts().sort_index()
    esc_labels = [ESC_MAP.get(int(k), str(k)) for k in esc_counts.index]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(esc_labels, esc_counts.values, color=sns.color_palette("Blues_d", len(esc_counts)))
    ax.set_title("Distribuição Escolaridade — Gestantes")
    ax.set_ylabel("Quantidade")
    plt.tight_layout()
    salvar_fig("05_escolaridade.png", fig)

    # ── 5.6 Distribuição temporal
    log("  5.6 Distribuição por ano")
    ano_counts = df["ano"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(ano_counts.index.astype(str), ano_counts.values, color="steelblue", edgecolor="white")
    ax.set_title("Gestantes por Ano — SISVAN")
    ax.set_ylabel("Quantidade")
    for tick in ax.get_xticklabels():
        tick.set_rotation(45)
    plt.tight_layout()
    salvar_fig("06_distribuicao_ano.png", fig)
    stats["por_ano"] = ano_counts.to_dict()

    # ── 5.7 Correlação entre features contínuas
    log("  5.7 Mapa de correlação")
    cols_corr = ["nu_peso", "nu_altura", "nu_imc", "nu_imc_pre_gestacional",
                 "ganho_imc", "log_taxa_sifilis_gest", "taxa_mortalidade_materna",
                 "cnes_hospitais"]
    cols_corr = [c for c in cols_corr if c in df.columns and df[c].notna().sum() > 100]
    if len(cols_corr) >= 3:
        corr = df[cols_corr].corr()
        fig, ax = plt.subplots(figsize=(10, 8))
        mask = np.triu(np.ones_like(corr, dtype=bool))
        sns.heatmap(corr, mask=mask, annot=True, fmt=".2f", cmap="coolwarm",
                    center=0, ax=ax, linewidths=0.5, annot_kws={"size": 8})
        ax.set_title("Correlação entre Features (sem escala)")
        plt.tight_layout()
        salvar_fig("07_correlacao.png", fig)

    # ── 5.8 Boxplots contínuos
    log("  5.8 Boxplots — outliers")
    cols_box = ["nu_peso", "nu_altura", "nu_imc", "nu_imc_pre_gestacional", "ganho_imc"]
    cols_box = [c for c in cols_box if c in df.columns]
    fig, axes = plt.subplots(1, len(cols_box), figsize=(3 * len(cols_box), 5))
    if len(cols_box) == 1:
        axes = [axes]
    for ax, col in zip(axes, cols_box):
        ax.boxplot(df[col].dropna(), patch_artist=True,
                   boxprops=dict(facecolor="steelblue", alpha=0.6))
        ax.set_title(col, fontsize=9)
        ax.set_xticks([])
    plt.suptitle("Boxplots das Variáveis Contínuas (antes do capping)", y=1.02)
    plt.tight_layout()
    salvar_fig("08_boxplots_antes_capping.png", fig)

    # ── 5.9 Taxa de sífilis por ano (contexto municipal)
    log("  5.9 Taxas de risco municipal por ano")
    if "log_taxa_sifilis_gest" in df.columns:
        taxa_ano = df.groupby("ano")["log_taxa_sifilis_gest"].median().dropna()
        if not taxa_ano.empty:
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(taxa_ano.index, taxa_ano.values, marker="o", color="crimson")
            ax.fill_between(taxa_ano.index, taxa_ano.values, alpha=0.2, color="crimson")
            ax.set_title("Mediana de log(1 + Taxa de Sífilis Gestacional) por Ano")
            ax.set_ylabel("log(1 + taxa/1.000 consultas)")
            ax.set_xlabel("Ano")
            plt.tight_layout()
            salvar_fig("09_taxa_sifilis_por_ano.png", fig)

    # ── 5.10 Cobertura pré-natal
    log("  5.10 Cobertura pré-natal por ano")
    if "sia_consultas_prenatal" in df.columns:
        cob = df.groupby("ano")["sia_consultas_prenatal"].sum().dropna()
        if not cob.empty:
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.bar(cob.index.astype(str), cob.values / 1e6, color="teal", edgecolor="white")
            ax.set_title("Total de Consultas Pré-Natais Aprovadas (SIA) por Ano — municípios das gestantes SISVAN")
            ax.set_ylabel("Milhões de consultas")
            for tick in ax.get_xticklabels():
                tick.set_rotation(45)
            plt.tight_layout()
            salvar_fig("10_cobertura_prenatal_ano.png", fig)

    # ── Estatísticas descritivas
    stats_desc = df[["nu_peso", "nu_altura", "nu_imc", "nu_imc_pre_gestacional",
                      "ganho_imc"]].describe().round(3)
    stats["descritivas"] = stats_desc.to_dict()
    log(f"\n  Estatísticas descritivas:\n{stats_desc}")

    return stats

# ── PASSO 6 — Tratamento de Valores Ausentes ────────────────────────────────────

def tratar_ausentes(df: pd.DataFrame) -> pd.DataFrame:
    secao("PASSO 6 — Tratamento de Valores Ausentes")

    antes = df.isnull().sum().sum()
    log(f"  Total de nulos antes: {antes:,}")

    # Contínuas individuais: imputar mediana
    cols_continuas_ind = ["nu_peso", "nu_altura", "nu_imc", "nu_imc_pre_gestacional", "ganho_imc"]
    cols_continuas_ind = [c for c in cols_continuas_ind if c in df.columns]
    imp_med = SimpleImputer(strategy="median")
    df[cols_continuas_ind] = imp_med.fit_transform(df[cols_continuas_ind])

    # Ordinais individuais: imputar moda
    cols_ord_ind = ["escolaridade", "raca_cor", "estado_nutricional_cod"]
    cols_ord_ind = [c for c in cols_ord_ind if c in df.columns]
    imp_moda = SimpleImputer(strategy="most_frequent")
    df[cols_ord_ind] = imp_moda.fit_transform(df[cols_ord_ind])

    # Taxas contextuais: imputar mediana (se município não tem dado, usa mediana geral)
    cols_taxas = ["taxa_sifilis_gest", "taxa_sifilis_cong", "taxa_toxo_gest",
                  "taxa_mortalidade_materna", "log_taxa_sifilis_gest", "cnes_hospitais"]
    cols_taxas = [c for c in cols_taxas if c in df.columns]
    imp_med2 = SimpleImputer(strategy="median")
    df[cols_taxas] = imp_med2.fit_transform(df[cols_taxas])

    # Flags: preencher com 0 (ausência de cobertura)
    cols_flags = ["flag_vdrl", "flag_anti_hiv", "flag_ultrassom", "tem_dado_sia"]
    for c in cols_flags:
        if c in df.columns:
            df[c] = df[c].fillna(0).astype(int)

    # Contagens de agravos: 0 se sem registro
    cols_counts = ["sinan_sifilis_gest", "sinan_toxo_gest", "sinan_dengue",
                   "sinan_zika", "sim_obitos_maternos", "sia_consultas_prenatal"]
    for c in cols_counts:
        if c in df.columns:
            df[c] = df[c].fillna(0)

    depois = df.isnull().sum().sum()
    log(f"  Total de nulos após imputação: {depois:,}")

    return df

# ── PASSO 7 — Tratamento de Outliers ────────────────────────────────────────────

def tratar_outliers(df: pd.DataFrame) -> pd.DataFrame:
    secao("PASSO 7 — Tratamento de Outliers (IQR Capping)")
    cols_cap = ["nu_peso", "nu_altura", "nu_imc", "nu_imc_pre_gestacional",
                "ganho_imc", "log_taxa_sifilis_gest", "cnes_hospitais"]
    cols_cap = [c for c in cols_cap if c in df.columns]
    df, rel_out = aplicar_iqr_capping(df, cols_cap, fator=2.0)
    log("\n  Relatório de capping IQR:")
    log(rel_out.to_string(index=False))

    # Boxplot pós-capping
    cols_box = ["nu_peso", "nu_altura", "nu_imc", "nu_imc_pre_gestacional", "ganho_imc"]
    cols_box = [c for c in cols_box if c in df.columns]
    fig, axes = plt.subplots(1, len(cols_box), figsize=(3 * len(cols_box), 5))
    if len(cols_box) == 1:
        axes = [axes]
    for ax, col in zip(axes, cols_box):
        ax.boxplot(df[col].dropna(), patch_artist=True,
                   boxprops=dict(facecolor="mediumseagreen", alpha=0.7))
        ax.set_title(col, fontsize=9)
        ax.set_xticks([])
    plt.suptitle("Boxplots Pós-Capping (IQR × 2.0)", y=1.02)
    plt.tight_layout()
    salvar_fig("11_boxplots_pos_capping.png", fig)

    return df

# ── PASSO 8 — Análise de Variância ──────────────────────────────────────────────

def analisar_variancia(df: pd.DataFrame, cols: list[str]) -> list[str]:
    secao("PASSO 8 — Análise de Variância (seleção de features)")
    variancias = df[cols].var().sort_values()
    LIMIAR = 0.001

    log(f"\n  Variâncias por feature (limiar={LIMIAR}):")
    for col, v in variancias.items():
        flag = " ← REMOVIDA" if v < LIMIAR else ""
        log(f"    {col:<40} {v:.6f}{flag}")

    baixa_var = variancias[variancias < LIMIAR].index.tolist()
    cols_ok   = [c for c in cols if c not in baixa_var]

    fig, ax = plt.subplots(figsize=(10, max(4, len(variancias) * 0.3)))
    variancias.plot(kind="barh", ax=ax, color="steelblue", edgecolor="white")
    ax.axvline(LIMIAR, color="red", linestyle="--", label=f"Limiar ({LIMIAR})")
    ax.set_title("Variância por Feature")
    ax.legend()
    plt.tight_layout()
    salvar_fig("12_variancia_features.png", fig)

    if baixa_var:
        log(f"\n  Features removidas (baixa variância): {baixa_var}")
    else:
        log("  Nenhuma feature removida por baixa variância.")

    return cols_ok

# ── PASSO 9 — Codificação e Normalização ────────────────────────────────────────

def codificar_normalizar(df: pd.DataFrame) -> tuple[pd.DataFrame, RobustScaler, list[str]]:
    secao("PASSO 9 — Codificação e Normalização")

    # Features base para o modelo
    # CORREÇÃO 1: log_taxa_sifilis_gest no lugar de taxa_sifilis_gest (normalização robusta)
    # CORREÇÃO 2: taxa_mortalidade_materna removida do cluster (correlação 0.91 com sífilis)
    COLS_CONTINUAS = ["nu_imc", "nu_imc_pre_gestacional", "ganho_imc",
                      "nu_peso", "nu_altura",
                      "log_taxa_sifilis_gest", "cnes_hospitais"]
    COLS_ORDINAIS   = ["escolaridade"]
    COLS_NOMINAIS   = ["estado_nutricional_cod", "raca_cor"]
    COLS_FLAGS      = ["flag_anti_hiv", "tem_dado_sia"]

    # Filtrar para colunas disponíveis
    cols_cont = [c for c in COLS_CONTINUAS if c in df.columns]
    cols_ord  = [c for c in COLS_ORDINAIS  if c in df.columns]
    cols_nom  = [c for c in COLS_NOMINAIS  if c in df.columns]
    cols_flag = [c for c in COLS_FLAGS     if c in df.columns]

    df_model = df[cols_cont + cols_ord + cols_nom + cols_flag].copy()

    # Feature engenharia: log(1+consultas_prenatal) — reduz escala da contagem
    if "sia_consultas_prenatal" in df.columns:
        df_model["cobertura_prenatal_log"] = np.log1p(df["sia_consultas_prenatal"])
        cols_cont.append("cobertura_prenatal_log")

    # ── Ordinais como inteiro (hierarquia preservada)
    for col in cols_ord:
        df_model[col] = df_model[col].astype(float)

    # ── One-Hot Encoding para nominais
    ohe_cols = []
    for col in cols_nom:
        if col == "estado_nutricional_cod":
            map_ohe = {0: "est_nut_baixo_peso", 1: "est_nut_adequado",
                       2: "est_nut_sobrepeso",  3: "est_nut_obesidade",
                       4: "est_nut_obesidade",  5: "est_nut_obesidade"}
            df_model["_nut"] = df_model[col].map(map_ohe).fillna("est_nut_adequado")
            dummies = pd.get_dummies(df_model["_nut"], prefix="", prefix_sep="", dtype=int)
            for cat_col in ["est_nut_baixo_peso", "est_nut_adequado",
                             "est_nut_sobrepeso", "est_nut_obesidade"]:
                if cat_col not in dummies.columns:
                    dummies[cat_col] = 0
            df_model = pd.concat([df_model, dummies[["est_nut_baixo_peso","est_nut_adequado",
                                                       "est_nut_sobrepeso","est_nut_obesidade"]]], axis=1)
            df_model.drop(columns=[col, "_nut"], inplace=True)
            ohe_cols += ["est_nut_baixo_peso","est_nut_adequado","est_nut_sobrepeso","est_nut_obesidade"]

        elif col == "raca_cor":
            map_raca = {1: "raca_branca", 2: "raca_preta", 3: "raca_amarela",
                        4: "raca_parda",  5: "raca_indigena"}
            df_model["_raca"] = df_model[col].map(map_raca).fillna("raca_parda")
            dummies = pd.get_dummies(df_model["_raca"], prefix="", prefix_sep="", dtype=int)
            for cat_col in ["raca_branca","raca_preta","raca_amarela","raca_parda","raca_indigena"]:
                if cat_col not in dummies.columns:
                    dummies[cat_col] = 0
            df_model = pd.concat([df_model, dummies[["raca_branca","raca_preta","raca_amarela",
                                                       "raca_parda","raca_indigena"]]], axis=1)
            df_model.drop(columns=[col, "_raca"], inplace=True)
            ohe_cols += ["raca_branca","raca_preta","raca_amarela","raca_parda","raca_indigena"]

    # ── Selecionar features finais para normalização
    todas_cols = [c for c in (cols_cont + cols_ord + ohe_cols + cols_flag)
                  if c in df_model.columns]
    todas_cols = analisar_variancia(df_model, todas_cols)

    # ── RobustScaler em contínuas + ordinais (não nas OHE e flags)
    cols_para_escalar = [c for c in (cols_cont + cols_ord) if c in todas_cols]
    cols_bin = [c for c in (ohe_cols + cols_flag) if c in todas_cols]

    scaler = RobustScaler()
    arr_scaled = scaler.fit_transform(df_model[cols_para_escalar])
    df_scaled = pd.DataFrame(arr_scaled, columns=cols_para_escalar, index=df_model.index)

    # Reunir escalado + binárias
    df_final = pd.concat([df_scaled, df_model[cols_bin].reset_index(drop=True)], axis=1)

    log(f"\n  Shape final para cluster: {df_final.shape}")
    log(f"  Features escaladas: {cols_para_escalar}")
    log(f"  Features binárias: {cols_bin}")

    # Verificação pós-escala
    stats_pos = df_scaled.describe().loc[["50%"]]
    log(f"\n  Verificação pós-escala (mediana deve ser ~0):\n{stats_pos.round(3)}")

    # Gráfico: distribuição pós-normalização
    fig, axes = plt.subplots(
        2, max(1, (len(cols_para_escalar) + 1) // 2),
        figsize=(4 * max(1, (len(cols_para_escalar) + 1) // 2), 8)
    )
    axes = axes.flatten()
    for i, col in enumerate(cols_para_escalar):
        if i < len(axes):
            axes[i].hist(df_scaled[col].dropna(), bins=40,
                         color="teal", edgecolor="white", alpha=0.8)
            axes[i].set_title(f"{col}\n(escala RobustScaler)", fontsize=8)
    for j in range(len(cols_para_escalar), len(axes)):
        axes[j].set_visible(False)
    plt.suptitle("Distribuição das Features Após Normalização (RobustScaler)", y=1.01, fontsize=12)
    plt.tight_layout()
    salvar_fig("13_distribuicao_pos_normalizacao.png", fig)

    return df_final, scaler, todas_cols

# ── PASSO 10 — Exportação ───────────────────────────────────────────────────────

def exportar(
    conn,
    df_features: pd.DataFrame,
    df_scaled:   pd.DataFrame,
    df_mun:      pd.DataFrame,
    scaler:      RobustScaler,
) -> None:
    secao("PASSO 10 — Exportação")

    # ── Limpar tabelas destino (idempotente)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE ml_maternar.gestante_features RESTART IDENTITY;")
        cur.execute("TRUNCATE TABLE ml_maternar.gestante_para_cluster RESTART IDENTITY;")
        cur.execute("TRUNCATE TABLE ml_maternar.municipio_risco RESTART IDENTITY;")
    conn.commit()
    log("  Tabelas ml_maternar truncadas.")

    # ── municipio_risco
    cols_mun_pg = [
        "municipio", "ano",
        "sinan_sifilis_gest", "sinan_sifilis_cong", "sinan_toxo_gest",
        "sinan_dengue", "sinan_zika", "sinan_hepatite", "sinan_chik",
        "sim_obitos_maternos", "sim_hipertensivos", "sim_hemorragicos",
        "sia_consultas_prenatal", "sia_vdrl", "sia_anti_hiv", "sia_ultrassom",
        "sia_glicemia", "sia_toxo_exame",
        "cnes_hospitais",
        "taxa_sifilis_gest", "taxa_sifilis_cong", "taxa_toxo_gest",
        "taxa_mortalidade_materna", "log_taxa_sifilis_gest",
        "flag_vdrl", "flag_anti_hiv", "flag_ultrassom", "tem_dado_sia",
    ]
    cols_mun_pg = [c for c in cols_mun_pg if c in df_mun.columns]
    n = salvar_df_pg(conn, df_mun, "ml_maternar.municipio_risco", cols_mun_pg)
    log(f"  municipio_risco: {n:,} linhas inseridas")

    # ── gestante_features
    cols_feat_pg = [
        "sisvan_id", "ano", "municipio",
        "nu_peso", "nu_altura", "nu_imc", "nu_imc_pre_gestacional", "ganho_imc",
        "estado_nutricional_cod", "raca_cor", "escolaridade",
        "sinan_sifilis_gest", "sinan_toxo_gest", "sinan_dengue", "sinan_zika",
        "sim_obitos_maternos", "sia_consultas_prenatal",
        "taxa_sifilis_gest", "taxa_toxo_gest", "taxa_mortalidade_materna",
        "log_taxa_sifilis_gest",
        "flag_vdrl", "flag_anti_hiv", "flag_ultrassom",
        "tem_dado_sia", "cnes_hospitais",
    ]
    cols_feat_pg = [c for c in cols_feat_pg if c in df_features.columns]
    n = salvar_df_pg(conn, df_features, "ml_maternar.gestante_features", cols_feat_pg)
    log(f"  gestante_features: {n:,} linhas inseridas")

    # ── gestante_para_cluster
    df_cluster_pg = df_scaled.copy()
    df_cluster_pg.insert(0, "gestante_feature_id", range(1, len(df_cluster_pg) + 1))
    cols_cluster_pg = [c for c in [
        "gestante_feature_id",
        "nu_imc", "nu_imc_pre_gestacional", "ganho_imc", "nu_peso", "nu_altura",
        "escolaridade", "log_taxa_sifilis_gest", "cnes_hospitais",
        "cobertura_prenatal_log",
        "est_nut_baixo_peso", "est_nut_adequado", "est_nut_sobrepeso", "est_nut_obesidade",
        "raca_branca", "raca_preta", "raca_parda", "raca_amarela", "raca_indigena",
        "flag_anti_hiv", "tem_dado_sia",
    ] if c in df_cluster_pg.columns]
    n = salvar_df_pg(conn, df_cluster_pg, "ml_maternar.gestante_para_cluster", cols_cluster_pg)
    log(f"  gestante_para_cluster: {n:,} linhas inseridas")

    # ── Parquets locais
    df_features.to_parquet(OUTPUT_DIR / "gestante_features.parquet", index=False)
    df_scaled.to_parquet(OUTPUT_DIR / "gestante_para_cluster.parquet", index=False)
    log(f"  Parquets salvos em {OUTPUT_DIR}")

    # ── Scaler
    scaler_path = OUTPUT_DIR / "scaler_maternar.pkl"
    joblib.dump(scaler, scaler_path)
    log(f"  Scaler salvo: {scaler_path}")

# ── PASSO 11 — Relatório Markdown ───────────────────────────────────────────────

def gerar_relatorio(stats: dict, df_features: pd.DataFrame, df_scaled: pd.DataFrame,
                    df_mun: pd.DataFrame) -> None:
    secao("PASSO 11 — Gerando Relatório")

    n_municipios = df_mun["municipio"].nunique()
    n_anos = df_features["ano"].nunique()
    anos_range = f"{int(df_features['ano'].min())}–{int(df_features['ano'].max())}"

    nut_dist = stats.get("estado_nutricional", {})
    nut_total = sum(nut_dist.values()) or 1
    nut_linhas = "\n".join(
        f"| {k} | {v:,} | {v/nut_total*100:.1f}% |"
        for k, v in nut_dist.items()
    )

    nulos_linhas = "\n".join(
        f"| `{k}` | {v:.2f}% |"
        for k, v in stats.get("nulos", {}).items()
    ) or "| — | Sem valores ausentes |"

    ano_linhas = "\n".join(
        f"| {int(k)} | {v:,} |"
        for k, v in sorted(stats.get("por_ano", {}).items())
    )

    conteudo = textwrap.dedent(f"""
    # Relatório de Pré-Processamento — Maternar
    **Gerado em:** {TIMESTAMP}
    **Responsável:** Pipeline de ML — Projeto Maternar

    ---

    ## 1. Objetivo

    Pré-processar os dados dos 5 sistemas DATASUS do Projeto Maternar para alimentar
    o modelo K-Means de clusterização de perfis de risco gestacional. O foco é nas
    **mulheres grávidas e todos os fatores associados à gestação** que possam impactar
    o resultado clínico e o acompanhamento pré-natal.

    ---

    ## 2. Fontes de dados utilizadas

    | Sistema | Tabela PostgreSQL | Papel no modelo |
    |---------|-------------------|-----------------|
    | SISVAN | `datasus.sisvan_gestante` | Dados individuais — espinha do dataset |
    | SINAN  | `datasus.sinan_agravos_gestantes` | Taxas de agravos por município/ano |
    | SIM    | `datasus.sim_mortalidade_materna` | Taxa de mortalidade materna por município/ano |
    | SIA    | `datasus.sia_prenatal` | Cobertura pré-natal e exames por município/ano |
    | CNES   | `datasus.cnes_estabelecimentos` | Infraestrutura obstétrica por município/ano |

    ---

    ## 3. Estratégia de pré-processamento

    ### 3.1 Arquitetura do dataset

    ```
    SISVAN (individual) ← JOIN por (municipio_ibge 6-dígitos, ano) ← SINAN + SIM + SIA + CNES
    ```

    - **SISVAN** fornece os registros individuais (~1.2M gestantes)
    - **SINAN/SIM/SIA/CNES** são agregados a nível municipal via SQL (tabela `municipio_risco`)
    - O join enriquece cada gestante com o contexto de risco do seu município

    ### 3.2 Por que SQL para as agregações?

    SIA (32 GB) e SIM (30 GB) são grandes demais para carga completa em memória.
    Toda a sumarização foi feita diretamente no PostgreSQL, trazendo apenas os
    resultados agregados para Python.

    ---

    ## 4. Registros processados

    | Indicador | Valor |
    |-----------|-------|
    | Gestantes individuais (SISVAN) | {len(df_features):,} |
    | Municípios cobertos | {n_municipios:,} |
    | Anos cobertos | {anos_range} ({n_anos} anos) |
    | Features finais (para cluster) | {df_scaled.shape[1]} |
    | Municípios na tabela de risco | {n_municipios:,} |

    ---

    ## 5. Distribuição por ano

    | Ano | Gestantes |
    |-----|-----------|
    {ano_linhas}

    ---

    ## 6. Estado Nutricional das Gestantes

    | Categoria | Quantidade | % |
    |-----------|------------|---|
    {nut_linhas}

    ---

    ## 7. Valores ausentes (antes da imputação)

    | Feature | % ausente |
    |---------|-----------|
    {nulos_linhas}

    **Estratégia de imputação:**
    - Variáveis contínuas individuais (IMC, peso, altura): **mediana**
    - Variáveis ordinais (escolaridade, raça): **moda**
    - Taxas contextuais municipais: **mediana** (municípios sem dado recebem valor mediano)
    - Flags de cobertura (VDRL, HIV, ultrassom): **0** (ausência = sem cobertura)

    ---

    ## 8. Tratamento de Outliers — IQR Capping (fator 2.0)

    Valores extremos nas variáveis contínuas foram "cappados" pelo método IQR×2.0
    (Winsorization). Isso preserva todos os registros e neutraliza os extremos sem
    distorcer o cálculo de distância do K-Means.

    ---

    ## 9. Codificação de variáveis

    | Tipo | Variáveis | Tratamento |
    |------|-----------|------------|
    | Contínuas | IMC, peso, altura, taxas de risco | RobustScaler (mediana=0, IQR=1) |
    | Ordinal | Escolaridade | Inteiro preservando hierarquia |
    | Nominal — Estado nutricional | Baixo peso / Adequado / Sobrepeso / Obesidade | One-Hot Encoding (sem drop_first) |
    | Nominal — Raça/cor | Branca / Preta / Amarela / Parda / Indígena | One-Hot Encoding |
    | Binárias | flag_vdrl, flag_anti_hiv, flag_ultrassom | 0/1 sem escala |

    **Por que RobustScaler?**
    O K-Means é sensível à escala. O RobustScaler usa mediana e IQR em vez de
    média e desvio-padrão, sendo robusto a distribuições assimétricas e outliers
    residuais — características típicas de dados epidemiológicos brasileiros.

    **Por que OHE sem drop_first?**
    Em clustering não há problema de multicolinearidade. Remover uma categoria
    (como `drop_first=True`) esconderia um perfil inteiro do algoritmo.

    ---

    ## 10. Features finais para o K-Means

    ### Individuais (SISVAN)
    | Feature | Descrição |
    |---------|-----------|
    | `nu_imc` | IMC atual na aferição |
    | `nu_imc_pre_gestacional` | IMC pré-gestacional |
    | `ganho_imc` | Diferença IMC atual − pré-gestacional |
    | `nu_peso` | Peso em kg |
    | `nu_altura` | Altura em metros |
    | `escolaridade` | Escolaridade (1=Nenhuma…5=Superior) |
    | `est_nut_*` | OHE estado nutricional (4 flags) |
    | `raca_*` | OHE raça/cor (5 flags) |

    ### Contextuais municipais (SINAN + SIM + SIA + CNES)
    | Feature | Fonte | Descrição |
    |---------|-------|-----------|
    | `taxa_sifilis_gest` | SINAN | Casos SIFG / 1.000 consultas pré-natais |
    | `taxa_toxo_gest` | SINAN | Casos TOXG / 1.000 consultas |
    | `taxa_mortalidade_materna` | SIM | Óbitos maternos / 1.000 consultas |
    | `cobertura_prenatal_log` | SIA | log(1 + consultas pré-natais aprovadas) |
    | `cnes_leitos_obs` | CNES | Leitos obstétricos registrados |
    | `flag_vdrl` | SIA | 1 se VDRL foi ofertado no município/ano |
    | `flag_anti_hiv` | SIA | 1 se Anti-HIV foi ofertado |
    | `flag_ultrassom` | SIA | 1 se ultrassom obstétrico foi ofertado |

    ---

    ## 11. Tabelas criadas no PostgreSQL

    | Tabela | Descrição | Linhas |
    |--------|-----------|--------|
    | `ml_maternar.municipio_risco` | Indicadores de risco por município/ano | {n_municipios:,}+ |
    | `ml_maternar.gestante_features` | Dataset individual limpo (escala real) | {len(df_features):,} |
    | `ml_maternar.gestante_para_cluster` | Dataset encodado + normalizado (K-Means) | {len(df_scaled):,} |

    ---

    ## 12. Arquivos gerados

    | Arquivo | Descrição |
    |---------|-----------|
    | `preprocess_output/gestante_features.parquet` | Dataset individual — escala real |
    | `preprocess_output/gestante_para_cluster.parquet` | Dataset pronto para K-Means |
    | `preprocess_output/scaler_maternar.pkl` | RobustScaler serializado |
    | `preprocess_output/graficos/01_valores_ausentes.png` | Mapa de nulos |
    | `preprocess_output/graficos/02_distribuicao_imc.png` | Histogramas IMC |
    | `preprocess_output/graficos/03_estado_nutricional.png` | Estado nutricional |
    | `preprocess_output/graficos/04_raca_cor.png` | Raça/cor |
    | `preprocess_output/graficos/05_escolaridade.png` | Escolaridade |
    | `preprocess_output/graficos/06_distribuicao_ano.png` | Volume por ano |
    | `preprocess_output/graficos/07_correlacao.png` | Mapa de correlação |
    | `preprocess_output/graficos/08_boxplots_antes_capping.png` | Outliers pré-capping |
    | `preprocess_output/graficos/09_taxa_sifilis_por_ano.png` | Tendência sífilis |
    | `preprocess_output/graficos/10_cobertura_prenatal_ano.png` | Cobertura pré-natal |
    | `preprocess_output/graficos/11_boxplots_pos_capping.png` | Boxplots pós-capping |
    | `preprocess_output/graficos/12_variancia_features.png` | Variância por feature |
    | `preprocess_output/graficos/13_distribuicao_pos_normalizacao.png` | Distribuição pós-escala |

    ---

    ## 13. Próximo passo — Clustering K-Means

    ```python
    import pandas as pd, joblib
    from sklearn.cluster import KMeans

    df = pd.read_parquet("preprocess_output/gestante_para_cluster.parquet")
    scaler = joblib.load("preprocess_output/scaler_maternar.pkl")

    kmeans = KMeans(n_clusters=4, random_state=42, n_init=20)
    labels = kmeans.fit_predict(df)

    # Interpretar centroides na escala original
    centroides_raw = scaler.inverse_transform(kmeans.cluster_centers_[:, :len(scaler.center_)])
    ```

    ---
    *Gerado automaticamente por `preprocessing_maternar.py` — Projeto Maternar*
    """).strip()

    caminho = OUTPUT_DIR / "relatorio_preprocessamento.md"
    caminho.write_text(conteudo, encoding="utf-8")
    log(f"  Relatório salvo: {caminho}")

# ── Orquestrador Principal ───────────────────────────────────────────────────────

def main():
    secao("MATERNAR — Pré-Processamento Gestacional")
    log(f"Início: {TIMESTAMP}")

    conn = conectar()
    try:
        criar_schema_ml(conn)

        # 1. Dados individuais SISVAN
        df_sisvan = extrair_sisvan(conn)

        # 2. Agregações municipais (SQL)
        df_sinan = agregar_sinan(conn)
        df_sim   = agregar_sim(conn)
        df_sia   = agregar_sia(conn)
        df_cnes  = agregar_cnes(conn)

        # 3. Tabela de risco municipal
        df_mun = construir_municipio_risco(df_sinan, df_sim, df_sia, df_cnes)

        # 4. Dataset individual com contexto municipal
        df_features = construir_gestante_features(df_sisvan, df_mun)

        # 5. Análise exploratória
        stats = analise_exploratoria(df_features)

        # 6. Imputação
        df_features = tratar_ausentes(df_features)

        # 7. Outliers
        df_features = tratar_outliers(df_features)

        # 8–9. Codificação + normalização
        df_scaled, scaler, features_finais = codificar_normalizar(df_features)

        # 10. Exportação
        exportar(conn, df_features, df_scaled, df_mun, scaler)

        # 11. Relatório
        gerar_relatorio(stats, df_features, df_scaled, df_mun)

        secao("CONCLUÍDO")
        log(f"  Gestantes processadas:     {len(df_features):,}")
        log(f"  Features para K-Means:     {df_scaled.shape[1]}")
        log(f"  Municípios na base risco:  {df_mun['municipio'].nunique():,}")
        log(f"  Gráficos gerados:          {len(list(GRAFICOS.glob('*.png')))}")
        log(f"  Relatório:                 {OUTPUT_DIR}/relatorio_preprocessamento.md")
        log(f"  Tabelas PostgreSQL:        ml_maternar.{{gestante_features,gestante_para_cluster,municipio_risco}}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()

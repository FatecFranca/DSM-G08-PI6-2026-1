"""
================================================================================
  DATASUS → PostgreSQL — Carregador de Dados Gestacionais
================================================================================
  Lê os arquivos parquet baixados pelo main.py e carrega no banco PostgreSQL
  local no schema 'datasus'. Após carga bem-sucedida, cada parquet é excluído
  do disco e registrado no manifest (pipeline_manifest.json).

  Pré-requisitos:
    pip install psycopg2-binary pandas pyarrow numpy
    # Criar banco: createdb maternar  (ou conforme PGDATABASE)

  Variáveis de ambiente (ou edite DB_CONFIG diretamente):
    PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD

  Uso:
    python db_loader.py                          # carrega todos os sistemas
    python db_loader.py sinan sim cnes           # carrega sistemas específicos
    python db_loader.py --reset sinan            # trunca tabela antes de recarregar
    python db_loader.py --sync sinan sim cnes    # registra + exclui parquets já no banco
================================================================================
"""

import datetime
import json
import logging
import math
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import Json, execute_values

import manifest

warnings.filterwarnings("ignore")

# ── Configuração ───────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     os.getenv("PGHOST",     "127.0.0.1"),
    "port":     int(os.getenv("PGPORT", "5435")),
    "database": os.getenv("PGDATABASE", "maternar"),
    "user":     os.getenv("PGUSER",     "postgres"),
    "password": os.getenv("PGPASSWORD", ""),
}

BASE_PATH  = Path(__file__).parent / "dados_datasus"
BATCH_SIZE = 5_000

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)

# ── DDL ────────────────────────────────────────────────────────────────────────

DDL = """
CREATE SCHEMA IF NOT EXISTS datasus;

-- SINAN: Agravos em Gestantes (sífilis, toxoplasmose, dengue, zika, etc.)
CREATE TABLE IF NOT EXISTS datasus.sinan_agravos_gestantes (
    id              BIGSERIAL    PRIMARY KEY,
    agravo          VARCHAR(4)   NOT NULL,
    ano             SMALLINT     NOT NULL,
    dt_notific      VARCHAR(8),
    sg_uf_not       VARCHAR(2),
    id_municip      VARCHAR(6),
    dt_nasc         VARCHAR(8),
    cs_sexo         VARCHAR(1),
    cs_gestant      SMALLINT,
    cs_raca         SMALLINT,
    cs_escol_n      SMALLINT,
    sg_uf           VARCHAR(2),
    id_mn_resi      VARCHAR(6),
    dado_raw        JSONB,
    inserted_at     TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sinan_agravo_ano ON datasus.sinan_agravos_gestantes(agravo, ano);
CREATE INDEX IF NOT EXISTS idx_sinan_municipio  ON datasus.sinan_agravos_gestantes(id_municip);
CREATE INDEX IF NOT EXISTS idx_sinan_gestant    ON datasus.sinan_agravos_gestantes(cs_gestant);
CREATE INDEX IF NOT EXISTS idx_sinan_uf         ON datasus.sinan_agravos_gestantes(sg_uf_not);

-- SIM: Óbitos Maternos (CID-10 O00-O99)
CREATE TABLE IF NOT EXISTS datasus.sim_mortalidade_materna (
    id              BIGSERIAL    PRIMARY KEY,
    estado          CHAR(2)      NOT NULL,
    ano             SMALLINT     NOT NULL,
    causabas        VARCHAR(10),
    causabas_o      VARCHAR(10),
    obitograv       SMALLINT,
    obitopuerp      SMALLINT,
    dtobito         VARCHAR(8),
    dtnasc          VARCHAR(8),
    sexo            SMALLINT,
    racacor         SMALLINT,
    esc             SMALLINT,
    esc2010         SMALLINT,
    codmunres       VARCHAR(6),
    codmunocor      VARCHAR(6),
    gestacao        SMALLINT,
    semanagest      VARCHAR(10),
    tpmorteoco      SMALLINT,
    dado_raw        JSONB,
    inserted_at     TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sim_uf_ano       ON datasus.sim_mortalidade_materna(estado, ano);
CREATE INDEX IF NOT EXISTS idx_sim_causabas     ON datasus.sim_mortalidade_materna(causabas);
CREATE INDEX IF NOT EXISTS idx_sim_munres       ON datasus.sim_mortalidade_materna(codmunres);

-- CNES: Estabelecimentos de Saúde (cobertura pré-natal por município)
CREATE TABLE IF NOT EXISTS datasus.cnes_estabelecimentos (
    id              BIGSERIAL    PRIMARY KEY,
    estado          CHAR(2)      NOT NULL,
    ano             SMALLINT     NOT NULL,
    mes             SMALLINT     NOT NULL,
    grupo           VARCHAR(2)   NOT NULL,
    codmunicipio    VARCHAR(6),
    cnes            VARCHAR(7),
    tp_unidade      VARCHAR(2),
    qt_leito_obs    INTEGER,
    co_latitude     DECIMAL(10,6),
    co_longitude    DECIMAL(10,6),
    dado_raw        JSONB,
    inserted_at     TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cnes_uf_ano      ON datasus.cnes_estabelecimentos(estado, ano, mes);
CREATE INDEX IF NOT EXISTS idx_cnes_municipio   ON datasus.cnes_estabelecimentos(codmunicipio);
CREATE INDEX IF NOT EXISTS idx_cnes_tp_unidade  ON datasus.cnes_estabelecimentos(tp_unidade);

-- SIA: Produção Pré-Natal (proxy SISPreNatal — procedimentos SIGTAP)
CREATE TABLE IF NOT EXISTS datasus.sia_prenatal (
    id              BIGSERIAL    PRIMARY KEY,
    estado          CHAR(2)      NOT NULL,
    ano             SMALLINT     NOT NULL,
    mes             SMALLINT     NOT NULL,
    pa_cmp          VARCHAR(6),
    pa_coduni       VARCHAR(7),
    pa_munpcn       VARCHAR(6),
    pa_proc_id      VARCHAR(10),
    pa_sexo         VARCHAR(1),
    pa_idade        SMALLINT,
    pa_racacor      VARCHAR(2),
    pa_qtdpro       INTEGER,
    pa_qtdapr       INTEGER,
    dado_raw        JSONB,
    inserted_at     TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sia_uf_ano       ON datasus.sia_prenatal(estado, ano, mes);
CREATE INDEX IF NOT EXISTS idx_sia_municipio    ON datasus.sia_prenatal(pa_munpcn);
CREATE INDEX IF NOT EXISTS idx_sia_proc         ON datasus.sia_prenatal(pa_proc_id);

-- SISVAN: Estado Nutricional de Gestantes
CREATE TABLE IF NOT EXISTS datasus.sisvan_gestante (
    id                      BIGSERIAL    PRIMARY KEY,
    ano                     SMALLINT     NOT NULL,
    nu_cns                  VARCHAR(15),
    co_municipio_ibge       VARCHAR(7),
    nu_competencia_aaaamm   VARCHAR(6),
    nu_semana_gestacional   SMALLINT,
    nu_peso                 DECIMAL(6,2),
    nu_altura               DECIMAL(5,2),
    nu_imc                  DECIMAL(6,2),
    ds_st_nutricional       VARCHAR(50),
    nu_imc_pre_gestacional  DECIMAL(6,2),
    ds_acompanhamento       VARCHAR(50),
    co_raca_cor             SMALLINT,
    nu_escolaridade         SMALLINT,
    dado_raw                JSONB,
    inserted_at             TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sisvan_ano        ON datasus.sisvan_gestante(ano);
CREATE INDEX IF NOT EXISTS idx_sisvan_municipio  ON datasus.sisvan_gestante(co_municipio_ibge);
CREATE INDEX IF NOT EXISTS idx_sisvan_semana     ON datasus.sisvan_gestante(nu_semana_gestacional);
"""

# ── Utilitários ────────────────────────────────────────────────────────────────

def clean_val(v):
    """Normaliza tipos numpy/NaN/inf para valores Python puros."""
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, (pd.Timestamp, np.datetime64)):
        try:
            return pd.Timestamp(v).isoformat()
        except Exception:
            return None
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if hasattr(v, "item"):
        return v.item()
    return v


def _safe_int(series: pd.Series) -> list:
    result = []
    for v in pd.to_numeric(series, errors="coerce"):
        try:
            if pd.isna(v):
                result.append(None)
            else:
                result.append(int(v))
        except (TypeError, ValueError):
            result.append(None)
    return result


def _safe_str(series: pd.Series, max_len: int = None) -> list:
    def _clean(v):
        if v is None:
            return None
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(v, (datetime.date, datetime.datetime)):
            s = v.strftime("%Y%m%d")
        else:
            s = str(v).strip()
        if s in ("nan", "None", "NaT", ""):
            return None
        return s[:max_len] if max_len else s

    return series.apply(_clean).tolist()


def _safe_float(series: pd.Series) -> list:
    result = []
    for v in pd.to_numeric(series, errors="coerce"):
        try:
            if pd.isna(v):
                result.append(None)
            else:
                result.append(float(v))
        except (TypeError, ValueError):
            result.append(None)
    return result


def _dado_raw(df: pd.DataFrame) -> list:
    """Serializa cada linha como JSONB (Json adapter do psycopg2)."""
    upper_cols = [c.upper() for c in df.columns]
    rows_as_dicts = [
        {upper_cols[i]: clean_val(row[i]) for i in range(len(upper_cols))}
        for row in df.itertuples(index=False, name=None)
    ]
    return [Json(d) for d in rows_as_dicts]


def _col(df: pd.DataFrame, *nomes: str) -> pd.Series:
    """Retorna a coluna (case-insensitive) ou série de None."""
    mapa = {c.upper(): c for c in df.columns}
    for nome in nomes:
        encontrado = mapa.get(nome.upper())
        if encontrado:
            return df[encontrado]
    return pd.Series([None] * len(df), index=df.index)


# ── Conexão e Schema ───────────────────────────────────────────────────────────

def conectar() -> psycopg2.extensions.connection:
    log.info(
        f"Conectando: {DB_CONFIG['host']}:{DB_CONFIG['port']}"
        f"/{DB_CONFIG['database']} (user={DB_CONFIG['user']})"
    )
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        log.info("  ✓ Conexão estabelecida")
        return conn
    except psycopg2.OperationalError as exc:
        log.error(f"  ✗ Falha: {exc}")
        log.error(
            "  Configure: PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD\n"
            "  Crie o banco com: createdb maternar"
        )
        raise


def criar_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()
    log.info("  ✓ Schema 'datasus' e tabelas verificadas/criadas")


def truncar_tabela(conn, tabela: str, prefixo_manifest: str = None) -> None:
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {tabela} RESTART IDENTITY CASCADE")
    conn.commit()
    log.info(f"  ✓ Tabela {tabela} truncada")
    if prefixo_manifest:
        manifest.limpar_carga_prefixo(prefixo_manifest)
        log.info(f"  ✓ Manifest: 'loaded' limpo para '{prefixo_manifest}*'")


# ── Inserção em Lote ───────────────────────────────────────────────────────────

def _inserir(conn, tabela: str, colunas: list[str], linhas: list[tuple]) -> int:
    if not linhas:
        return 0
    query = f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES %s"
    with conn.cursor() as cur:
        execute_values(cur, query, linhas, page_size=BATCH_SIZE)
    conn.commit()
    return len(linhas)


# ── Carregadores por Sistema ───────────────────────────────────────────────────

def carregar_sinan(conn, reset: bool = False) -> None:
    pasta = BASE_PATH / "SINAN"
    if not pasta.exists():
        log.warning("SINAN: diretório não encontrado, pulando")
        return

    tabela = "datasus.sinan_agravos_gestantes"
    log.info(f"\n{'=' * 55}\nSINAN → {tabela}\n{'=' * 55}")

    if reset:
        truncar_tabela(conn, tabela, "SINAN/")

    colunas = [
        "agravo", "ano",
        "dt_notific", "sg_uf_not", "id_municip",
        "dt_nasc", "cs_sexo", "cs_gestant",
        "cs_raca", "cs_escol_n", "sg_uf", "id_mn_resi",
        "dado_raw",
    ]

    import pyarrow.parquet as pq

    total_geral = 0
    for arq in sorted(pasta.glob("SINAN_*.parquet")):
        partes = arq.stem.split("_")
        if len(partes) < 3:
            continue
        if not reset and manifest.ja_foi_carregado(arq):
            log.info(f"  → skip (já carregado): {arq.name}")
            continue
        agravo, ano = partes[1], int(partes[2])
        log.info(f"  {arq.name} [{agravo}/{ano}]...")

        total_arq = 0
        try:
            for batch in pq.ParquetFile(arq).iter_batches(batch_size=BATCH_SIZE):
                df = batch.to_pandas()
                linhas = list(zip(
                    [agravo] * len(df), [ano] * len(df),
                    _safe_str(_col(df, "DT_NOTIFIC"), 8),
                    _safe_str(_col(df, "SG_UF_NOT"), 2),
                    _safe_str(_col(df, "ID_MUNICIP"), 6),
                    _safe_str(_col(df, "DT_NASC"), 8),
                    _safe_str(_col(df, "CS_SEXO"), 1),
                    _safe_int(_col(df, "CS_GESTANT")),
                    _safe_int(_col(df, "CS_RACA")),
                    _safe_int(_col(df, "CS_ESCOL_N")),
                    _safe_str(_col(df, "SG_UF"), 2),
                    _safe_str(_col(df, "ID_MN_RESI"), 6),
                    _dado_raw(df),
                ))
                total_arq += _inserir(conn, tabela, colunas, linhas)
            arq.unlink(missing_ok=True)
            manifest.registrar_carga(arq)
            log.info(f"    ✓ {total_arq:,} registros | parquet excluído")
        except Exception as exc:
            log.error(f"  ✗ erro ao carregar {arq.name}: {exc}")
        total_geral += total_arq

    log.info(f"\n  SINAN total: {total_geral:,} registros")


def carregar_sim(conn, reset: bool = False) -> None:
    pasta = BASE_PATH / "SIM"
    if not pasta.exists():
        log.warning("SIM: diretório não encontrado, pulando")
        return

    tabela = "datasus.sim_mortalidade_materna"
    log.info(f"\n{'=' * 55}\nSIM → {tabela}\n{'=' * 55}")

    if reset:
        truncar_tabela(conn, tabela, "SIM/")

    colunas = [
        "estado", "ano",
        "causabas", "causabas_o", "obitograv", "obitopuerp",
        "dtobito", "dtnasc", "sexo", "racacor", "esc", "esc2010",
        "codmunres", "codmunocor", "gestacao", "semanagest", "tpmorteoco",
        "dado_raw",
    ]

    import pyarrow.parquet as pq

    total_geral = 0
    for arq in sorted(pasta.glob("SIM_MATERNO_*.parquet")):
        partes = arq.stem.split("_")
        if len(partes) < 4:
            continue
        if not reset and manifest.ja_foi_carregado(arq):
            log.info(f"  → skip (já carregado): {arq.name}")
            continue
        estado, ano = partes[2], int(partes[3])
        log.info(f"  {arq.name} [{estado}/{ano}]...")

        total_arq = 0
        try:
            for batch in pq.ParquetFile(arq).iter_batches(batch_size=BATCH_SIZE):
                df = batch.to_pandas()
                linhas = list(zip(
                    [estado] * len(df), [ano] * len(df),
                    _safe_str(_col(df, "CAUSABAS"), 10),
                    _safe_str(_col(df, "CAUSABAS_O"), 10),
                    _safe_int(_col(df, "OBITOGRAV", "OBITOGRAVID")),
                    _safe_int(_col(df, "OBITOPUERP")),
                    _safe_str(_col(df, "DTOBITO"), 8),
                    _safe_str(_col(df, "DTNASC"), 8),
                    _safe_int(_col(df, "SEXO")),
                    _safe_int(_col(df, "RACACOR")),
                    _safe_int(_col(df, "ESC")),
                    _safe_int(_col(df, "ESC2010")),
                    _safe_str(_col(df, "CODMUNRES"), 6),
                    _safe_str(_col(df, "CODMUNOCOR"), 6),
                    _safe_int(_col(df, "GESTACAO")),
                    _safe_str(_col(df, "SEMANAGEST"), 10),
                    _safe_int(_col(df, "TPMORTEOCO")),
                    _dado_raw(df),
                ))
                total_arq += _inserir(conn, tabela, colunas, linhas)
            arq.unlink(missing_ok=True)
            manifest.registrar_carga(arq)
            log.info(f"    ✓ {total_arq:,} registros | parquet excluído")
        except Exception as exc:
            log.error(f"  ✗ erro ao carregar {arq.name}: {exc}")
        total_geral += total_arq

    log.info(f"\n  SIM total: {total_geral:,} registros")


def carregar_cnes(conn, reset: bool = False) -> None:
    pasta = BASE_PATH / "CNES"
    if not pasta.exists():
        log.warning("CNES: diretório não encontrado, pulando")
        return

    tabela = "datasus.cnes_estabelecimentos"
    log.info(f"\n{'=' * 55}\nCNES → {tabela}\n{'=' * 55}")

    if reset:
        truncar_tabela(conn, tabela, "CNES/")

    colunas = [
        "estado", "ano", "mes", "grupo",
        "codmunicipio", "cnes", "tp_unidade",
        "qt_leito_obs", "co_latitude", "co_longitude",
        "dado_raw",
    ]

    import pyarrow.parquet as pq

    total_geral = 0
    for arq in sorted(pasta.glob("CNES_*.parquet")):
        partes = arq.stem.split("_")
        if len(partes) < 5:
            continue
        if not reset and manifest.ja_foi_carregado(arq):
            log.info(f"  → skip (já carregado): {arq.name}")
            continue
        grupo, estado, ano, mes = partes[1], partes[2], int(partes[3]), int(partes[4])
        log.info(f"  {arq.name} [{grupo}/{estado}/{ano}-{mes:02d}]...")

        total_arq = 0
        try:
            for batch in pq.ParquetFile(arq).iter_batches(batch_size=BATCH_SIZE):
                df = batch.to_pandas()
                linhas = list(zip(
                    [estado] * len(df), [ano] * len(df), [mes] * len(df), [grupo] * len(df),
                    _safe_str(_col(df, "CODMUNICIPIO", "CO_MUNICIP", "CODMUNIC"), 6),
                    _safe_str(_col(df, "CNES", "CO_CNES"), 7),
                    _safe_str(_col(df, "TP_UNIDADE", "TPUNIDADE"), 2),
                    _safe_int(_col(df, "QT_LEITO_OBS")),
                    _safe_float(_col(df, "CO_LATITUDE", "LATITUDE")),
                    _safe_float(_col(df, "CO_LONGITUDE", "LONGITUDE")),
                    _dado_raw(df),
                ))
                total_arq += _inserir(conn, tabela, colunas, linhas)
            arq.unlink(missing_ok=True)
            manifest.registrar_carga(arq)
            log.info(f"    ✓ {total_arq:,} registros | parquet excluído")
        except Exception as exc:
            log.error(f"  ✗ erro ao carregar {arq.name}: {exc}")
        total_geral += total_arq

    log.info(f"\n  CNES total: {total_geral:,} registros")


def carregar_sia(conn, reset: bool = False) -> None:
    pasta = BASE_PATH / "SIA_PRENATAL"
    if not pasta.exists():
        log.warning("SIA_PRENATAL: diretório não encontrado, pulando")
        return

    tabela = "datasus.sia_prenatal"
    log.info(f"\n{'=' * 55}\nSIA → {tabela}\n{'=' * 55}")

    if reset:
        truncar_tabela(conn, tabela, "SIA_PRENATAL/")

    colunas = [
        "estado", "ano", "mes",
        "pa_cmp", "pa_coduni", "pa_munpcn", "pa_proc_id",
        "pa_sexo", "pa_idade", "pa_racacor", "pa_qtdpro", "pa_qtdapr",
        "dado_raw",
    ]

    import pyarrow.parquet as pq

    total_geral = 0
    for arq in sorted(pasta.glob("SIA_PRENATAL_*.parquet")):
        partes = arq.stem.split("_")
        if len(partes) < 5:
            continue
        if not reset and manifest.ja_foi_carregado(arq):
            log.info(f"  → skip (já carregado): {arq.name}")
            continue
        estado, ano, mes = partes[2], int(partes[3]), int(partes[4])
        log.info(f"  {arq.name} [{estado}/{ano}-{mes:02d}]...")

        total_arq = 0
        try:
            for batch in pq.ParquetFile(arq).iter_batches(batch_size=BATCH_SIZE):
                df = batch.to_pandas()
                linhas = list(zip(
                    [estado] * len(df), [ano] * len(df), [mes] * len(df),
                    _safe_str(_col(df, "PA_CMP"), 6),
                    _safe_str(_col(df, "PA_CODUNI"), 7),
                    _safe_str(_col(df, "PA_MUNPCN"), 6),
                    _safe_str(_col(df, "PA_PROC_ID"), 10),
                    _safe_str(_col(df, "PA_SEXO"), 1),
                    _safe_int(_col(df, "PA_IDADE")),
                    _safe_str(_col(df, "PA_RACACOR"), 2),
                    _safe_int(_col(df, "PA_QTDPRO")),
                    _safe_int(_col(df, "PA_QTDAPR")),
                    _dado_raw(df),
                ))
                total_arq += _inserir(conn, tabela, colunas, linhas)
            arq.unlink(missing_ok=True)
            manifest.registrar_carga(arq)
            log.info(f"    ✓ {total_arq:,} registros | parquet excluído")
        except Exception as exc:
            log.error(f"  ✗ erro ao carregar {arq.name}: {exc}")
        total_geral += total_arq

    log.info(f"\n  SIA total: {total_geral:,} registros")


def _normalizar_decimal(df: pd.DataFrame, *colunas: str) -> None:
    """Substitui vírgula por ponto nos campos numéricos do SISVAN (padrão IBGE)."""
    for col in colunas:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(",", ".", regex=False)


def carregar_sisvan(conn, reset: bool = False) -> None:
    pasta = BASE_PATH / "SISVAN"
    if not pasta.exists():
        log.warning("SISVAN: diretório não encontrado, pulando")
        return

    tabela = "datasus.sisvan_gestante"
    log.info(f"\n{'=' * 55}\nSISVAN → {tabela}\n{'=' * 55}")

    if reset:
        truncar_tabela(conn, tabela, "SISVAN/")

    colunas = [
        "ano",
        "nu_cns", "co_municipio_ibge", "nu_competencia_aaaamm",
        "nu_semana_gestacional",
        "nu_peso", "nu_altura", "nu_imc",
        "ds_st_nutricional", "nu_imc_pre_gestacional",
        "ds_acompanhamento", "co_raca_cor", "nu_escolaridade",
        "dado_raw",
    ]

    total_geral = 0

    # ── Parquets (formato pysus: sisvan_gestante_AAAA.parquet) ─────────────────
    import pyarrow.parquet as pq

    for arq in sorted(pasta.glob("sisvan_gestante_*.parquet")):
        partes = arq.stem.split("_")
        if len(partes) < 3:
            continue
        if not reset and manifest.ja_foi_carregado(arq):
            log.info(f"  → skip (já carregado): {arq.name}")
            continue
        ano = int(partes[-1])
        log.info(f"  {arq.name} [{ano}] (parquet)...")

        total_arq = 0
        try:
            for batch in pq.ParquetFile(arq).iter_batches(batch_size=BATCH_SIZE):
                df = batch.to_pandas()
                linhas = list(zip(
                    [ano] * len(df),
                    _safe_str(_col(df, "nu_cns", "NU_CNS"), 15),
                    _safe_str(_col(df, "co_municipio_ibge", "CO_MUNICIPIO_IBGE"), 7),
                    _safe_str(_col(df, "nu_competencia_aaaamm", "NU_COMPETENCIA_AAAAMM"), 6),
                    _safe_int(_col(df, "nu_semana_gestacional", "NU_SEMANA_GESTACIONAL")),
                    _safe_float(_col(df, "nu_peso", "NU_PESO")),
                    _safe_float(_col(df, "nu_altura", "NU_ALTURA")),
                    _safe_float(_col(df, "nu_imc", "NU_IMC")),
                    _safe_str(_col(df, "ds_st_nutricional", "DS_ST_NUTRICIONAL"), 50),
                    _safe_float(_col(df, "nu_imc_pre_gestacional", "NU_IMC_PRE_GESTACIONAL")),
                    _safe_str(_col(df, "ds_acompanhamento", "DS_ACOMPANHAMENTO"), 50),
                    _safe_int(_col(df, "co_raca_cor", "CO_RACA_COR")),
                    _safe_int(_col(df, "nu_escolaridade", "NU_ESCOLARIDADE")),
                    _dado_raw(df),
                ))
                total_arq += _inserir(conn, tabela, colunas, linhas)
            arq.unlink(missing_ok=True)
            manifest.registrar_carga(arq)
            log.info(f"    ✓ {total_arq:,} registros | parquet excluído")
        except Exception as exc:
            log.error(f"  ✗ erro ao carregar {arq.name}: {exc}")
        total_geral += total_arq

    # ── CSVs OpenDataSUS (sisvan_estado_nutricional_AAAA.csv) ─────────────────
    # ZIPs são ignorados — devem ser tratados em etapa separada.
    #
    # Filtro gestantes: DS_IMC_PRE_GESTACIONAL preenchido e != "0".
    # Encoding: latin-1.  Decimal: vírgula → ponto antes de converter.
    # Chunks de 100 k linhas para caber na RAM com arquivos de até 9 GB.

    for arq in sorted(pasta.glob("sisvan_estado_nutricional_*.csv")):
        try:
            ano = int(arq.stem.rsplit("_", 1)[-1])
        except ValueError:
            log.warning(f"  Não foi possível extrair ano de: {arq.name}")
            continue

        if not reset and manifest.ja_foi_carregado(arq):
            log.info(f"  → skip (já carregado): {arq.name}")
            continue

        tamanho_gb = arq.stat().st_size / 1_073_741_824
        log.info(f"  {arq.name} [{ano}] ({tamanho_gb:.1f} GB)...")

        total_arq = 0
        try:
            leitor = pd.read_csv(
                arq,
                sep=";",
                encoding="latin-1",
                dtype=str,
                chunksize=100_000,
                low_memory=False,
            )
            for chunk in leitor:
                # Identifica coluna de IMC pré-gestacional (case-insensitive)
                col_gest = next(
                    (c for c in chunk.columns if "IMC_PRE_GESTACIONAL" in c.upper()),
                    None,
                )
                if col_gest is None:
                    df = chunk.copy()
                else:
                    imc = chunk[col_gest].fillna("").str.strip()
                    df = chunk[(imc != "") & (imc != "0")].copy()

                if df.empty:
                    continue

                # Normaliza decimais com vírgula antes de converter para float
                _normalizar_decimal(df, "NU_PESO", "NU_ALTURA", "DS_IMC",
                                    col_gest or "DS_IMC_PRE_GESTACIONAL")

                linhas = list(zip(
                    [ano]  * len(df),
                    [None] * len(df),   # nu_cns — ausente no formato CSV
                    _safe_str(_col(df, "CO_MUNICIPIO_IBGE"), 7),
                    _safe_str(_col(df, "NU_COMPETENCIA"), 6),
                    [None] * len(df),   # nu_semana_gestacional — ausente no formato CSV
                    _safe_float(_col(df, "NU_PESO")),
                    _safe_float(_col(df, "NU_ALTURA")),
                    _safe_float(_col(df, "DS_IMC")),
                    # Estado nutricional: tenta adulto primeiro, cai no sem-gestacional
                    _safe_str(_col(df, "CO_ESTADO_NUTRI_ADULTO", "CO_ESTADO_NUTRI_IMC_SEMGEST"), 50),
                    _safe_float(_col(df, col_gest or "DS_IMC_PRE_GESTACIONAL")),
                    _safe_str(_col(df, "DT_ACOMPANHAMENTO"), 50),
                    _safe_int(_col(df, "CO_RACA_COR")),
                    _safe_int(_col(df, "CO_ESCOLARIDADE")),
                    _dado_raw(df),
                ))
                total_arq += _inserir(conn, tabela, colunas, linhas)

            arq.unlink(missing_ok=True)
            manifest.registrar_carga(arq)
            log.info(f"    ✓ {total_arq:,} gestantes carregadas | CSV excluído")
        except Exception as exc:
            log.error(f"  ✗ erro ao carregar {arq.name}: {exc}")
        total_geral += total_arq

    log.info(f"\n  SISVAN total: {total_geral:,} registros")


# ── Relatório Final ────────────────────────────────────────────────────────────

def relatorio(conn) -> None:
    log.info(f"\n{'=' * 55}\nRELATÓRIO DE CARGA\n{'=' * 55}")
    tabelas = [
        ("datasus.sinan_agravos_gestantes", "SINAN"),
        ("datasus.sim_mortalidade_materna", "SIM"),
        ("datasus.cnes_estabelecimentos",   "CNES"),
        ("datasus.sia_prenatal",            "SIA Pré-Natal"),
        ("datasus.sisvan_gestante",         "SISVAN"),
    ]
    total = 0
    with conn.cursor() as cur:
        print(f"\n{'Sistema':<20} {'Registros':>15}")
        print("-" * 37)
        for tabela, nome in tabelas:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {tabela}")
                n = cur.fetchone()[0]
            except Exception:
                n = 0
            print(f"{nome:<20} {n:>15,}")
            total += n
        print("-" * 37)
        print(f"{'TOTAL':<20} {total:>15,}")


# ── Sincronização (para dados já no banco, sem parquets) ──────────────────────

# Mapeamento sistema → (subdiretório, padrão glob)
_SISTEMA_PASTA = {
    "sinan":  ("SINAN",       "SINAN_*.parquet"),
    "sim":    ("SIM",         "SIM_MATERNO_*.parquet"),
    "cnes":   ("CNES",        "CNES_*.parquet"),
    "sia":    ("SIA_PRENATAL","SIA_PRENATAL_*.parquet"),
    "sisvan": ("SISVAN",      "sisvan_gestante_*.parquet"),
}


def sincronizar(sistemas_alvo: list) -> None:
    """Registra no manifest e exclui parquets de sistemas já carregados no banco."""
    log.info(f"\n{'=' * 55}\nSINCRONIZAR MANIFEST (registrar + excluir)\n{'=' * 55}")
    total_removidos = 0
    for nome in sistemas_alvo:
        if nome not in _SISTEMA_PASTA:
            log.warning(f"  Sistema desconhecido: {nome}")
            continue
        subdir, glob_pat = _SISTEMA_PASTA[nome]
        pasta = BASE_PATH / subdir
        if not pasta.exists():
            log.info(f"  {nome.upper()}: diretório não existe, pulando")
            continue
        arquivos = sorted(pasta.glob(glob_pat))
        log.info(f"\n  {nome.upper()}: {len(arquivos)} parquets encontrados")
        for arq in arquivos:
            manifest.registrar_carga(arq)
            arq.unlink(missing_ok=True)
            log.info(f"    ✓ excluído: {arq.name}")
            total_removidos += 1
    log.info(f"\n  Sync concluído: {total_removidos} arquivos removidos do disco")


# ── Orquestração ───────────────────────────────────────────────────────────────

SISTEMAS = {
    "sinan":  carregar_sinan,
    "sim":    carregar_sim,
    "cnes":   carregar_cnes,
    "sia":    carregar_sia,
    "sisvan": carregar_sisvan,
}


def main():
    args = [a.lower() for a in sys.argv[1:]]
    reset = "--reset" in args
    sync  = "--sync"  in args
    if reset:
        args.remove("--reset")
    if sync:
        args.remove("--sync")

    sistemas_alvo = [s for s in args if s in SISTEMAS] if args else list(SISTEMAS.keys())

    if args and not sistemas_alvo:
        log.error(f"Sistemas desconhecidos: {args}. Disponíveis: {list(SISTEMAS.keys())}")
        sys.exit(1)

    if sync:
        sincronizar(sistemas_alvo)
        return

    conn = conectar()
    try:
        criar_schema(conn)
        for nome in sistemas_alvo:
            SISTEMAS[nome](conn, reset=reset)
        relatorio(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

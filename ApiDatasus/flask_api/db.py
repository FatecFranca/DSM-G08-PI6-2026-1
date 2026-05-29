"""
Acesso ao PostgreSQL para busca de features municipais em tempo real.

A tabela `ml_maternar.municipio_features` é populada pelo pipeline de
pré-processamento (preprocessing_maternar.py) e contém indicadores
epidemiológicos agregados por município/ano usados como features do modelo.
"""

import logging
import psycopg2
import psycopg2.pool
from config import PG_DSN

log = logging.getLogger(__name__)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None

MUNICIPIO_DEFAULTS = {
    "log_taxa_sifilis_gest":  0.0,
    "cnes_hospitais":         2.0,
    "cobertura_prenatal_log": 0.0,
    "tem_dado_sia":           False,
}


def init_pool(minconn: int = 1, maxconn: int = 10) -> None:
    global _pool
    _pool = psycopg2.pool.ThreadedConnectionPool(minconn, maxconn, dsn=PG_DSN)
    log.info("Pool PostgreSQL iniciado (min=%d, max=%d)", minconn, maxconn)


def get_municipio_features(cod_municipio: str) -> dict:
    """
    Busca as features municipais necessárias para inferência.

    Parâmetros
    ----------
    cod_municipio : str
        Código IBGE do município — 6 ou 7 dígitos (ex: "350950" ou "3509502").

    Retorno
    -------
    dict com as chaves:
        log_taxa_sifilis_gest  : float  — log1p(taxa de sífilis gestacional)
        cnes_hospitais         : float  — nº de hospitais no município
        cobertura_prenatal_log : float  — log1p(consultas pré-natal por habitante)
        tem_dado_sia           : bool   — se há dados SIA para o município
    """
    if _pool is None:
        log.warning("Pool não inicializado — usando defaults municipais")
        return MUNICIPIO_DEFAULTS.copy()

    # Normaliza: aceita 6 ou 7 dígitos
    cod = str(cod_municipio).strip()[:6]

    conn = _pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    log_taxa_sifilis_gest,
                    cnes_hospitais,
                    cobertura_prenatal_log,
                    tem_dado_sia
                FROM ml_maternar.municipio_features
                WHERE cod_municipio = %s
                ORDER BY ano DESC
                LIMIT 1
                """,
                (cod,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "log_taxa_sifilis_gest":  float(row[0] or 0.0),
                    "cnes_hospitais":         float(row[1] or 2.0),
                    "cobertura_prenatal_log": float(row[2] or 0.0),
                    "tem_dado_sia":           bool(row[3]),
                }
            log.warning("Município %s não encontrado — usando defaults", cod)
            return MUNICIPIO_DEFAULTS.copy()
    except Exception as exc:
        log.error("Erro ao buscar município %s: %s", cod, exc)
        return MUNICIPIO_DEFAULTS.copy()
    finally:
        _pool.putconn(conn)

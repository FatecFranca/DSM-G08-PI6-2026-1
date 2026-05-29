"""
Motor de inferência do Maternar — K-Means K=3.

Carrega os artefatos na inicialização e expõe classify() como função pura.
Thread-safe: os objetos sklearn são read-only após o fit.
"""

import math
import logging
import warnings
import numpy as np
import pandas as pd
import joblib
from pathlib import Path

from config import (
    KMEANS_PATH, SCALER_PATH, PCA_PATH,
    CLUSTER_NOMES, CLUSTER_NOMES_APP, CLUSTER_RISCO, CLUSTER_COR, RECOMENDACOES,
)

log = logging.getLogger(__name__)

# ── Modelos (carregados uma vez no startup) ───────────────────────────────────
_scaler = None
_pca    = None
_kmeans = None

# Ordem exata das features contínuas usada no treino
COLS_SCALE = [
    "nu_imc",
    "nu_imc_pre_gestacional",
    "ganho_imc",
    "nu_peso",
    "nu_altura",
    "log_taxa_sifilis_gest",
    "cnes_hospitais",
    "cobertura_prenatal_log",
    "escolaridade",
]

# Ordem exata das features binárias usada no treino
COLS_BIN = [
    "est_nut_baixo_peso",
    "est_nut_adequado",
    "est_nut_sobrepeso",
    "est_nut_obesidade",
    "raca_branca",
    "raca_preta",
    "raca_amarela",
    "raca_parda",
    "raca_indigena",
    "flag_anti_hiv",
    "tem_dado_sia",
]

# Total: 9 contínuas + 11 binárias = 20 features → PCA 8 componentes → KMeans K=3


def load_models() -> None:
    global _scaler, _pca, _kmeans
    log.info("Carregando artefatos de ML...")
    _scaler = joblib.load(SCALER_PATH)
    _pca    = joblib.load(PCA_PATH)
    _kmeans = joblib.load(KMEANS_PATH)
    log.info(
        "Modelos carregados — Scaler(%d feat) → PCA(%d comp) → KMeans(K=%d)",
        _scaler.n_features_in_, _pca.n_components_, _kmeans.n_clusters,
    )


def _estado_nutricional(imc: float) -> str:
    if imc < 18.5:  return "baixo_peso"
    if imc < 25.0:  return "adequado"
    if imc < 30.0:  return "sobrepeso"
    return "obesidade"


def _raca_col(raca_cor: int) -> str:
    return {1: "branca", 2: "preta", 3: "amarela", 4: "parda", 5: "indigena"}.get(raca_cor, "parda")


def classify(payload: dict, municipio_features: dict) -> dict:
    """
    Classifica uma gestante e retorna seu cluster de cuidado.

    Parâmetros
    ----------
    payload : dict
        Dados da gestante — ver schema abaixo.
    municipio_features : dict
        Dados do município buscados via db.get_municipio_features().

    Schema de entrada (payload)
    ---------------------------
    nu_peso                : float   — peso atual em kg
    nu_altura              : float   — altura em metros
    nu_imc_pre_gestacional : float   — IMC antes da gestação
    raca_cor               : int     — 1=Branca 2=Preta 3=Amarela 4=Parda 5=Indígena
    escolaridade           : int     — 1=Sem escolaridade … 5=Superior completo
    flag_anti_hiv          : int     — 0=Não testada / 1=Testada  (default 0)

    Schema municipio_features
    -------------------------
    log_taxa_sifilis_gest  : float
    cnes_hospitais         : float
    cobertura_prenatal_log : float
    tem_dado_sia           : bool

    Retorno
    -------
    dict com cluster_id, nomes, risco, recomendações e métricas calculadas.
    """
    if _kmeans is None:
        raise RuntimeError("Modelos não carregados — chame load_models() no startup")

    # ── Features derivadas ────────────────────────────────────────────────────
    nu_peso   = float(payload["nu_peso"])
    nu_altura = float(payload["nu_altura"])
    nu_imc_pre = float(payload["nu_imc_pre_gestacional"])

    nu_imc    = nu_peso / (nu_altura ** 2)
    ganho_imc = nu_imc - nu_imc_pre

    est_nut  = _estado_nutricional(nu_imc)
    raca_col = _raca_col(int(payload["raca_cor"]))
    escolaridade = int(payload.get("escolaridade", 3))
    flag_anti_hiv = int(payload.get("flag_anti_hiv", 0))

    # ── Vetor contínuo (9 features — mesma ordem do treino) ──────────────────
    x_cont = np.array([[
        nu_imc,
        nu_imc_pre,
        ganho_imc,
        nu_peso,
        nu_altura,
        float(municipio_features.get("log_taxa_sifilis_gest", 0.0)),
        float(municipio_features.get("cnes_hospitais", 2.0)),
        float(municipio_features.get("cobertura_prenatal_log", 0.0)),
        escolaridade,
    ]])

    # ── Vetor binário (11 features — mesma ordem do treino) ──────────────────
    x_bin = np.array([[
        1 if est_nut == "baixo_peso"  else 0,
        1 if est_nut == "adequado"    else 0,
        1 if est_nut == "sobrepeso"   else 0,
        1 if est_nut == "obesidade"   else 0,
        1 if raca_col == "branca"     else 0,
        1 if raca_col == "preta"      else 0,
        1 if raca_col == "amarela"    else 0,
        1 if raca_col == "parda"      else 0,
        1 if raca_col == "indigena"   else 0,
        flag_anti_hiv,
        1 if municipio_features.get("tem_dado_sia", False) else 0,
    ]])

    # ── Pipeline de inferência ────────────────────────────────────────────────
    # DataFrame preserva os nomes de features que o scaler/pca esperam
    df_cont  = pd.DataFrame(x_cont, columns=COLS_SCALE)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        x_scaled = np.hstack([_scaler.transform(df_cont), x_bin])   # (1, 20)
        x_pca    = _pca.transform(
            pd.DataFrame(x_scaled, columns=COLS_SCALE + COLS_BIN)
        )                                                              # (1, 8)
    cluster_id = int(_kmeans.predict(x_pca)[0])

    return {
        "cluster_id":        cluster_id,
        "cluster_nome":      CLUSTER_NOMES[cluster_id],
        "cluster_nome_app":  CLUSTER_NOMES_APP[cluster_id],
        "nivel_risco":       CLUSTER_RISCO[cluster_id],
        "cor_hex":           CLUSTER_COR[cluster_id],
        "recomendacoes":     RECOMENDACOES[cluster_id],
        "metricas": {
            "nu_imc_calculado":       round(nu_imc, 2),
            "ganho_imc":              round(ganho_imc, 2),
            "estado_nutricional":     est_nut,
            "cnes_hospitais_municipio": float(municipio_features.get("cnes_hospitais", 2.0)),
        },
    }

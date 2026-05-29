"""
Maternar — API Flask de Inferência (HTTP)
=========================================
Endpoints HTTP para desenvolvimento, testes e health-check.
Em produção, o tráfego de classificação chega via mensageria (worker.py).
"""

import logging
import time
import traceback
from flask import Flask, jsonify, request

import config
import db
import classifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)

_startup_time = time.time()


# ── Startup ───────────────────────────────────────────────────────────────────

def startup() -> None:
    classifier.load_models()
    db.init_pool()
    log.info("API Maternar pronta na porta %d", config.FLASK_PORT)


# ── Helpers ───────────────────────────────────────────────────────────────────

CAMPOS_OBRIGATORIOS = [
    "nu_peso",
    "nu_altura",
    "nu_imc_pre_gestacional",
    "raca_cor",
    "escolaridade",
    "cod_municipio",
]

LIMITES = {
    "nu_peso":                (30.0, 250.0),
    "nu_altura":              (1.30, 2.15),
    "nu_imc_pre_gestacional": (10.0, 80.0),
    "raca_cor":               (1, 5),
    "escolaridade":           (1, 5),
}


def _validar(body: dict) -> list[str]:
    erros = []
    for campo in CAMPOS_OBRIGATORIOS:
        if campo not in body or body[campo] is None:
            erros.append(f"Campo obrigatório ausente: '{campo}'")

    for campo, (minv, maxv) in LIMITES.items():
        if campo in body and body[campo] is not None:
            try:
                v = float(body[campo])
                if not (minv <= v <= maxv):
                    erros.append(f"'{campo}' fora do intervalo [{minv}, {maxv}]: recebido {v}")
            except (TypeError, ValueError):
                erros.append(f"'{campo}' deve ser numérico")

    return erros


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/classificar")
def classificar():
    """
    Classifica o perfil de cuidado de uma gestante.

    Body JSON obrigatório:
        nu_peso                : number   — peso atual em kg          [30–250]
        nu_altura              : number   — altura em metros          [1.30–2.15]
        nu_imc_pre_gestacional : number   — IMC pré-gestacional       [10–80]
        raca_cor               : integer  — raça/cor (1–5)
        escolaridade           : integer  — escolaridade (1–5)
        cod_municipio          : string   — código IBGE 6 ou 7 dígitos

    Body JSON opcional:
        flag_anti_hiv          : integer  — 0=não testada / 1=testada  (default 0)

    Resposta 200:
        cluster_id        : 0 | 1 | 2
        cluster_nome      : nome clínico
        cluster_nome_app  : nome acolhedor exibido no app
        nivel_risco       : "alto" | "moderado" | "atencao"
        cor_hex           : cor da UI
        recomendacoes     : lista de {categoria, texto}
        metricas          : {nu_imc_calculado, ganho_imc, estado_nutricional, cnes_hospitais_municipio}
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"erro": "Body JSON inválido ou ausente"}), 400

    erros = _validar(body)
    if erros:
        return jsonify({"erro": "Dados inválidos", "detalhes": erros}), 422

    try:
        municipio = db.get_municipio_features(str(body["cod_municipio"]))
        resultado = classifier.classify(body, municipio)
        return jsonify(resultado), 200
    except Exception:
        log.error("Erro na classificação:\n%s", traceback.format_exc())
        return jsonify({"erro": "Erro interno na classificação"}), 500


@app.get("/health")
def health():
    return jsonify({
        "status":     "ok",
        "modelo":     "kmeans_k3",
        "K":          3,
        "silhouette": 0.2873,
        "uptime_s":   round(time.time() - _startup_time, 1),
    }), 200


@app.get("/clusters")
def clusters():
    """
    Retorna a definição dos 3 clusters: nomes, risco, cor e recomendações.
    Útil para o backend popular a tabela `clusters` do banco da aplicação.
    """
    return jsonify([
        {
            "cluster_id":       cid,
            "cluster_nome":     config.CLUSTER_NOMES[cid],
            "cluster_nome_app": config.CLUSTER_NOMES_APP[cid],
            "nivel_risco":      config.CLUSTER_RISCO[cid],
            "cor_hex":          config.CLUSTER_COR[cid],
            "recomendacoes":    config.RECOMENDACOES[cid],
        }
        for cid in range(3)
    ]), 200


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    startup()
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
    )

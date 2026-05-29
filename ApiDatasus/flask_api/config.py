import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

# ── Modelos ──────────────────────────────────────────────────────────────────
MODEL_DIR = Path(os.getenv("MODEL_DIR", BASE_DIR / "models"))

KMEANS_PATH  = MODEL_DIR / os.getenv("KMEANS_FILENAME",  "kmeans_k3.pkl")
SCALER_PATH  = MODEL_DIR / os.getenv("SCALER_FILENAME",  "scaler_maternar.pkl")
PCA_PATH     = MODEL_DIR / os.getenv("PCA_FILENAME",     "pca_maternar.pkl")

# ── PostgreSQL ────────────────────────────────────────────────────────────────
PG_HOST     = os.getenv("PGHOST",     "127.0.0.1")
PG_PORT     = int(os.getenv("PGPORT", "5435"))
PG_DATABASE = os.getenv("PGDATABASE", "maternar")
PG_USER     = os.getenv("PGUSER",     "postgres")
PG_PASSWORD = os.getenv("PGPASSWORD", "")

PG_DSN = (
    f"host={PG_HOST} port={PG_PORT} dbname={PG_DATABASE} "
    f"user={PG_USER} password={PG_PASSWORD}"
)

# ── RabbitMQ ──────────────────────────────────────────────────────────────────
RABBITMQ_HOST     = os.getenv("RABBITMQ_HOST",     "localhost")
RABBITMQ_PORT     = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER     = os.getenv("RABBITMQ_USER",     "maternar")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "")
RABBITMQ_VHOST    = os.getenv("RABBITMQ_VHOST",    "/")

# Filas
QUEUE_CLASSIFY    = os.getenv("QUEUE_CLASSIFY", "maternar.classificar")
QUEUE_DLX         = os.getenv("QUEUE_DLX",      "maternar.classificar.dlq")

RABBITMQ_URL = (
    f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}"
    f"@{RABBITMQ_HOST}:{RABBITMQ_PORT}/{RABBITMQ_VHOST}"
)

# ── Flask ─────────────────────────────────────────────────────────────────────
FLASK_HOST  = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT  = int(os.getenv("FLASK_PORT", "5001"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

# ── Definições dos Clusters ───────────────────────────────────────────────────
CLUSTER_NOMES = {
    0: "Obesidade Gestacional",
    1: "Eutrofia / Baixo Peso",
    2: "Acesso Diferenciado",
}
CLUSTER_NOMES_APP = {
    0: "Cuidado Integral",
    1: "Caminho Seguro",
    2: "Atenção Redobrada",
}
CLUSTER_RISCO = {
    0: "alto",
    1: "moderado",
    2: "atencao",
}
CLUSTER_COR = {
    0: "#FFB347",
    1: "#A8D8EA",
    2: "#FFE08A",
}

RECOMENDACOES = {
    0: [
        {"categoria": "nutricao",   "texto": "Encaminhar para nutricionista especializado em gestação"},
        {"categoria": "consultas",  "texto": "Monitoramento intensivo: consultas a cada 2-3 semanas"},
        {"categoria": "exames",     "texto": "Rastreamento de pré-eclâmpsia e diabetes gestacional"},
        {"categoria": "alertas",    "texto": "Risco elevado de parto cesáreo e complicações metabólicas"},
    ],
    1: [
        {"categoria": "nutricao",   "texto": "Orientação nutricional básica; monitorar ganho de peso"},
        {"categoria": "consultas",  "texto": "Garantir mínimo de 6 consultas de pré-natal (padrão SUS)"},
        {"categoria": "exames",     "texto": "Hemograma, glicemia, VDRL e anti-HIV (rotina)"},
        {"categoria": "alertas",    "texto": "Verificar se peso pré-gestacional está na faixa adequada"},
    ],
    2: [
        {"categoria": "nutricao",   "texto": "Avaliação nutricional completa (acesso a centros especializados)"},
        {"categoria": "consultas",  "texto": "Verificar se está vinculada a maternidade de referência"},
        {"categoria": "exames",     "texto": "Atenção ao VDRL — município com taxa de sífilis mais elevada"},
        {"categoria": "alertas",    "texto": "Pode necessitar de encaminhamento para pré-natal de alto risco"},
    ],
}

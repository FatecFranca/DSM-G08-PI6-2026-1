"""
Maternar — Worker de Mensageria (RabbitMQ)
==========================================
Consome mensagens da fila `maternar.classificar`, executa a inferência
e publica a resposta na fila de retorno informada pelo backend (reply_to).

Padrão: RPC assíncrono com correlation_id.

  Backend (Next.js)                     Worker (Flask/Python)
  ─────────────────                     ─────────────────────
  Publica em:                           Consome de:
    queue = "maternar.classificar"        queue = "maternar.classificar"
    reply_to = "<uuid-fila-temp>"
    correlation_id = "<uuid-req>"

                                        Processa e publica em:
                                          queue = reply_to
                                          correlation_id = correlation_id

  Consome de:
    "<uuid-fila-temp>"
"""

import json
import logging
import signal
import sys
import traceback
import time

import pika
import pika.exceptions

import config
import db
import classifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
log = logging.getLogger(__name__)


def _connect(retries: int = 10, delay: float = 3.0) -> pika.BlockingConnection:
    params = pika.ConnectionParameters(
        host=config.RABBITMQ_HOST,
        port=config.RABBITMQ_PORT,
        virtual_host=config.RABBITMQ_VHOST,
        credentials=pika.PlainCredentials(
            config.RABBITMQ_USER,
            config.RABBITMQ_PASSWORD,
        ),
        heartbeat=60,
        blocked_connection_timeout=300,
    )
    for attempt in range(1, retries + 1):
        try:
            conn = pika.BlockingConnection(params)
            log.info("Conectado ao RabbitMQ (%s:%d)", config.RABBITMQ_HOST, config.RABBITMQ_PORT)
            return conn
        except pika.exceptions.AMQPConnectionError as exc:
            log.warning("Tentativa %d/%d — RabbitMQ indisponível: %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(delay)
    log.error("Não foi possível conectar ao RabbitMQ após %d tentativas", retries)
    sys.exit(1)


def _declare_queues(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    # Dead-letter queue — mensagens que falharam
    channel.queue_declare(
        queue=config.QUEUE_DLX,
        durable=True,
        arguments={"x-queue-type": "classic"},
    )
    # Fila principal com DLX configurado
    channel.queue_declare(
        queue=config.QUEUE_CLASSIFY,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": config.QUEUE_DLX,
            "x-message-ttl": 30_000,   # 30 s — timeout por mensagem
        },
    )
    channel.basic_qos(prefetch_count=1)
    log.info("Filas declaradas: %s | DLQ: %s", config.QUEUE_CLASSIFY, config.QUEUE_DLX)


def _on_message(
    channel: pika.adapters.blocking_connection.BlockingChannel,
    method: pika.spec.Basic.Deliver,
    properties: pika.spec.BasicProperties,
    body: bytes,
) -> None:
    correlation_id = properties.correlation_id or "?"
    reply_to       = properties.reply_to

    log.info("Mensagem recebida [corr=%s]", correlation_id)

    # ── Resposta de erro padrão ───────────────────────────────────────────────
    def _responder(payload: dict) -> None:
        if not reply_to:
            log.warning("[corr=%s] reply_to ausente — descartando resposta", correlation_id)
            return
        channel.basic_publish(
            exchange="",
            routing_key=reply_to,
            properties=pika.BasicProperties(
                correlation_id=correlation_id,
                content_type="application/json",
                delivery_mode=1,   # não persistente (resposta é efêmera)
            ),
            body=json.dumps(payload, ensure_ascii=False).encode(),
        )

    # ── Parse do body ─────────────────────────────────────────────────────────
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        log.error("[corr=%s] JSON inválido: %s", correlation_id, exc)
        _responder({"erro": "JSON inválido", "correlation_id": correlation_id})
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    # ── Inferência ────────────────────────────────────────────────────────────
    try:
        cod_municipio = str(data.get("cod_municipio", ""))
        municipio     = db.get_municipio_features(cod_municipio)
        resultado     = classifier.classify(data, municipio)
        resultado["correlation_id"] = correlation_id
        _responder(resultado)
        channel.basic_ack(delivery_tag=method.delivery_tag)
        log.info("[corr=%s] cluster=%d | risco=%s", correlation_id,
                 resultado["cluster_id"], resultado["nivel_risco"])

    except (KeyError, ValueError, TypeError) as exc:
        log.warning("[corr=%s] Payload inválido: %s", correlation_id, exc)
        _responder({"erro": f"Payload inválido: {exc}", "correlation_id": correlation_id})
        channel.basic_ack(delivery_tag=method.delivery_tag)

    except Exception:
        log.error("[corr=%s] Erro interno:\n%s", correlation_id, traceback.format_exc())
        _responder({"erro": "Erro interno na classificação", "correlation_id": correlation_id})
        # nack com requeue=False → vai para DLQ
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def run() -> None:
    classifier.load_models()
    db.init_pool()

    conn    = _connect()
    channel = conn.channel()
    _declare_queues(channel)

    channel.basic_consume(
        queue=config.QUEUE_CLASSIFY,
        on_message_callback=_on_message,
    )

    def _shutdown(sig, frame):
        log.info("Encerrando worker (sinal %d)...", sig)
        channel.stop_consuming()
        conn.close()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info("Worker aguardando mensagens em '%s'...", config.QUEUE_CLASSIFY)
    channel.start_consuming()


if __name__ == "__main__":
    run()

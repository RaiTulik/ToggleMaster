import json
import logging
import os
import threading
from datetime import datetime

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)

AWS_REGION = os.getenv("AWS_REGION")
SQS_QUEUE_URL = os.getenv("AWS_SQS_URL")
DYNAMODB_TABLE_NAME = os.getenv("AWS_DYNAMODB_TABLE")

if not all([AWS_REGION, SQS_QUEUE_URL, DYNAMODB_TABLE_NAME]):
    raise RuntimeError(
        "AWS_REGION, AWS_SQS_URL e AWS_DYNAMODB_TABLE devem ser definidos."
    )

session = boto3.Session(region_name=AWS_REGION)

# As novas tentativas de processamento ficam a cargo da fila.
io_config = Config(
    connect_timeout=2,
    read_timeout=5,
    retries={"total_max_attempts": 1, "mode": "standard"},
)
poll_config = Config(
    connect_timeout=2,
    read_timeout=25,
    retries={"total_max_attempts": 1, "mode": "standard"},
)

sqs_client = session.client(
    "sqs",
    endpoint_url=os.getenv("AWS_SQS_ENDPOINT") or None,
    config=io_config,
)
poll_client = session.client(
    "sqs",
    endpoint_url=os.getenv("AWS_SQS_ENDPOINT") or None,
    config=poll_config,
)
dynamodb_client = session.client(
    "dynamodb",
    endpoint_url=os.getenv("AWS_DYNAMODB_ENDPOINT") or None,
    config=io_config,
)

stop_event = threading.Event()
ready_event = threading.Event()
worker_lock = threading.Lock()
worker_thread = None

app = Flask(__name__)


class InvalidEvent(ValueError):
    pass


def require_text(body, name, max_bytes):
    value = body.get(name)
    if not isinstance(value, str) or not value.strip():
        raise InvalidEvent(f"{name} deve ser uma string preenchida")
    if len(value.encode("utf-8")) > max_bytes:
        raise InvalidEvent(f"{name} excede {max_bytes} bytes")
    return value


def build_item(message):
    try:
        body = json.loads(message["Body"])
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidEvent("JSON invalido") from exc

    if not isinstance(body, dict):
        raise InvalidEvent("O evento deve ser um objeto JSON")

    # Compatibilidade com eventos antigos, sem ID no corpo.
    if "event_id" not in body:
        body["event_id"] = message["MessageId"]

    event_id = require_text(body, "event_id", 128)
    user_id = require_text(body, "user_id", 256)
    flag_name = require_text(body, "flag_name", 100)
    timestamp = require_text(body, "timestamp", 64)

    if type(body.get("result")) is not bool:
        raise InvalidEvent("result deve ser um booleano")

    try:
        parsed_timestamp = datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise InvalidEvent("timestamp invalido") from exc

    if parsed_timestamp.utcoffset() is None:
        raise InvalidEvent("timestamp deve informar o fuso horario")

    return {
        "event_id": {"S": event_id},
        "user_id": {"S": user_id},
        "flag_name": {"S": flag_name},
        "result": {"BOOL": body["result"]},
        "timestamp": {"S": timestamp},
    }


def save_event(item):
    try:
        dynamodb_client.put_item(
            TableName=DYNAMODB_TABLE_NAME,
            Item=item,
            ConditionExpression="attribute_not_exists(event_id)",
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code != "ConditionalCheckFailedException":
            raise

        existing = dynamodb_client.get_item(
            TableName=DYNAMODB_TABLE_NAME,
            Key={"event_id": item["event_id"]},
            ConsistentRead=True,
        ).get("Item")

        if existing != item:
            raise InvalidEvent(
                "event_id ja utilizado por um evento diferente"
            ) from exc

        log.info(
            "Evento %s ja armazenado; entrega repetida reconhecida.",
            item["event_id"]["S"],
        )


def process_message(message):
    message_id = message.get("MessageId", "desconhecido")

    try:
        item = build_item(message)
        save_event(item)

        # Confirma somente depois de persistir ou reconhecer duplicata.
        sqs_client.delete_message(
            QueueUrl=SQS_QUEUE_URL,
            ReceiptHandle=message["ReceiptHandle"],
        )
        log.info(
            "Evento %s persistido e mensagem %s confirmada.",
            item["event_id"]["S"],
            message_id,
        )
    except InvalidEvent as exc:
        # Sem confirmação: a fila fará novas entregas e aplicará a DLQ.
        log.error("Mensagem %s rejeitada: %s", message_id, exc)
    except Exception:
        ready_event.clear()
        log.exception(
            "Falha ao processar mensagem %s; permanecera na fila.",
            message_id,
        )
        stop_event.wait(2)


def sqs_worker_loop():
    log.info("Consumidor SQS iniciado.")

    try:
        while not stop_event.is_set():
            try:
                table = dynamodb_client.describe_table(
                    TableName=DYNAMODB_TABLE_NAME
                )["Table"]

                if table["TableStatus"] != "ACTIVE":
                    raise RuntimeError("Tabela DynamoDB ainda indisponivel")

                response = poll_client.receive_message(
                    QueueUrl=SQS_QUEUE_URL,
                    MaxNumberOfMessages=1,
                    WaitTimeSeconds=20,
                    VisibilityTimeout=60,
                )

                if stop_event.is_set():
                    break

                ready_event.set()

                for message in response.get("Messages", []):
                    if stop_event.is_set():
                        break
                    process_message(message)

            except Exception:
                ready_event.clear()
                log.exception("Falha no consumidor SQS.")
                stop_event.wait(2)
    finally:
        ready_event.clear()
        log.info("Consumidor SQS encerrado.")


def start_worker():
    global worker_thread

    with worker_lock:
        if worker_thread is not None and worker_thread.is_alive():
            return

        stop_event.clear()
        ready_event.clear()
        worker_thread = threading.Thread(
            target=sqs_worker_loop,
            name="sqs-consumer",
            daemon=True,
        )
        worker_thread.start()


def stop_worker():
    stop_event.set()
    ready_event.clear()

    with worker_lock:
        thread = worker_thread

    if thread is not None:
        thread.join(timeout=35)
        if thread.is_alive():
            log.error(
                "Consumidor excedeu o prazo de encerramento; "
                "mensagens sem confirmacao poderao ser reentregues."
            )


@app.get("/health")
def health():
    # Liveness: o processo HTTP esta respondendo.
    return jsonify({"status": "ok"})


@app.get("/ready")
def readiness():
    with worker_lock:
        alive = worker_thread is not None and worker_thread.is_alive()

    if stop_event.is_set() or not alive or not ready_event.is_set():
        return jsonify({"status": "not ready"}), 503

    return jsonify({"status": "ready"})


if __name__ == "__main__":
    start_worker()
    try:
        app.run(
            host="0.0.0.0",
            port=int(os.getenv("PORT", "8005")),
            debug=False,
            use_reloader=False,
        )
    finally:
        stop_worker()
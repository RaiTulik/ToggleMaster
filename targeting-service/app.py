import logging
import os
import sys
from contextlib import contextmanager
from functools import wraps

import psycopg2
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from psycopg2.extras import Json, RealDictCursor
from psycopg2.pool import PoolError, SimpleConnectionPool

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL")

if not DATABASE_URL or not AUTH_SERVICE_URL:
    log.critical("DATABASE_URL e AUTH_SERVICE_URL devem ser definidos.")
    sys.exit(1)

pool = None


class DatabaseUnavailable(Exception):
    pass


def get_pool():
    global pool

    if pool is None:
        pool = SimpleConnectionPool(
            1,
            5,
            dsn=DATABASE_URL,
            connect_timeout=2,
            options="-c statement_timeout=2000 -c lock_timeout=1000",
        )
        log.info("Pool de conexoes com o PostgreSQL (targeting) inicializado.")

    return pool


def release_connection(conn, discard=False):
    if conn is None:
        return

    if not discard and not conn.closed:
        try:
            conn.rollback()
        except psycopg2.Error:
            discard = True

    try:
        pool.putconn(conn, close=discard or bool(conn.closed))
    except (psycopg2.Error, PoolError):
        conn.close()
        log.exception("Falha ao devolver conexao ao pool.")


def checkout_connection():
    # A repeticao ocorre apenas antes da operacao de negocio.
    for attempt in range(2):
        conn = None

        try:
            conn = get_pool().getconn()

            if conn.closed:
                raise psycopg2.InterfaceError("Conexao fechada")

            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()

            conn.rollback()
            return conn

        except PoolError as exc:
            raise DatabaseUnavailable("Pool indisponivel") from exc

        except (
            psycopg2.OperationalError,
            psycopg2.InterfaceError,
        ) as exc:
            release_connection(conn, discard=True)
            log.warning(
                "Conexao PostgreSQL indisponivel na verificacao "
                "(tentativa %s/2).",
                attempt + 1,
            )

            if attempt == 1:
                raise DatabaseUnavailable(
                    "Nao foi possivel obter uma conexao valida"
                ) from exc

        except Exception:
            release_connection(conn, discard=True)
            raise


@contextmanager
def database_cursor(write=False):
    conn = checkout_connection()
    discard = False

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur

        if write:
            conn.commit()
        else:
            conn.rollback()

    except (
        psycopg2.OperationalError,
        psycopg2.InterfaceError,
    ) as exc:
        discard = True
        raise DatabaseUnavailable(
            "Conexao perdida durante a operacao"
        ) from exc

    finally:
        release_connection(conn, discard=discard)


@app.errorhandler(DatabaseUnavailable)
def handle_database_unavailable(error):
    log.error("Falha de conexao com o banco de targeting: %s", error)
    return jsonify({
        "error": "Banco de targeting temporariamente indisponivel",
        "message": (
            "Se uma escrita estava em andamento, seu resultado pode "
            "ser incerto. Consulte o recurso antes de repetir."
        ),
    }), 503


@app.errorhandler(psycopg2.Error)
def handle_database_error(error):
    log.exception("Erro na operacao com o banco de targeting.")
    return jsonify({"error": "Erro interno do servidor"}), 500


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return jsonify({"error": "Authorization header obrigatorio"}), 401

        try:
            with requests.get(
                f"{AUTH_SERVICE_URL.rstrip('/')}/validate",
                headers={"Authorization": auth_header},
                timeout=3,
                allow_redirects=False,
            ) as response:
                status = response.status_code
        except requests.exceptions.Timeout:
            log.error("Timeout ao consultar o auth-service.")
            return jsonify({
                "error": "Servico de autenticacao indisponivel (timeout)"
            }), 504
        except requests.exceptions.RequestException:
            log.exception("Falha ao consultar o auth-service.")
            return jsonify({
                "error": "Servico de autenticacao indisponivel"
            }), 503

        if status == 401:
            return jsonify({"error": "Chave de API invalida ou inativa"}), 401

        if status != 200:
            log.error("Auth-service retornou status inesperado: %s", status)
            return jsonify({
                "error": "Servico de autenticacao indisponivel"
            }), 503

        return f(*args, **kwargs)

    return decorated


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# Readiness: verifica se o PostgreSQL aceita conexoes.
@app.route("/ready")
def ready():
    conn = None

    try:
        conn = checkout_connection()
        return jsonify({"status": "ready"}), 200
    except (DatabaseUnavailable, psycopg2.Error):
        return jsonify({"status": "not ready"}), 503
    finally:
        if conn is not None:
            release_connection(conn)


@app.route("/rules", methods=["POST"])
@require_auth
def create_rule():
    data = request.get_json()
    if (
        not isinstance(data, dict)
        or "flag_name" not in data
        or "rules" not in data
    ):
        return jsonify({
            "error": "'flag_name' e 'rules' sao obrigatorios"
        }), 400

    flag_name = data["flag_name"]
    rules_obj = data["rules"]
    is_enabled = data.get("is_enabled", True)

    try:
        with database_cursor(write=True) as cur:
            cur.execute(
                "INSERT INTO targeting_rules "
                "(flag_name, is_enabled, rules, created_at, updated_at) "
                "VALUES (%s, %s, %s, NOW(), NOW()) RETURNING *",
                (flag_name, is_enabled, Json(rules_obj)),
            )
            new_rule = cur.fetchone()
    except psycopg2.errors.UniqueViolation:
        return jsonify({
            "error": f"Regra para a flag '{flag_name}' ja existe"
        }), 409

    log.info("Regra para %r criada com sucesso.", flag_name)
    return jsonify(new_rule), 201


@app.route("/rules/<string:flag_name>", methods=["GET"])
@require_auth
def get_rule(flag_name):
    with database_cursor() as cur:
        cur.execute(
            "SELECT * FROM targeting_rules WHERE flag_name = %s",
            (flag_name,),
        )
        rule = cur.fetchone()

    if not rule:
        return jsonify({"error": "Regra nao encontrada"}), 404

    return jsonify(rule)


@app.route("/rules/<string:flag_name>", methods=["PUT"])
@require_auth
def update_rule(flag_name):
    data = request.get_json()
    if not isinstance(data, dict) or not data:
        return jsonify({"error": "Corpo da requisicao obrigatorio"}), 400

    fields = []
    values = []

    if "rules" in data:
        fields.append("rules = %s")
        values.append(Json(data["rules"]))
    if "is_enabled" in data:
        fields.append("is_enabled = %s")
        values.append(data["is_enabled"])

    if not fields:
        return jsonify({"error": "Informe rules ou is_enabled"}), 400

    values.append(flag_name)
    query = (
        f"UPDATE targeting_rules SET {', '.join(fields)} "
        "WHERE flag_name = %s RETURNING *"
    )

    with database_cursor(write=True) as cur:
        cur.execute(query, tuple(values))
        updated_rule = cur.fetchone()

    if not updated_rule:
        return jsonify({"error": "Regra nao encontrada"}), 404

    log.info("Regra para %r atualizada com sucesso.", flag_name)
    return jsonify(updated_rule), 200


@app.route("/rules/<string:flag_name>", methods=["DELETE"])
@require_auth
def delete_rule(flag_name):
    with database_cursor(write=True) as cur:
        cur.execute(
            "DELETE FROM targeting_rules WHERE flag_name = %s",
            (flag_name,),
        )
        deleted = cur.rowcount

    if deleted == 0:
        return jsonify({"error": "Regra nao encontrada"}), 404

    log.info("Regra para %r deletada com sucesso.", flag_name)
    return "", 204


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8003))
    app.run(host="0.0.0.0", port=port, debug=False)
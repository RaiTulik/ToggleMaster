import logging
import os
import sys
from functools import wraps

import psycopg2
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from psycopg2.extras import Json, RealDictCursor
from psycopg2.pool import SimpleConnectionPool

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL")

if not DATABASE_URL or not AUTH_SERVICE_URL:
    log.critical("DATABASE_URL e AUTH_SERVICE_URL devem ser definidos.")
    sys.exit(1)

try:
    pool = SimpleConnectionPool(1, 5, dsn=DATABASE_URL)
    log.info("Pool de conexoes com o PostgreSQL (targeting) inicializado.")
except psycopg2.OperationalError:
    log.exception("Erro fatal ao conectar ao PostgreSQL.")
    sys.exit(1)


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


@app.route("/rules", methods=["POST"])
@require_auth
def create_rule():
    data = request.get_json()
    if not data or "flag_name" not in data or "rules" not in data:
        return jsonify({
            "error": "'flag_name' e 'rules' sao obrigatorios"
        }), 400

    flag_name = data["flag_name"]
    rules_obj = data["rules"]
    is_enabled = data.get("is_enabled", True)

    conn = None
    cur = None
    try:
        conn = pool.getconn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "INSERT INTO targeting_rules "
            "(flag_name, is_enabled, rules, created_at, updated_at) "
            "VALUES (%s, %s, %s, NOW(), NOW()) RETURNING *",
            (flag_name, is_enabled, Json(rules_obj)),
        )
        new_rule = cur.fetchone()
        conn.commit()
        log.info("Regra para %r criada com sucesso.", flag_name)
        return jsonify(new_rule), 201
    except psycopg2.IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({
            "error": f"Regra para a flag '{flag_name}' ja existe"
        }), 409
    except Exception as e:
        if conn:
            conn.rollback()
        log.exception("Erro ao criar regra.")
        return jsonify({
            "error": "Erro interno do servidor",
            "details": str(e),
        }), 500
    finally:
        if cur:
            cur.close()
        if conn:
            pool.putconn(conn)


@app.route("/rules/<string:flag_name>", methods=["GET"])
@require_auth
def get_rule(flag_name):
    conn = None
    cur = None
    try:
        conn = pool.getconn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT * FROM targeting_rules WHERE flag_name = %s",
            (flag_name,),
        )
        rule = cur.fetchone()
        if not rule:
            return jsonify({"error": "Regra nao encontrada"}), 404
        return jsonify(rule)
    except Exception as e:
        log.exception("Erro ao buscar regra para %r.", flag_name)
        return jsonify({
            "error": "Erro interno do servidor",
            "details": str(e),
        }), 500
    finally:
        if cur:
            cur.close()
        if conn:
            pool.putconn(conn)


@app.route("/rules/<string:flag_name>", methods=["PUT"])
@require_auth
def update_rule(flag_name):
    data = request.get_json()
    if not data:
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
        return jsonify({
            "error": "Informe rules ou is_enabled"
        }), 400

    values.append(flag_name)
    query = (
        f"UPDATE targeting_rules SET {', '.join(fields)} "
        "WHERE flag_name = %s RETURNING *"
    )

    conn = None
    cur = None
    try:
        conn = pool.getconn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query, tuple(values))

        if cur.rowcount == 0:
            return jsonify({"error": "Regra nao encontrada"}), 404

        updated_rule = cur.fetchone()
        conn.commit()
        log.info("Regra para %r atualizada com sucesso.", flag_name)
        return jsonify(updated_rule), 200
    except Exception as e:
        if conn:
            conn.rollback()
        log.exception("Erro ao atualizar regra para %r.", flag_name)
        return jsonify({
            "error": "Erro interno do servidor",
            "details": str(e),
        }), 500
    finally:
        if cur:
            cur.close()
        if conn:
            pool.putconn(conn)


@app.route("/rules/<string:flag_name>", methods=["DELETE"])
@require_auth
def delete_rule(flag_name):
    conn = None
    cur = None
    try:
        conn = pool.getconn()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM targeting_rules WHERE flag_name = %s",
            (flag_name,),
        )

        if cur.rowcount == 0:
            return jsonify({"error": "Regra nao encontrada"}), 404

        conn.commit()
        log.info("Regra para %r deletada com sucesso.", flag_name)
        return "", 204
    except Exception as e:
        if conn:
            conn.rollback()
        log.exception("Erro ao deletar regra para %r.", flag_name)
        return jsonify({
            "error": "Erro interno do servidor",
            "details": str(e),
        }), 500
    finally:
        if cur:
            cur.close()
        if conn:
            pool.putconn(conn)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8003))
    app.run(host="0.0.0.0", port=port, debug=False)
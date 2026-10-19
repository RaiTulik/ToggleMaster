import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

AUTH_URL = os.environ["AUTH_SERVICE_URL"].rstrip("/")
MASTER_KEY = os.environ["MASTER_KEY"]
KEY_FILE = Path("/service-key/evaluation-api-key")


def request_json(path, token=None, body=None):
    headers = {"Accept": "application/json"}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    request = Request(
        f"{AUTH_URL}{path}",
        data=data,
        headers=headers,
    )

    with urlopen(request, timeout=5) as response:
        return json.load(response)


def prepare_key():
    # Reutiliza a chave somente se o auth confirmar sua validade.
    if KEY_FILE.exists():
        existing_key = KEY_FILE.read_text(encoding="utf-8").strip()

        if existing_key:
            try:
                request_json("/validate", token=existing_key)
                print("Chave do evaluation validada e reutilizada.", flush=True)
                return
            except HTTPError as error:
                if error.code != 401:
                    raise

    response = request_json(
        "/admin/keys",
        token=MASTER_KEY,
        body={"name": "evaluation-service-local"},
    )

    new_key = response.get("key")
    if not isinstance(new_key, str) or not new_key.strip():
        raise ValueError("O auth nao retornou uma chave valida.")

    # Confirma a chave antes de disponibiliza-la ao evaluation.
    request_json("/validate", token=new_key)

    temporary_file = KEY_FILE.with_suffix(".tmp")
    temporary_file.write_text(new_key, encoding="utf-8")
    temporary_file.chmod(0o600)
    temporary_file.replace(KEY_FILE)

    print("Nova chave do evaluation criada e armazenada.", flush=True)


for attempt in range(1, 31):
    try:
        request_json("/health")
        prepare_key()
        break
    except HTTPError as error:
        # Erros de configuracao/autorizacao exigem correcao.
        if error.code < 500:
            raise RuntimeError(
                f"Preparacao recusada pelo auth: HTTP {error.code}."
            ) from None

        if attempt == 30:
            raise RuntimeError("Auth indisponivel apos as tentativas.") from None

        print("Auth temporariamente indisponivel; tentando novamente.", flush=True)
        time.sleep(2)
    except (URLError, TimeoutError, ConnectionError):
        if attempt == 30:
            raise RuntimeError("Nao foi possivel acessar o auth.") from None

        print("Aguardando o auth ficar acessivel.", flush=True)
        time.sleep(2)
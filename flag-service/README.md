# Flag Service

Serviço Python responsável por criar, consultar, atualizar e remover
as definições de feature flags.

## Execução local

Use o Docker Compose na raiz do repositório, conforme o
[guia principal](../README.md).

O serviço utiliza a porta local `8002`, depende do auth para validar
chaves de API e armazena suas definições no PostgreSQL.

## Configuração

| Variável | Finalidade |
|---|---|
| PORT | Porta HTTP; padrão 8002 |
| DATABASE_URL | Conexão com o banco de flags |
| AUTH_SERVICE_URL | Endereço do serviço de autenticação |

No Compose, a aplicação utiliza o banco `flags_db` com o usuário `flag_app`.
Esse usuário não possui permissão de conexão ao banco `targeting_db`.

## Endpoints

Todas as rotas de flags exigem o header:

```text
Authorization: Bearer <chave-de-api>
```

A chave deve ser criada no auth com a MASTER_KEY.
A MASTER_KEY não é utilizada diretamente nas rotas de flags.

| Método | Rota | Finalidade |
|---|---|---|
| GET | `/health` | Verificar resposta do processo HTTP; não exige chave |
| POST | `/flags` | Criar uma flag |
| GET | `/flags` | Listar as flags |
| GET | `/flags/<name>` | Consultar uma flag |
| PUT | `/flags/<name>` | Atualizar descrição ou estado |
| DELETE | `/flags/<name>` | Remover uma flag |

Corpo de criação:

```json
{
  "name": "enable-new-dashboard",
  "description": "Ativa o novo dashboard",
  "is_enabled": true
}
```

O campo `name` é obrigatório.
Quando omitidos, `description` recebe uma string vazia e `is_enabled`
recebe `false`.

Corpo de atualização:

```json
{
  "description": "Descricao atualizada",
  "is_enabled": false
}
```

A atualização exige pelo menos um dos campos `description` ou `is_enabled`.
O nome da flag não é alterado pelo PUT.

## Respostas e falhas

| Situação | HTTP |
|---|---|
| Flag criada | 201 |
| Consulta ou atualização concluída | 200 |
| Flag removida | 204 |
| Campos obrigatórios ausentes | 400 |
| Chave ausente, inválida ou inativa | 401 |
| Flag não encontrada | 404 |
| Nome duplicado na criação | 409 |
| Auth indisponível | 503 |
| Timeout ao consultar o auth | 504 |
| Erro interno na operação com o banco de flags | 500 |
| Falha de conexão com o banco do serviço | 503 |

O middleware consulta o auth com timeout de três segundos.
Uma falha do auth não é interpretada como chave inválida.

## Saúde e cache

O `/health` verifica somente a resposta do processo HTTP.
Este serviço ainda não possui endpoint `/ready`.

Alterações nas definições não invalidam imediatamente o cache do evaluation.
Dados já armazenados podem continuar sendo utilizados até o TTL de
30 segundos expirar.

## Recuperação do banco

As conexões são verificadas antes do uso. Conexões quebradas são
descartadas, permitindo recuperação após o retorno do PostgreSQL
sem reiniciar a aplicação.

As transações são finalizadas antes da devolução da conexão ao pool.
Operações de escrita não são repetidas automaticamente.

Se ocorrer perda de conexão durante uma escrita, consulte o recurso
antes de repetir a operação, pois o resultado pode ser incerto.


## Operação

A imagem executa a aplicação com Gunicorn.

Para consultar os logs, execute na raiz do repositório:

```powershell
docker compose logs --tail 30 flag-service
```

O roteiro para criar uma chave, cadastrar uma flag e avaliar seu resultado
está no [README principal](../README.md).
# Targeting Service

Serviço Python responsável por criar, consultar, atualizar e remover
as regras de segmentação associadas às feature flags.

## Execução local

Use o Docker Compose na raiz do repositório, conforme o
[guia principal](../README.md).

O serviço utiliza a porta local `8003`, depende do auth para validar
chaves de API e armazena as regras no PostgreSQL.

## Configuração

| Variável | Finalidade |
|---|---|
| PORT | Porta HTTP; padrão 8003 |
| DATABASE_URL | Conexão com o banco de targeting |
| AUTH_SERVICE_URL | Endereço do serviço de autenticação |

No Compose, a aplicação utiliza o banco `targeting_db` com o usuário
`targeting_app`. Esse usuário não possui permissão de conexão ao banco
`flags_db`.

Os dois bancos compartilham o container PostgreSQL `flag-db`,
mas possuem usuários e permissões separados.

## Endpoints

Todas as rotas de regras exigem o header:

```text
Authorization: Bearer <chave-de-api>
```

A chave deve ser criada no auth com a MASTER_KEY.
A MASTER_KEY não é utilizada diretamente nas rotas de regras.

| Método | Rota | Finalidade |
|---|---|---|
| GET | `/health` | Verificar resposta do processo HTTP; não exige chave |
| POST | `/rules` | Criar uma regra para uma flag |
| GET | `/rules/<flag_name>` | Consultar a regra |
| PUT | `/rules/<flag_name>` | Atualizar a regra ou seu estado |
| DELETE | `/rules/<flag_name>` | Remover a regra |

Corpo de criação de uma regra percentual:

```json
{
  "flag_name": "enable-new-dashboard",
  "is_enabled": true,
  "rules": {
    "type": "PERCENTAGE",
    "value": 50
  }
}
```

Os campos `flag_name` e `rules` são obrigatórios.
Quando omitido, `is_enabled` recebe `true`.

Corpo de atualização:

```json
{
  "rules": {
    "type": "PERCENTAGE",
    "value": 100
  }
}
```

A atualização exige pelo menos um dos campos `rules` ou `is_enabled`.
Quando informado, `rules` substitui o objeto anterior por completo.
O campo `flag_name` não é alterado pelo PUT.

O serviço armazena as regras em JSON. A interpretação das regras
é responsabilidade do evaluation.

O cadastro de uma regra não verifica se a flag correspondente existe
no flag-service. Para o teste integrado, cadastre ambos usando o mesmo nome.

## Respostas e falhas

| Situação | HTTP |
|---|---|
| Regra criada | 201 |
| Consulta ou atualização concluída | 200 |
| Regra removida | 204 |
| Campos obrigatórios ausentes | 400 |
| Chave ausente, inválida ou inativa | 401 |
| Regra não encontrada | 404 |
| Regra duplicada para a mesma flag | 409 |
| Auth indisponível | 503 |
| Timeout ao consultar o auth | 504 |
| Erro interno na operação com o banco de targeting | 500 |

O middleware consulta o auth com timeout de três segundos.
Uma falha do auth não é interpretada como chave inválida.

## Saúde e cache

O `/health` verifica somente a resposta do processo HTTP.
Este serviço ainda não possui endpoint `/ready`.

Alterações nas regras não invalidam imediatamente o cache do evaluation.
Dados já armazenados podem continuar sendo utilizados até o TTL de
30 segundos expirar.

O evaluation distingue uma regra inexistente de uma falha ao consultar
o targeting. A indisponibilidade do serviço não é tratada como ausência
de regra.

## Operação

A imagem executa a aplicação com Gunicorn.

Para consultar os logs, execute na raiz do repositório:

```powershell
docker compose logs --tail 30 targeting-service
```

O roteiro de criação de uma regra e avaliação de uma flag está no
[README principal](../README.md).
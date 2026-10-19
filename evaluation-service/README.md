# Evaluation Service

Serviço Go responsável por avaliar feature flags para um usuário.
Consulta definições e regras, utiliza cache Redis e publica eventos
de avaliação no SQS.

## Execução local

Use o Docker Compose na raiz do repositório, conforme o
[guia principal](../README.md).

O serviço utiliza a porta local `8004`.

No ambiente local, o ElasticMQ substitui o Amazon SQS.
Não são necessários recursos ou credenciais reais da AWS.

## Fluxo de avaliação

1. Recebe `user_id` e `flag_name`.
2. Consulta as informações da flag no Redis.
3. Em caso de cache MISS, consulta flag-service e targeting-service
   em paralelo.
4. Avalia a definição e a regra para o usuário informado.
5. Coloca um evento na fila interna de publicação.
6. Retorna o resultado e o identificador do evento.

Os enviadores publicam os eventos no SQS de forma assíncrona.
O analytics consome esses eventos e os grava no DynamoDB.

## Configuração

| Variável | Finalidade |
|---|---|
| PORT | Porta HTTP; padrão 8004 |
| REDIS_URL | Endereço do Redis |
| FLAG_SERVICE_URL | Endereço do serviço de flags |
| TARGETING_SERVICE_URL | Endereço do serviço de targeting |
| SERVICE_API_KEY_FILE | Arquivo com a chave de API do evaluation |
| SERVICE_API_KEY | Alternativa para fornecer a chave por variável |
| AWS_REGION | Região utilizada pelo cliente SQS |
| AWS_SQS_URL | URL da fila de eventos |
| AWS_SQS_ENDPOINT | Endpoint alternativo; utilizado pelo ElasticMQ |

Quando `SERVICE_API_KEY_FILE` está definido, a chave é lida desse arquivo.
Caso contrário, utiliza-se `SERVICE_API_KEY`.

No Compose, o inicializador `service-key-init` prepara a chave
automaticamente. Ela fica em um volume compartilhado, montado como
somente leitura no evaluation.

O serviço não recebe a MASTER_KEY nem credenciais dos bancos PostgreSQL.

As credenciais AWS fictícias do Compose atendem exclusivamente aos
emuladores locais. Na cloud, a autenticação deverá utilizar o mecanismo
definido para o ambiente de implantação.

Sem `AWS_SQS_URL`, o publicador fica desabilitado e as avaliações são
registradas nos logs. O Compose configura a fila, portanto a publicação
está habilitada na execução integrada local.

## Endpoints

| Método | Rota | Finalidade |
|---|---|---|
| GET | `/health` | Verificar resposta do processo HTTP |
| GET | `/ready` | Verificar condições locais de prontidão |
| GET | `/evaluate` | Avaliar uma flag para um usuário |

O endpoint de avaliação não exige chave de API do cliente.
O evaluation utiliza sua própria chave para consultar flag e targeting.

Exemplo:

```text
GET /evaluate?user_id=usuario-123&flag_name=enable-new-dashboard
```

Resposta de exemplo com publicação habilitada:

```json
{
  "flag_name": "enable-new-dashboard",
  "user_id": "usuario-123",
  "result": true,
  "event_id": "65caa538be12cee1f9ed370a67b81524"
}
```

O `event_id` é gerado para cada requisição.
Repetir a chamada HTTP cria uma nova avaliação e um novo evento.

Com a publicação desabilitada, o campo `event_id` é omitido.

## Respostas e falhas

| Situação | HTTP |
|---|---|
| Avaliação concluída e evento aceito na fila interna, quando habilitada | 200 |
| Parâmetros ausentes ou acima do tamanho permitido | 400 |
| Método não permitido | 405 |
| Falha ao preparar o identificador do evento | 500 |
| Falha ao consultar os serviços necessários à avaliação | 502 |
| Serviço encerrando ou fila interna indisponível | 503 |

O limite de `user_id` é de 256 bytes.
O limite de `flag_name` é de 100 bytes.

Uma flag inexistente produz resultado `false`.
Uma regra inexistente permite usar o comportamento padrão da flag.
Falhas de comunicação com targeting são retornadas como erro,
em vez de serem interpretadas como ausência de regra.

## Cache

O Redis armazena as informações combinadas da definição e da regra,
com TTL de 30 segundos.

Requisições consecutivas podem apresentar `Cache MISS` e depois
`Cache HIT` nos logs.

Alterações feitas em flag ou targeting podem levar até o vencimento
do cache existente para aparecer nas avaliações.

O cache evita consultas aos serviços de origem; cada avaliação ainda
gera seu próprio evento quando a publicação está habilitada.

## Publicação de eventos

O publicador possui uma fila interna com capacidade para 256 eventos
aguardando processamento e quatro enviadores concorrentes.

O corpo publicado contém:
- `event_id`.
- `user_id`.
- `flag_name`.
- `result`, como booleano.
- `timestamp`, com fuso horário.

As tentativas de envio do mesmo evento preservam seu identificador.

A resposta HTTP de sucesso não garante que o SQS já recebeu o evento.
Ela confirma a aceitação na fila interna do processo.

Essa fila é mantida em memória. Uma interrupção abrupta ou uma falha
definitiva de envio pode causar perda de eventos.
Não há outbox persistente nem garantia de entrega exatamente uma vez.

Falhas de publicação são registradas nos logs.

## Saúde e prontidão

O `/health` verifica a resposta do processo HTTP.

O `/ready` verifica:
- Se o serviço está encerrando.
- Se o Redis responde.
- Se o publicador, quando habilitado, aceita novos eventos.

O `/ready` não comprova conectividade com SQS, flag-service ou
targeting-service, nem garante a entrega de eventos.

## Encerramento e chave de serviço

Ao receber SIGTERM, o serviço interrompe a aceitação de novas conexões,
permite até dez segundos para concluir as requisições HTTP e até
30 segundos para finalizar as tentativas pendentes do publicador.

O Compose permite 50 segundos antes de forçar o encerramento.

A chave de API é carregada na inicialização.
Depois de revogá-la, prepare uma nova chave e reinicie o evaluation:

```powershell
docker compose run --rm service-key-init
docker compose restart evaluation-service
```

## Operação

Execute na raiz do repositório:

```powershell
docker compose logs --tail 30 evaluation-service
```

O roteiro completo de criação de uma flag, regra e consulta do evento
no DynamoDB está no [README principal](../README.md).
# Analytics Service

Serviço Python responsável por consumir eventos de avaliação do SQS
e armazená-los no DynamoDB.

Sua API HTTP expõe somente os endpoints de saúde e prontidão.
A consulta dos eventos armazenados não é disponibilizada por uma rota HTTP.

## Execução local

Use o Docker Compose na raiz do repositório, conforme o
[guia principal](../README.md).

O serviço utiliza a porta local `8005`.

No ambiente local:
- ElasticMQ substitui o Amazon SQS.
- DynamoDB Local armazena os eventos.
- O inicializador `dynamodb-init` prepara a tabela automaticamente.

Não são necessários recursos ou credenciais reais da AWS.

## Configuração

| Variável | Finalidade |
|---|---|
| PORT | Porta HTTP; padrão 8005 |
| AWS_REGION | Região dos clientes AWS |
| AWS_SQS_URL | URL da fila de eventos |
| AWS_SQS_ENDPOINT | Endpoint alternativo do SQS |
| AWS_DYNAMODB_TABLE | Nome da tabela de eventos |
| AWS_DYNAMODB_ENDPOINT | Endpoint alternativo do DynamoDB |

`AWS_REGION`, `AWS_SQS_URL` e `AWS_DYNAMODB_TABLE` são obrigatórias.

O Compose configura credenciais fictícias para os emuladores locais.
Na implantação cloud, os clientes deverão receber credenciais pelo
mecanismo definido para o ambiente AWS.

## Endpoints

| Método | Rota | Finalidade |
|---|---|---|
| GET | `/health` | Verificar resposta do processo HTTP |
| GET | `/ready` | Verificar prontidão do consumidor |

O `/health` não consulta SQS ou DynamoDB.

O `/ready` considera:
- Se a thread do consumidor está ativa.
- Se o encerramento foi solicitado.
- Se o consumidor concluiu recentemente suas verificações de
  disponibilidade e a consulta da fila.

A verificação ocorre no ciclo do consumidor.
Portanto, a mudança de estado não é instantânea após uma falha
ou recuperação de dependência.

Uma mensagem com conteúdo inválido não torna o serviço indisponível.
Uma falha operacional no processamento pode retirar sua prontidão.

## Processamento

O consumidor:

1. Verifica se a tabela DynamoDB está ativa.
2. Consulta a fila com long polling de até 20 segundos.
3. Recebe uma mensagem por vez, com visibilidade de 60 segundos.
4. Valida o conteúdo do evento.
5. Grava o evento no DynamoDB ou reconhece uma entrega repetida.
6. Confirma a mensagem no SQS somente após essas etapas.

A tabela local chama-se `ToggleMasterAnalytics` e possui
`event_id`, do tipo String, como chave de partição.

## Formato do evento

Exemplo:

```json
{
  "event_id": "65caa538be12cee1f9ed370a67b81524",
  "user_id": "usuario-123",
  "flag_name": "enable-new-dashboard",
  "result": true,
  "timestamp": "2026-10-18T14:21:50.000Z"
}
```

As validações incluem:
- Corpo JSON do tipo objeto.
- Identificador, usuário e nome da flag como strings preenchidas.
- `result` como booleano, sem aceitar textos como `"true"`.
- Data e hora válidas, com fuso horário.

Limites em bytes:

| Campo | Limite |
|---|---|
| event_id | 128 |
| user_id | 256 |
| flag_name | 100 |
| timestamp | 64 |

Por compatibilidade, eventos antigos sem `event_id` no corpo utilizam
o `MessageId` do SQS como identificador.

## Entregas repetidas

A gravação utiliza uma condição para não substituir um evento existente.

Se o mesmo `event_id` já estiver armazenado:
- Conteúdo igual: a entrega é reconhecida e a mensagem é confirmada.
- Conteúdo diferente: a mensagem é rejeitada e não é confirmada.

Esse tratamento evita duplicação do registro para o mesmo evento.
Ele não transforma toda a cadeia em uma garantia de entrega exatamente
uma vez.

## Falhas e DLQ

Mensagens inválidas não são apagadas da fila principal.
Falhas operacionais também deixam mensagens sem confirmação.

A configuração local do ElasticMQ encaminha mensagens para
`togglemaster-events-dlq` após cinco recebimentos sem confirmação.

O analytics não consome a DLQ automaticamente.
As mensagens nela precisam ser inspecionadas antes de eventual
correção, reenvio ou remoção.

A aplicação evita receber novas mensagens enquanto a verificação
da tabela DynamoDB falha. Uma mensagem já recebida pode precisar
aguardar o fim do prazo de visibilidade antes de ser processada novamente.

## Ciclo de vida

O arquivo `gunicorn.conf.py` configura um worker HTTP e inicia
uma thread consumidora depois que a aplicação é carregada.

Importar o módulo `app` não inicia automaticamente o consumidor.
Isso permite usar o módulo nos comandos de diagnóstico.

Ao encerrar o worker, o Gunicorn solicita a parada do consumidor.
A thread recebe até 35 segundos para finalizar.

Os prazos configurados são:
- Até 35 segundos de espera pela thread consumidora.
- Até 45 segundos de encerramento gracioso do Gunicorn.
- Até 50 segundos antes de o Docker forçar a parada.

Mensagens sem confirmação podem ser entregues novamente.

Para executar pelo Gunicorn, use a configuração fornecida:

```text
gunicorn --config gunicorn.conf.py app:app
```

Executar Gunicorn sem esse arquivo não aciona os hooks que iniciam
e encerram o consumidor.

## Operação

Execute na raiz do repositório:

```powershell
docker compose logs --tail 30 analytics-service
```

Verifique a prontidão:

```powershell
Invoke-RestMethod -Uri "http://localhost:8005/ready"
```

O roteiro para gerar uma avaliação e consultar o evento no DynamoDB
está no [README principal](../README.md).
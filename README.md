# ToggleMaster — Tech Challenge Fase 2

Projeto acadêmico de conteinerização e implantação de microsserviços,
desenvolvido na pós-graduação da FIAP.

## Status

O ambiente local integrado está implementado e foi validado com Docker Compose.

Foram testados:
- Inicialização com volumes novos.
- Criação e validação de chaves de API.
- Segregação dos usuários de aplicação nos bancos PostgreSQL.
- Criação e consulta de flags e regras de segmentação.
- Avaliação de flags e uso do cache Redis.
- Publicação de eventos no SQS local e persistência no DynamoDB local.
- Reconhecimento de eventos repetidos.
- Encerramento controlado do evaluation e do analytics.
- Encaminhamento de mensagens inválidas para a DLQ.
- Persistência dos dados após recriação dos containers de SQS e DynamoDB.
- Indisponibilidade e recuperação do DynamoDB.
- Diferenciação entre credenciais inválidas e falhas de autenticação.

A implantação em cloud e a configuração Kubernetes/GitOps são etapas posteriores.

## Arquitetura local

| Serviço | Tecnologia | Responsabilidade |
|---|---|---|
| auth-service | Go | Criação e validação de chaves de API |
| flag-service | Python | Gerenciamento das definições de flags |
| targeting-service | Python | Gerenciamento das regras de segmentação |
| evaluation-service | Go | Avaliação das flags, cache e publicação de eventos |
| analytics-service | Python | Consumo de eventos e gravação no DynamoDB |
| auth-db | PostgreSQL | Banco de autenticação |
| flag-db | PostgreSQL | Bancos lógicos separados de flags e targeting |
| redis | Redis | Cache das definições e regras |
| sqs | ElasticMQ | Emulação local do SQS, incluindo DLQ |
| dynamodb | DynamoDB Local | Armazenamento dos eventos |

O fluxo principal é:

```text
Cliente -> evaluation-service -> Redis
                     |
                     +-> flag-service -------> flags_db
                     +-> targeting-service --> targeting_db
                              |
                              +-> auth-service -> auth_db

evaluation-service -> SQS local -> analytics-service -> DynamoDB local
                          |
                          +-> DLQ, após falhas repetidas de processamento
```

São dez containers permanentes. O enunciado prevê nove, mas o fluxo
integralmente local também precisa de um substituto para o SQS.
O ElasticMQ é o décimo componente e permite testar a comunicação assíncrona
sem depender de uma conta AWS.

Existem ainda dois containers temporários de preparação:

| Inicializador | Função |
|---|---|
| dynamodb-init | Aguarda o DynamoDB e cria a tabela, caso ela não exista |
| service-key-init | Cria ou reutiliza uma chave de API exclusiva do evaluation |

Esses inicializadores terminam após a execução.
O estado `Exited (0)` indica conclusão com sucesso.

## Pré-requisitos

- Git.
- Docker Engine ou Docker Desktop com containers Linux.
- Docker Compose com suporte ao comando `docker compose`.
- Portas locais 8001 a 8005 disponíveis.

Os exemplos abaixo usam PowerShell e devem ser executados na raiz
do repositório. Não é necessário instalar Go, Python, PostgreSQL,
Redis ou AWS CLI na máquina para executar o ambiente com Compose.

## Instalação

Clone o repositório:

```powershell
git clone https://github.com/RaiTulik/ToggleMaster.git
Set-Location ToggleMaster
```

Na primeira instalação, copie o arquivo de exemplo:

```powershell
Copy-Item .env.example .env
```

Se já existir um `.env`, preserve sua configuração.
Os valores de exemplo são exclusivos para desenvolvimento local.

Valide a configuração:

```powershell
docker compose config --quiet
```

Construa as imagens e inicie o ambiente:

```powershell
docker compose up -d --build
```

Confira os containers:

```powershell
docker compose ps -a
```

Os dez serviços permanentes devem permanecer ativos.
Os dois inicializadores devem concluir com código de saída 0.

Na primeira execução, o download das imagens e a preparação dos bancos
podem levar alguns minutos.

## Configuração e credenciais

O `.env` da raiz fornece ao Compose as credenciais locais.

Os serviços acessam PostgreSQL com usuários exclusivos:
- `auth_app`: banco `auth_db`.
- `flag_app`: banco `flags_db`.
- `targeting_app`: banco `targeting_db`.

Os usuários administrativos dos containers PostgreSQL são utilizados
na preparação dos bancos, não pelas aplicações.

Os scripts de inicialização do PostgreSQL são executados automaticamente
somente quando o volume de dados está vazio. Alterar o `.env` não modifica
automaticamente senhas e permissões já armazenadas em volumes existentes.

A chave do evaluation é preparada automaticamente e armazenada no volume
`service-key-data`. O evaluation recebe acesso de leitura ao arquivo.
Não é necessário copiar essa chave para o `.env`.

A `MASTER_KEY` é usada para criar chaves administrativas de acesso à API.
Ela não substitui as credenciais individuais dos bancos.

ElasticMQ e DynamoDB Local usam credenciais fictícias configuradas no Compose.
Este ambiente local não precisa de credenciais ou recursos reais da AWS.

## Portas e disponibilidade

As portas publicadas estão vinculadas a `127.0.0.1`.

| Serviço | Porta | Liveness | Readiness |
|---|---|---|---|
| Auth | 8001 | `/health` | `/ready` |
| Flag | 8002 | `/health` | Não implementado |
| Targeting | 8003 | `/health` | Não implementado |
| Evaluation | 8004 | `/health` | `/ready` |
| Analytics | 8005 | `/health` | `/ready` |

PostgreSQL, Redis, ElasticMQ e DynamoDB são acessados pela rede interna
do Compose, sem publicação de portas no host.

Os endpoints `/health` verificam a resposta do processo HTTP.
Eles não comprovam a disponibilidade de todas as dependências.

A prontidão do auth verifica a conexão com PostgreSQL.
A do evaluation verifica Redis, encerramento e capacidade da fila interna.
A do analytics considera a execução do consumidor e suas verificações
recentes de DynamoDB e SQS.

Confira a prontidão:

```powershell
Invoke-RestMethod -Uri "http://localhost:8001/ready"
Invoke-RestMethod -Uri "http://localhost:8004/ready"
Invoke-RestMethod -Uri "http://localhost:8005/ready"
```

A resposta esperada é `status: ready`. O analytics pode precisar de um ciclo
de consulta da fila antes de indicar prontidão.

## Teste do fluxo completo

Execute os blocos no mesmo terminal PowerShell.

Crie uma chave para os testes. O exemplo pressupõe a `MASTER_KEY` padrão
do `.env.example`; ajuste caso tenha definido outro valor:

```powershell
$chaveTeste = Invoke-RestMethod -Method Post `
    -Uri "http://localhost:8001/admin/keys" `
    -Headers @{ Authorization = "Bearer local_master_123" } `
    -ContentType "application/json" `
    -Body '{"name":"teste-documentacao"}'

$headersTeste = @{ Authorization = "Bearer $($chaveTeste.key)" }
$nomeFlag = "teste-local-$([guid]::NewGuid().ToString('N'))"
```

Crie uma flag habilitada:

```powershell
$corpoFlag = @{
    name = $nomeFlag
    description = "Validacao do ambiente local"
    is_enabled = $true
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
    -Uri "http://localhost:8002/flags" `
    -Headers $headersTeste `
    -ContentType "application/json" `
    -Body $corpoFlag
```

Crie uma regra que habilita a flag para 100% dos usuários:

```powershell
$corpoRegra = @{
    flag_name = $nomeFlag
    is_enabled = $true
    rules = @{
        type = "PERCENTAGE"
        value = 100
    }
} | ConvertTo-Json -Depth 3

Invoke-RestMethod -Method Post `
    -Uri "http://localhost:8003/rules" `
    -Headers $headersTeste `
    -ContentType "application/json" `
    -Body $corpoRegra
```

Avalie a flag:

```powershell
$avaliacao = Invoke-RestMethod `
    -Uri "http://localhost:8004/evaluate?user_id=usuario-documentacao&flag_name=$nomeFlag"

$avaliacao
```

A resposta deve conter `result: True` e um `event_id`.

Após alguns segundos, consulte o evento pelo identificador retornado:

```powershell
$env:EVENT_ID_TESTE = $avaliacao.event_id

docker compose exec -T -e "EVENT_ID_TESTE=$env:EVENT_ID_TESTE" analytics-service python -c "import app,json,os; response=app.dynamodb_client.get_item(TableName=app.DYNAMODB_TABLE_NAME,Key={'event_id':{'S':os.environ['EVENT_ID_TESTE']}},ConsistentRead=True); print(json.dumps(response.get('Item'),indent=2))"

Remove-Item Env:EVENT_ID_TESTE
```

O item deve apresentar o mesmo `event_id`, usuário, flag e resultado.
Como o processamento é assíncrono, execute novamente o bloco inteiro
de consulta caso ele retorne `null`, incluindo a definição de
`$env:EVENT_ID_TESTE = $avaliacao.event_id`.

Consulte os logs:

```powershell
docker compose logs --tail 30 evaluation-service analytics-service
```

## Comportamento dos eventos

Cada avaliação recebe um `event_id`, utilizado como chave no DynamoDB.

O evaluation possui uma fila interna limitada e quatro enviadores.
Se a fila estiver cheia ou encerrando, a requisição retorna 503.

A resposta HTTP de sucesso indica que o evento entrou na fila interna;
ela não garante que o SQS já aceitou a mensagem.
Essa fila reside em memória e não constitui uma outbox persistente.
Falhas no envio são registradas nos logs.

O analytics valida os campos recebidos e grava o evento antes de confirmar
a mensagem na fila.

Entregas repetidas com o mesmo identificador e conteúdo são reconhecidas.
Um identificador reutilizado com conteúdo diferente é rejeitado.
Eventos antigos sem `event_id` no corpo utilizam o `MessageId` como identificador.

Mensagens inválidas não são confirmadas. A configuração local encaminha
a mensagem para `togglemaster-events-dlq` após cinco recebimentos sem
confirmação. O prazo de visibilidade utilizado é de 60 segundos.

## Autenticação e falhas

- Chave ausente, inválida ou inativa: 401 nos endpoints protegidos por chave de API.
- Chave mestra ausente ou incorreta na criação de chaves: 403.
- Banco do auth indisponível: 503.
- Falha de comunicação com o auth em flag ou targeting: 503.
- Timeout de comunicação com o auth em flag ou targeting: 504.

Uma falha de infraestrutura não é interpretada como revogação da chave.

Para substituir uma chave do evaluation que tenha sido revogada,
execute novamente a preparação e reinicie o serviço:

```powershell
docker compose run --rm service-key-init
docker compose restart evaluation-service
```

A chave é carregada pelo evaluation na inicialização.

## Recuperação do PostgreSQL de flags e targeting

Flag e targeting verificam as conexões retiradas do pool e descartam
conexões quebradas. Após o retorno do banco, novas requisições podem
ser atendidas sem reiniciar as aplicações.

Falhas de conexão retornam 503. A verificação da conexão pode ser repetida,
mas operações de escrita não são repetidas automaticamente.

Se a conexão cair durante uma escrita, seu resultado pode ser incerto.
Consulte o recurso antes de tentar novamente.

## Cache

O evaluation utiliza cache Redis com TTL de 30 segundos.
Alterações em flags e regras podem levar esse tempo para aparecer
em avaliações que reutilizem dados já armazenados.

Uma regra inexistente permite usar o comportamento padrão da flag.
Uma falha de comunicação com targeting não é tratada como regra inexistente.

## Persistência e operação

Os volumes nomeados preservam:
- Bancos PostgreSQL.
- Mensagens do ElasticMQ.
- Dados do DynamoDB Local.
- Chave de API do evaluation.

O Redis funciona como cache e não possui volume persistente neste ambiente.

Para parar mantendo containers e volumes:

```powershell
docker compose stop
```

Para iniciar novamente:

```powershell
docker compose up -d
```

Para remover containers e rede, preservando os volumes nomeados:

```powershell
docker compose down
```

Adicionar `--volumes` ao comando `down` remove também os volumes e seus dados.
Esse procedimento não faz parte da operação normal.

## Próximas etapas

- Implantação das imagens no Amazon ECR.
- Implantação dos serviços no Amazon EKS.
- Uso dos serviços gerenciados de dados e mensageria na AWS.
- Configuração Kubernetes de recursos, probes e escalabilidade.
- GitOps com Argo CD.
- Gestão de segredos com External Secrets Operator.
- HPA para evaluation e avaliação de KEDA para analytics,
  conforme as permissões do ambiente AWS.

O repositório destinado às configurações GitOps é:
https://github.com/RaiTulik/ToggleMaster-GitOps

Essas etapas não são apresentadas como concluídas nesta documentação.

## Origem dos códigos

Os códigos iniciais foram fornecidos pelos repositórios do desafio:

- https://github.com/FIAP-TCs/auth-service
- https://github.com/FIAP-TCs/flag-service
- https://github.com/FIAP-TCs/targeting-service
- https://github.com/FIAP-TCs/evaluation-service
- https://github.com/FIAP-TCs/analytics-service

Este repositório reúne e adapta esses códigos para a atividade.
As alterações estão registradas no histórico Git.
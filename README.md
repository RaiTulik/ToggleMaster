# ToggleMaster — Tech Challenge Fase 2

Projeto acadêmico de conteinerização e implantação de microsserviços,
desenvolvido na pós-graduação da FIAP.

## Status

**Fase 2 — implementação local e implantação AWS realizadas e validadas.**

O ambiente local foi implementado com Docker Compose e testado com volumes novos, criação e validação de chaves de API, bancos segregados, flags e regras, avaliação com Redis, publicação e consumo de eventos, persistência no DynamoDB Local, idempotência, DLQ, recuperação de dependências e encerramento controlado.

Na AWS Academy foram implantados cinco microsserviços no Amazon EKS, com imagens no Amazon ECR, três bancos Amazon RDS PostgreSQL, Amazon ElastiCache Redis, Amazon SQS e Amazon DynamoDB. O cluster utiliza NGINX Ingress Controller, Metrics Server e HPA de CPU para Evaluation e Analytics.

**Validações realizadas na AWS:** cinco pods funcionais, acesso externo a `/evaluate` com HTTP 200, criação/consulta/exclusão de regras no Targeting, Evaluation HPA escalando de 1 para 3 réplicas, Analytics HPA chegando a 2 réplicas e eventos entregues via SQS e gravados no DynamoDB. Em um teste de carga foram encontrados **8.708 eventos** do usuário de teste na tabela. Uma mensagem enviada manualmente ao SQS também foi confirmada no DynamoDB.

> Os recursos AWS pertencem a um laboratório temporário e podem deixar de estar disponíveis após seu encerramento. Os resultados acima descrevem testes realizados, não disponibilidade permanente.

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
| Flag | 8002 | `/health` | `/ready` |
| Targeting | 8003 | `/health` | `/ready` |
| Evaluation | 8004 | `/health` | `/ready` |
| Analytics | 8005 | `/health` | `/ready` |

PostgreSQL, Redis, ElasticMQ e DynamoDB são acessados pela rede interna
do Compose, sem publicação de portas no host.

Os endpoints `/health` verificam a resposta do processo HTTP.
Eles não comprovam a disponibilidade de todas as dependências.

A prontidão do auth, do flag e do targeting verifica a conexão com PostgreSQL.
A do evaluation verifica Redis, encerramento e capacidade da fila interna.
A do analytics considera a execução do consumidor e suas verificações
recentes de DynamoDB e SQS.

Confira a prontidão:

```powershell
Invoke-RestMethod -Uri "http://localhost:8001/ready"
Invoke-RestMethod -Uri "http://localhost:8002/ready"
Invoke-RestMethod -Uri "http://localhost:8003/ready"
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

## Arquitetura AWS — Fase 2

A implantação foi realizada na região `us-east-1` em ambiente **AWS Academy**, com recursos configurados no laboratório e manifests Kubernetes versionados em `kubernetes/`.

| Camada | Recurso | Uso |
|---|---|---|
| Contêineres | Amazon ECR | Cinco imagens dos microsserviços, tag `fase2` |
| Orquestração | Amazon EKS | Cluster `togglemaster-eks`, com Managed Node Group e dois nós EC2 |
| Entrada HTTP | NGINX Ingress Controller + balanceador AWS | Encaminhamento externo de `/evaluate` ao Evaluation |
| Autenticação | Amazon RDS PostgreSQL | Instância `togglemaster-auth-db`, banco `authdb` |
| Flags | Amazon RDS PostgreSQL | Instância `togglemaster-flag-db`, banco `flagdb` |
| Segmentação | Amazon RDS PostgreSQL | Instância `togglemaster-targeting-db`, banco `targetingdb` |
| Cache | Amazon ElastiCache Redis | Cache consultado pelo Evaluation |
| Eventos | Amazon SQS Standard | Fila `togglemaster-events`, com fila de mensagens mortas (DLQ) |
| Analytics | Amazon DynamoDB | Tabela `ToggleMasterAnalytics`, chave de partição `event_id` |
| Métricas | Kubernetes Metrics Server | Métricas de CPU utilizadas pelos HPAs |

Fluxo simplificado:

```text
Cliente HTTP
    |
    v
AWS Load Balancer -> NGINX Ingress (/evaluate)
                          |
                          v
                  Evaluation Service <----> ElastiCache Redis
                     |       |
                     |       +--> Flag Service ------> RDS flags
                     |       +--> Targeting Service -> RDS targeting
                     |                    |
                     |                    +--> Auth Service -> RDS auth
                     v
                 Amazon SQS (+ DLQ)
                     |
                     v
                Analytics Service
                     |
                     v
              Amazon DynamoDB
```

O Auth valida chaves usadas pelos endpoints protegidos. O Evaluation utiliza uma chave de serviço para comunicação interna e publica eventos de avaliação de forma assíncrona. O Analytics consome mensagens e persiste os eventos na tabela DynamoDB.

### Kubernetes e manifests

Os arquivos versionados estão organizados assim:

```text
kubernetes/
  namespace.yaml
  ingress.yaml
  shared/configmap.yaml
  auth/{deployment,service}.yaml
  flag/{deployment,service}.yaml
  targeting/{deployment,service}.yaml
  evaluation/{deployment,service,hpa}.yaml
  analytics/{deployment,service,hpa}.yaml
```

Todos os cinco serviços possuem `Deployment`, `Service` interno (`ClusterIP`), `readinessProbe` em `/ready`, `livenessProbe` em `/health`, e limites/solicitações de CPU e memória. Os serviços usam as portas 8001 (Auth), 8002 (Flag), 8003 (Targeting), 8004 (Evaluation) e 8005 (Analytics).

| Serviço | CPU request | CPU limit | Memória request | Memória limit |
|---|---:|---:|---:|---:|
| Auth | 50m | 250m | 64Mi | 256Mi |
| Flag | 50m | 250m | 64Mi | 256Mi |
| Targeting | 50m | 250m | 64Mi | 256Mi |
| Evaluation | 100m | 500m | 128Mi | 512Mi |
| Analytics | 100m | 500m | 128Mi | 512Mi |

O ConfigMap `togglemaster-config` centraliza `AWS_REGION`, `AWS_DYNAMODB_TABLE`, `AWS_SQS_URL` e as URLs internas dos serviços Auth, Flag e Targeting. Os endereços `http://auth-service:8001`, `http://flag-service:8002` e `http://targeting-service:8003` utilizam resolução DNS interna do Kubernetes.

O Ingress `togglemaster-ingress`, com classe `nginx`, publica **apenas** o caminho `/evaluate` para o `evaluation-service` na porta 8004. As demais APIs não são expostas por esse Ingress. O balanceador público é criado pelo controlador instalado no cluster; o manifesto do controlador e sua instalação não estão automatizados neste repositório.

### Secrets e cuidados de segurança

**Os valores de Secrets não são versionados.** Antes de aplicar os Deployments, é necessário criar no namespace `togglemaster`:

| Secret | Chaves exigidas |
|---|---|
| `auth-secrets` | `DATABASE_URL`, `MASTER_KEY` |
| `flag-secrets` | `DATABASE_URL` |
| `targeting-secrets` | `DATABASE_URL` |
| `evaluation-secrets` | `REDIS_URL`, `SERVICE_API_KEY` |

`DATABASE_URL` contém a string de conexão de cada RDS, `REDIS_URL` aponta para o ElastiCache e `SERVICE_API_KEY` deve corresponder a uma chave válida no Auth. Não publique senhas, tokens, chaves nem manifests de Secrets com valores reais. Crie os Secrets com um método seguro apropriado ao ambiente antes de executar os manifests. A chave da aplicação e os dados iniciais dos bancos também precisam ser preparados para uma nova implantação.

As imagens ECR e a URL SQS dos manifests contêm o ID de conta do laboratório. **Para reproduzir em outra conta AWS, altere essas referências**, além dos endpoints dos serviços gerenciados, credenciais e políticas de rede.

### Implantação e verificação

Pré-requisitos para uma implantação equivalente: AWS CLI autenticado e autorizado, `kubectl` configurado para o cluster EKS, imagens publicadas no ECR, três RDS acessíveis pelos pods, ElastiCache, fila SQS/DLQ, tabela DynamoDB, controlador NGINX Ingress e Metrics Server instalados, além de Secrets e dados iniciais preparados.

Exemplo de conexão e inspeção do cluster existente:

```powershell
aws eks update-kubeconfig --region us-east-1 --name togglemaster-eks --profile academy
kubectl get nodes
kubectl get pods -n togglemaster
kubectl get deployments,services,ingress,hpa -n togglemaster
```

Com todas as dependências provisionadas e os Secrets criados, os manifests podem ser aplicados na ordem abaixo:

```powershell
kubectl apply -f kubernetes/namespace.yaml
kubectl apply -f kubernetes/shared/configmap.yaml
kubectl apply -f kubernetes/auth/
kubectl apply -f kubernetes/flag/
kubectl apply -f kubernetes/targeting/
kubectl apply -f kubernetes/evaluation/
kubectl apply -f kubernetes/analytics/
kubectl apply -f kubernetes/ingress.yaml
kubectl get pods -n togglemaster
kubectl get hpa -n togglemaster
```

**Atenção:** os comandos acima **não criam** EKS, ECR, RDS, ElastiCache, SQS, DynamoDB, NGINX Ingress Controller, Metrics Server ou Secrets. Esses componentes precisam existir antes. A infraestrutura foi configurada no AWS Academy e não está integralmente declarada como IaC neste repositório.

Para consultar o endereço do Ingress:

```powershell
kubectl get ingress togglemaster-ingress -n togglemaster
kubectl get svc -n ingress-nginx
```

Com o hostname retornado pelo balanceador, é possível validar a rota pública:

```powershell
$ingressHost = "SUBSTITUIR_PELO_HOSTNAME_DO_BALANCEADOR"
Invoke-RestMethod -Uri "http://$ingressHost/evaluate?user_id=teste-readme&flag_name=aws-video-flag"
```

O exemplo usa a flag de demonstração `aws-video-flag`, que precisa existir no banco de flags para reproduzir o cenário. Uma resposta HTTP 200 com `event_id` comprova o atendimento da requisição, mas a persistência do evento é assíncrona e deve ser verificada separadamente.

### Escalabilidade automática

Os manifests `kubernetes/evaluation/hpa.yaml` e `kubernetes/analytics/hpa.yaml` usam `autoscaling/v2`, métrica de **CPU**, meta de **60% de utilização** e faixa de **1 a 3 réplicas** por serviço. A utilização é calculada sobre o CPU *request* (100m para ambos), não sobre o limite de 500m.

```powershell
kubectl get hpa -n togglemaster -w
```

Nos testes realizados, o Evaluation escalou de **1 para 3 réplicas** durante requisições concorrentes; o Analytics atingiu **2 réplicas**. Os resultados dependem da carga e das métricas observadas no momento, não sendo garantidos em toda execução. O HPA do Analytics reage a CPU, **não** diretamente ao tamanho da fila SQS. KEDA não foi implantado; o HPA nativo foi a alternativa utilizada no laboratório.

### Evidências funcionais obtidas na AWS

- **Pods e dependências:** cinco microsserviços em execução no EKS, com readiness e liveness configuradas.
- **Entrada externa:** requisição `GET /evaluate` pelo NGINX Ingress retornou HTTP 200 e `event_id`.
- **Targeting + RDS + Auth:** criação de regra (`POST /rules`, HTTP 201), consulta (`GET /rules/{id}`, HTTP 200) e exclusão (`DELETE /rules/{id}`, HTTP 204) executadas com sucesso a partir do ambiente Kubernetes.
- **HPA Evaluation:** escala de 1 para 3 réplicas sob carga, com CPU observada acima da meta de 60%.
- **Eventos de avaliação:** teste de carga resultou em **8.708 itens** identificados pelo usuário de teste `teste-carga` na tabela DynamoDB, evidenciando o fluxo Evaluation → SQS → Analytics → DynamoDB.
- **SQS manual:** envio de mensagem à fila `togglemaster-events`, seguido de consulta por `event_id` no DynamoDB, confirmou o processamento assíncrono.
- **HPA Analytics:** observada escala de 1 para 2 réplicas durante os testes.

Essas são observações da execução realizada, não um teste de desempenho padronizado ou uma garantia de entrega de mensagens em quaisquer condições.

### Restrições e decisões do AWS Academy

O laboratório possui permissões limitadas e utiliza o papel IAM `LabRole`. O acesso do Analytics a SQS e DynamoDB foi viabilizado pelas credenciais disponibilizadas ao nó EC2 no laboratório, incluindo ajuste de alcance do serviço de metadados da instância (IMDSv2). **Esse é um expediente específico do ambiente acadêmico**, não uma recomendação para produção. Em uma implantação real, o acesso deveria ser concedido com identidade e permissões mínimas por workload (por exemplo, EKS Pod Identity ou IRSA, conforme as permissões disponíveis), sem compartilhar privilégios do nó.

Os recursos gerenciados, o balanceador e os nós EC2 podem gerar custos enquanto estiverem ativos. É necessário acompanhar o orçamento/créditos do laboratório e encerrar os recursos quando a demonstração não for mais necessária.

### Recursos não implementados e possíveis evoluções

A implantação realizada **não inclui** GitOps operacional com Argo CD, External Secrets Operator nem escalonamento por tamanho de fila com KEDA. Esses itens foram considerados como possíveis evoluções, mas não são apresentados como concluídos. Também não há provisionamento integral da infraestrutura por Terraform ou CloudFormation neste repositório.

Repositório reservado para eventual evolução de GitOps: https://github.com/RaiTulik/ToggleMaster-GitOps

### Entregáveis acadêmicos

- **Código-fonte e manifests:** https://github.com/RaiTulik/ToggleMaster
- **Vídeo de demonstração (até 20 minutos):** inserir link após a gravação.
- **Relatório de entrega:** incluir participantes, RM, usuários do Discord, link do repositório, link do vídeo, diagrama da arquitetura e justificativas técnicas exigidas pelo enunciado.

## Origem dos códigos

Os códigos iniciais foram fornecidos pelos repositórios do desafio:

- https://github.com/FIAP-TCs/auth-service
- https://github.com/FIAP-TCs/flag-service
- https://github.com/FIAP-TCs/targeting-service
- https://github.com/FIAP-TCs/evaluation-service
- https://github.com/FIAP-TCs/analytics-service

Este repositório reúne e adapta esses códigos para a atividade.
As alterações estão registradas no histórico Git.
# ToggleMaster — Tech Challenge Fase 2

Projeto acadêmico de conteinerização e implantação de microsserviços,
desenvolvido na pós-graduação da FIAP.

## Status

Em desenvolvimento. Os códigos iniciais foram importados para análise.
A execução integrada ainda não foi validada.

## Microsserviços

| Serviço | Linguagem | Responsabilidade |
|---|---|---|
| auth-service | Go | Criação e validação de chaves de API |
| flag-service | Python | Gerenciamento das feature flags |
| targeting-service | Python | Gerenciamento das regras de segmentação |
| evaluation-service | Go | Avaliação das flags e publicação de eventos |
| analytics-service | Python | Consumo de eventos e armazenamento de análises |

## Escopo planejado

- Analisar e corrigir os serviços fornecidos.
- Criar Dockerfiles e ambiente local com Docker Compose.
- Publicar as imagens no Amazon ECR.
- Implantar os serviços no Amazon EKS.
- Integrar PostgreSQL, Redis, SQS e DynamoDB.
- Gerenciar a implantação com Argo CD.
- Gerenciar segredos com External Secrets Operator.
- Configurar HPA para evaluation-service.
- Configurar KEDA para analytics-service, conforme as permissões da AWS.

Os manifestos Kubernetes e as configurações GitOps ficarão em um
repositório separado, a ser criado.

## Origem dos códigos

Os códigos iniciais foram retirados do github fornecido no desafio:

- https://github.com/FIAP-TCs/auth-service
- https://github.com/FIAP-TCs/flag-service
- https://github.com/FIAP-TCs/targeting-service
- https://github.com/FIAP-TCs/evaluation-service
- https://github.com/FIAP-TCs/analytics-service

Este repositório reúne esses códigos para desenvolvimento da atividade.
As alterações realizadas durante o projeto serão registradas no histórico Git.
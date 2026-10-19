# Auth Service

Serviço Go responsável pela criação e validação das chaves de API do ToggleMaster.

## Execução local

Use o Docker Compose na raiz do repositório, conforme o
[guia principal](../README.md).

O serviço utiliza a porta local `8001` e depende do PostgreSQL `auth-db`.
A preparação do banco e das permissões ocorre automaticamente na primeira
inicialização de um volume vazio.

## Configuração

| Variável | Finalidade |
|---|---|
| PORT | Porta HTTP; padrão 8001 |
| DATABASE_URL | Conexão com o banco de autenticação |
| MASTER_KEY | Credencial administrativa para criar chaves de API |

No Compose, a aplicação acessa o banco `auth_db` com o usuário `auth_app`.
O usuário administrativo do PostgreSQL é reservado à preparação do banco.

As credenciais de exemplo são exclusivas para desenvolvimento local.

## Endpoints

| Método | Rota | Autenticação | Finalidade |
|---|---|---|---|
| GET | `/health` | Não exige | Verificar resposta do processo HTTP |
| GET | `/ready` | Não exige | Verificar conexão com o banco |
| POST | `/admin/keys` | Bearer com a MASTER_KEY | Criar uma chave de API |
| GET | `/validate` | Bearer com uma chave de API | Validar a chave |

Corpo para criação de uma chave:

```json
{"name":"minha-aplicacao"}
```

A resposta de criação apresenta a chave em texto uma única vez.
O banco armazena seu hash.

O endpoint `/validate` aceita somente chaves existentes e ativas.

## Respostas e falhas

| Situação | HTTP |
|---|---|
| Chave criada | 201 |
| Chave de API válida | 200 |
| Chave de API ausente, inválida ou inativa | 401 |
| MASTER_KEY ausente ou incorreta | 403 |
| Corpo inválido na criação | 400 |
| Método não permitido | 405 |
| Falha no banco durante validação ou criação | 503 |
| Banco indisponível no `/ready` | 503 |

As consultas de validação e criação possuem prazo de dois segundos.
A verificação do `/ready` possui prazo de um segundo.

Um erro de banco não é interpretado como chave inválida.
Se uma criação falhar por perda de conexão ou timeout, a resposta não
confirma se a gravação chegou a ser concluída.

## Operação

O servidor trata SIGTERM e permite até cinco segundos para concluir
as requisições HTTP em andamento antes de fechar suas conexões.

Para consultar os logs, execute na raiz do repositório:

```powershell
docker compose logs --tail 30 auth-service
```

O roteiro de instalação e os testes integrados estão no
[README principal](../README.md).
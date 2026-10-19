import time

import boto3
from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

client = boto3.client(
    "dynamodb",
    endpoint_url="http://dynamodb:8000",
    region_name="us-east-1",
    aws_access_key_id="local",
    aws_secret_access_key="local",
)

table_name = "ToggleMasterAnalytics"

# Aguarda o DynamoDB ficar acessivel.
for attempt in range(30):
    try:
        client.list_tables()
        break
    except (
        EndpointConnectionError,
        ConnectionClosedError,
        ConnectTimeoutError,
        ReadTimeoutError,
    ):
        if attempt == 29:
            raise
        time.sleep(2)

try:
    client.create_table(
        TableName=table_name,
        KeySchema=[
            {"AttributeName": "event_id", "KeyType": "HASH"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "event_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    print(f"Tabela {table_name} criada.")
except ClientError as error:
    if error.response["Error"]["Code"] != "ResourceInUseException":
        raise
    print(f"Tabela {table_name} ja existe.")

client.get_waiter("table_exists").wait(TableName=table_name)
print("Tabela pronta para uso.")
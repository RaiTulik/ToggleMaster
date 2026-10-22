
import os
import unittest
from unittest.mock import patch

from botocore.exceptions import ClientError

# Configuracoes ficticias utilizadas apenas nos testes.
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault(
    "AWS_SQS_URL",
    "https://sqs.us-east-1.amazonaws.com/000000000000/test-queue",
)
os.environ.setdefault("AWS_DYNAMODB_TABLE", "test-events")
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")

import app as analytics_app


class TestAnalyticsProcessing(unittest.TestCase):

    def setUp(self):
        self.message = {
            "MessageId": "mensagem-1",
            "ReceiptHandle": "receipt-teste",
            "Body": (
                '{"event_id":"evento-1",'
                '"user_id":"usuario-1",'
                '"flag_name":"flag-teste",'
                '"result":true,'
                '"timestamp":"2026-10-22T12:00:00Z"}'
            ),
        }

    @patch.object(analytics_app, "sqs_client")
    @patch.object(analytics_app, "dynamodb_client")
    def test_exclui_mensagem_apos_persistir(
        self, mock_dynamodb, mock_sqs
    ):
        analytics_app.process_message(self.message)

        mock_dynamodb.put_item.assert_called_once()
        mock_sqs.delete_message.assert_called_once_with(
            QueueUrl=analytics_app.SQS_QUEUE_URL,
            ReceiptHandle="receipt-teste",
        )

    @patch.object(analytics_app.stop_event, "wait")
    @patch.object(analytics_app, "sqs_client")
    @patch.object(analytics_app, "dynamodb_client")
    def test_nao_exclui_mensagem_se_dynamodb_falhar(
        self, mock_dynamodb, mock_sqs, mock_wait
    ):
        mock_dynamodb.put_item.side_effect = RuntimeError(
            "DynamoDB indisponivel"
        )

        analytics_app.process_message(self.message)

        mock_sqs.delete_message.assert_not_called()
        mock_wait.assert_called_once_with(2)

    @patch.object(analytics_app, "sqs_client")
    @patch.object(analytics_app, "dynamodb_client")
    def test_confirma_duplicata_identica(
        self, mock_dynamodb, mock_sqs
    ):
        item = analytics_app.build_item(self.message)

        mock_dynamodb.put_item.side_effect = ClientError(
            {
                "Error": {
                    "Code": "ConditionalCheckFailedException",
                    "Message": "Evento ja existe",
                }
            },
            "PutItem",
        )

        mock_dynamodb.get_item.return_value = {
            "Item": item
        }

        analytics_app.process_message(self.message)

        mock_dynamodb.get_item.assert_called_once_with(
            TableName=analytics_app.DYNAMODB_TABLE_NAME,
            Key={"event_id": item["event_id"]},
            ConsistentRead=True,
        )

        mock_sqs.delete_message.assert_called_once_with(
            QueueUrl=analytics_app.SQS_QUEUE_URL,
            ReceiptHandle="receipt-teste",
        )

    @patch.object(analytics_app, "sqs_client")
    @patch.object(analytics_app, "dynamodb_client")
    def test_rejeita_event_id_com_conteudo_diferente(
        self, mock_dynamodb, mock_sqs
    ):
        item = analytics_app.build_item(self.message)

        mock_dynamodb.put_item.side_effect = ClientError(
            {
                "Error": {
                    "Code": "ConditionalCheckFailedException",
                    "Message": "Evento ja existe",
                }
            },
            "PutItem",
        )

        existing_item = {
            **item,
            "user_id": {"S": "outro-usuario"},
        }

        mock_dynamodb.get_item.return_value = {
            "Item": existing_item
        }

        analytics_app.process_message(self.message)

        mock_dynamodb.get_item.assert_called_once()
        mock_sqs.delete_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()

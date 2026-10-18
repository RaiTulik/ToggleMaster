FROM amazon/dynamodb-local@sha256:6ada631ec7aa5fc83446855eb17233e3dad184fec47477e8140c6c569cfe0c86

USER root

RUN mkdir -p /home/dynamodblocal/data \
    && chown dynamodblocal /home/dynamodblocal/data

USER dynamodblocal
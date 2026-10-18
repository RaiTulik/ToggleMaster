FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN mkdir -p /service-key \
    && chown 10001:10001 /service-key \
    && chmod 700 /service-key

COPY init-service-key.py /app/init-service-key.py

USER 10001:10001

ENTRYPOINT ["python", "/app/init-service-key.py"]
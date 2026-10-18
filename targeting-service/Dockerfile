FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt && pip check

COPY app.py .

USER 10001:10001

EXPOSE 8003

CMD ["gunicorn", "--bind", "0.0.0.0:8003", "--workers", "2", "--worker-class", "sync", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
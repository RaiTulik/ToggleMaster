FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt && pip check

COPY app.py gunicorn.conf.py ./

USER 10001:10001

EXPOSE 8005

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8005')}"
workers = 1
worker_class = "sync"
preload_app = False

timeout = 60
graceful_timeout = 45

accesslog = "-"
errorlog = "-"
capture_output = True


def post_worker_init(worker):
    from app import start_worker

    start_worker()


def worker_exit(server, worker):
    from app import stop_worker

    stop_worker()
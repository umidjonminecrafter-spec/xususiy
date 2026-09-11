"""
Gunicorn production server configuration.
"""
import multiprocessing
import os

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
backlog = 2048

# Worker processes: respect WEB_CONCURRENCY env or default to 2 workers for cloud containers
workers = int(os.getenv('WEB_CONCURRENCY', os.getenv('GUNICORN_WORKERS', '2')))
worker_class = 'sync'
worker_connections = 1000
timeout = int(os.getenv('GUNICORN_TIMEOUT', '120'))
keepalive = 5

# Process naming
proc_name = 'smarttalim_backend'

# Logging
accesslog = '-'
errorlog = '-'
loglevel = os.getenv('GUNICORN_LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" (%(L)ss)'

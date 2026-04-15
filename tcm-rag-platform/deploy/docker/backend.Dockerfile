FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc default-libmysqlclient-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY backend/ ./backend/
COPY deploy/gunicorn_conf.py ./deploy/gunicorn_conf.py

EXPOSE 8000

CMD ["gunicorn", "backend.app.main:app", "-c", "deploy/gunicorn_conf.py"]

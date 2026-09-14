FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY apps ./apps

RUN useradd --create-home --uid 10003 server \
    && mkdir -p /data/curiosity \
    && chown -R server:server /app /data
USER server
WORKDIR /app/apps/server-shell
EXPOSE 8780

CMD ["python", "server.py"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY apps/model-gateway ./model-gateway
WORKDIR /app/model-gateway
EXPOSE 8090

CMD ["python", "gateway.py"]

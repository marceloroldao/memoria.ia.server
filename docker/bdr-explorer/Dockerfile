FROM alpine:3.20 AS source

RUN apk add --no-cache git ca-certificates
ARG BDR_COMMIT=1f6b7ccbe16bdfed2f1b5dcebceb17887bf6916e
RUN git init /source && \
    git -C /source remote add origin https://github.com/marceloroldao/resolutive-DB.git && \
    git -C /source fetch --depth 1 origin "${BDR_COMMIT}" && \
    git -C /source checkout --detach FETCH_HEAD

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /build
COPY --from=source /source/pyproject.toml /source/README.md /source/LICENSE ./
COPY --from=source /source/bdr ./bdr
RUN python -m pip install --upgrade pip && python -m pip install .

WORKDIR /app
COPY apps/bdr-explorer/explorer ./explorer

RUN useradd --create-home --uid 10002 explorer && chown -R explorer:explorer /app
USER explorer
EXPOSE 8765

FROM alpine:3.20 AS source

RUN apk add --no-cache git ca-certificates
ARG MEMORIA_COMMIT=162604240f22cfab6449ebe48f4eb764d6e76d0c
RUN git init /source && \
    git -C /source remote add origin https://github.com/marceloroldao/memoria.ia.git && \
    git -C /source fetch --depth 1 origin "${MEMORIA_COMMIT}" && \
    git -C /source checkout --detach FETCH_HEAD

FROM debian:bookworm-slim AS native-builder

ARG BDR_COMMIT=1f6b7ccbe16bdfed2f1b5dcebceb17887bf6916e
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates cmake git zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY --from=source /source/include ./include
COPY --from=source /source/native ./native

RUN git init /build/resolutive-DB && \
    git -C /build/resolutive-DB remote add origin https://github.com/marceloroldao/resolutive-DB.git && \
    git -C /build/resolutive-DB fetch --depth 1 origin "${BDR_COMMIT}" && \
    git -C /build/resolutive-DB checkout --detach FETCH_HEAD && \
    cmake -S /build/native/mobile -B /build/native-build \
      -DCMAKE_BUILD_TYPE=Release \
      -DMEMORIA_BDR_ROOT=/build/resolutive-DB && \
    cmake --build /build/native-build --target memoria_mobile --config Release -j2 && \
    test -f /build/native-build/libmemoria_mobile.so

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MEMORIA_NATIVE_LIB=/usr/local/lib/libmemoria_mobile.so \
    MEMORIA_CONVERSATION_RUNTIME=native \
    MEMORIA_EPISODIC_RUNTIME=native

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 memoria \
    && mkdir -p /data \
    && chown memoria:memoria /data

COPY --from=native-builder /build/native-build/libmemoria_mobile.so /usr/local/lib/libmemoria_mobile.so
COPY --from=source /source/pyproject.toml /source/README.md /source/LICENSE ./
COPY --from=source /source/src ./src
COPY --from=source /source/scripts ./scripts

RUN python -m pip install --upgrade pip && \
    python -m pip install ".[product]" && \
    python -c "import ctypes; lib=ctypes.CDLL('/usr/local/lib/libmemoria_mobile.so'); assert lib.memoria_mobile_abi_version() == 1"

USER memoria
EXPOSE 8080
VOLUME ["/data"]

CMD ["uvicorn", "memoria_resolutiva.product_server:app", "--host", "0.0.0.0", "--port", "8080"]

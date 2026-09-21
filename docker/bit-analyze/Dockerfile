FROM alpine:3.20 AS source

RUN apk add --no-cache git ca-certificates
ARG BIT_ANALYZE_COMMIT=3c35c7a8b03e77fd553bbbbea0f5595d8696ab13
RUN git init /source && \
    git -C /source remote add origin https://github.com/marceloroldao/bit.analyze.git && \
    git -C /source fetch --depth 1 origin "${BIT_ANALYZE_COMMIT}" && \
    git -C /source checkout --detach FETCH_HEAD

FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY --from=source /source /build/source
RUN cmake -S /build/source -B /build/out -DCMAKE_BUILD_TYPE=Release && \
    cmake --build /build/out --target bit_analyze_structural_ingest --config Release -j2 && \
    test -x /build/out/bit_analyze_structural_ingest

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BIT_ANALYZE_BINARY=/usr/local/bin/bit_analyze_structural_ingest \
    BIT_ANALYZE_CONSUMER=/opt/bit-analyze/consume_ingest.py

RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10004 bitanalyze \
    && mkdir -p /state /opt/bit-analyze \
    && chown -R bitanalyze:bitanalyze /state /opt/bit-analyze

COPY --from=builder /build/out/bit_analyze_structural_ingest /usr/local/bin/bit_analyze_structural_ingest
COPY --from=source /source/tools/consume_ingest.py /opt/bit-analyze/consume_ingest.py
COPY docker/bit-analyze/worker.py /opt/bit-analyze/worker.py

RUN python -m compileall -q /opt/bit-analyze && \
    /usr/local/bin/bit_analyze_structural_ingest --help >/dev/null

USER bitanalyze
VOLUME ["/state"]

CMD ["python", "/opt/bit-analyze/worker.py"]
